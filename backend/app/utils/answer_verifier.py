"""Answer verification and grounding system.

Verifies that LLM-generated answers are properly grounded in retrieved citations.
Prevents hallucinations by checking claims against source documents.
"""
import json
from typing import List, Dict, Any, Tuple
from openai import OpenAI
import os

# Lazy load OpenAI client to avoid import-time errors
_openai_client = None

def get_openai_client():
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    return _openai_client


def extract_claims(answer: str, model: str = "gpt-4o-mini") -> List[str]:
    """Break down answer into atomic factual claims.

    Args:
        answer: The LLM-generated answer to verify
        model: OpenAI model to use

    Returns:
        List of atomic claims that can be individually verified

    Example:
        Input: "System Database uses Fox protocol on port 1911. It syncs every 30 seconds."
        Output: [
            "System Database uses Fox protocol",
            "Fox protocol uses port 1911",
            "System Database syncs every 30 seconds"
        ]
    """
    prompt = f"""Extract all factual claims from this technical answer. Break it into atomic statements that can be individually verified.

ANSWER:
{answer}

Rules:
1. Each claim should be a single factual statement
2. Split compound claims (e.g., "X uses Y on port Z" → ["X uses Y", "Y uses port Z"])
3. Ignore opinion/recommendation statements
4. Focus on technical facts (settings, values, procedures, relationships)
5. Maximum 20 claims

Output JSON:
{{
    "claims": ["claim 1", "claim 2", ...]
}}
"""

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a technical fact extractor. Output only JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=800
        )

        result = json.loads(response.choices[0].message.content)
        return result.get('claims', [])

    except Exception as e:
        print(f"⚠️  Claim extraction failed: {e}")
        # Fallback: Split by sentences
        import re
        sentences = re.split(r'[.!?]+', answer)
        return [s.strip() for s in sentences if len(s.strip()) > 20][:20]


def check_claim_support(
    claim: str,
    citations: List[Dict[str, Any]],
    model: str = "gpt-4o-mini"
) -> Dict[str, Any]:
    """Check if a single claim is supported by citations.

    Args:
        claim: Atomic factual claim to verify
        citations: List of citation dicts with 'content' field
        model: OpenAI model to use

    Returns:
        {
            'claim': str,
            'is_supported': bool,
            'supporting_citation_ids': List[int],
            'confidence': float,  # 0.0-1.0
            'explanation': str
        }
    """
    # Build citation context
    citation_text = ""
    for i, citation in enumerate(citations, 1):
        content = citation.get('content', '')[:500]  # Limit to 500 chars per citation
        citation_text += f"[{i}] {content}\n\n"

    prompt = f"""You are a technical documentation fact-checker. Determine if the CLAIM is EXPLICITLY supported by the CITATIONS.

CLAIM: {claim}

CITATIONS:
{citation_text}

Verification Rules:
1. The claim must be DIRECTLY stated or clearly implied in the citations
2. Do NOT use external knowledge - ONLY the citations provided
3. Technical details (numbers, versions, settings) must match exactly
4. If you're unsure or the claim is partially supported, mark as NOT SUPPORTED
5. Provide specific citation numbers that support the claim

Output JSON:
{{
    "is_supported": true/false,
    "supporting_citation_ids": [1, 2, ...],
    "confidence": 0.0-1.0,
    "explanation": "brief explanation of why supported/not supported"
}}
"""

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a strict fact-checker. Output only JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=200
        )

        result = json.loads(response.choices[0].message.content)
        result['claim'] = claim

        return result

    except Exception as e:
        print(f"⚠️  Claim verification failed: {e}")
        # Conservative fallback: mark as not supported
        return {
            'claim': claim,
            'is_supported': False,
            'supporting_citation_ids': [],
            'confidence': 0.0,
            'explanation': f'Verification error: {str(e)}'
        }


def verify_answer_grounding(
    question: str,
    answer: str,
    citations: List[Dict[str, Any]],
    model: str = "gpt-4o-mini",
    min_confidence: float = 0.85
) -> Dict[str, Any]:
    """Verify that answer is properly grounded in citations.

    Args:
        question: Original user question
        answer: LLM-generated answer to verify
        citations: List of citation dicts (must have 'content' field)
        model: OpenAI model to use for verification
        min_confidence: Minimum grounding confidence (0.0-1.0)

    Returns:
        {
            'is_grounded': bool,  # True if confidence >= min_confidence
            'confidence': float,  # 0.0-1.0 (% of claims supported)
            'total_claims': int,
            'supported_claims': int,
            'unsupported_claims': List[str],
            'verification_details': List[dict],
            'suggested_disclaimer': str or None
        }
    """
    if not citations:
        return {
            'is_grounded': False,
            'confidence': 0.0,
            'total_claims': 0,
            'supported_claims': 0,
            'unsupported_claims': [],
            'verification_details': [],
            'suggested_disclaimer': '⚠️ **Note**: No source citations were found for this answer.'
        }

    # Step 1: Extract claims from answer
    print(f"📋 Extracting claims from answer...")
    claims = extract_claims(answer, model)

    if not claims:
        # Short answer or extraction failed - assume grounded
        return {
            'is_grounded': True,
            'confidence': 1.0,
            'total_claims': 0,
            'supported_claims': 0,
            'unsupported_claims': [],
            'verification_details': [],
            'suggested_disclaimer': None
        }

    print(f"   ✓ Found {len(claims)} claims to verify")

    # Step 2: Verify each claim
    verification_results = []
    for i, claim in enumerate(claims, 1):
        print(f"   Checking claim {i}/{len(claims)}: {claim[:60]}...")
        result = check_claim_support(claim, citations, model)
        verification_results.append(result)

    # Step 3: Calculate grounding metrics
    supported = [r for r in verification_results if r.get('is_supported', False)]
    unsupported = [r for r in verification_results if not r.get('is_supported', False)]

    confidence = len(supported) / len(claims) if claims else 1.0
    is_grounded = confidence >= min_confidence

    # Step 4: Generate disclaimer if needed
    disclaimer = None
    if not is_grounded:
        unsupported_count = len(unsupported)
        if unsupported_count > 0:
            disclaimer = f"\n\n⚠️ **Verification Note**: {unsupported_count} claim{'s' if unsupported_count > 1 else ''} in this answer may not be fully supported by the retrieved documentation (grounding confidence: {confidence:.0%}). Please verify critical details against the source documents."

    result = {
        'is_grounded': is_grounded,
        'confidence': confidence,
        'total_claims': len(claims),
        'supported_claims': len(supported),
        'unsupported_claims': [r['claim'] for r in unsupported],
        'verification_details': verification_results,
        'suggested_disclaimer': disclaimer
    }

    # Log summary
    print(f"\n✅ Verification complete:")
    print(f"   • Total claims: {result['total_claims']}")
    print(f"   • Supported: {result['supported_claims']}")
    print(f"   • Unsupported: {len(result['unsupported_claims'])}")
    print(f"   • Confidence: {result['confidence']:.1%}")
    print(f"   • Grounded: {'✓ YES' if result['is_grounded'] else '✗ NO'}")

    return result


def generate_grounding_report(verification: Dict[str, Any]) -> str:
    """Generate human-readable grounding report.

    Args:
        verification: Output from verify_answer_grounding()

    Returns:
        Formatted text report
    """
    lines = []
    lines.append("=" * 80)
    lines.append("ANSWER GROUNDING REPORT")
    lines.append("=" * 80)
    lines.append(f"Overall Confidence: {verification['confidence']:.1%}")
    lines.append(f"Grounded: {'✓ YES' if verification['is_grounded'] else '✗ NO'}")
    lines.append(f"Claims Checked: {verification['total_claims']}")
    lines.append(f"Supported: {verification['supported_claims']}")
    lines.append(f"Unsupported: {len(verification['unsupported_claims'])}")
    lines.append("")

    if verification['unsupported_claims']:
        lines.append("⚠️  UNSUPPORTED CLAIMS:")
        for i, claim in enumerate(verification['unsupported_claims'], 1):
            lines.append(f"  {i}. {claim}")
        lines.append("")

    lines.append("=" * 80)

    return "\n".join(lines)


# Lightweight version for production use
def quick_verify(
    answer: str,
    citations: List[Dict[str, Any]],
    model: str = "gpt-4o-mini"
) -> Tuple[bool, float, str]:
    """Quick verification for production (single LLM call).

    Args:
        answer: LLM-generated answer
        citations: List of citations with 'content' field
        model: OpenAI model to use

    Returns:
        (is_grounded, confidence, disclaimer_text)
    """
    if not citations:
        return False, 0.0, "⚠️ No source citations available."

    citation_text = "\n\n".join([
        f"[{i+1}] {c.get('content', '')[:400]}"
        for i, c in enumerate(citations[:5])
    ])

    prompt = f"""Verify if this ANSWER is well-grounded in the CITATIONS.

ANSWER:
{answer[:1500]}

CITATIONS:
{citation_text}

Check:
1. Are factual claims supported by citations?
2. Are technical details (numbers, versions) accurate?
3. Is the answer making unsupported assumptions?

Output JSON:
{{
    "is_grounded": true/false,
    "confidence": 0.0-1.0,
    "issues": "brief description of any issues, or empty string if none"
}}
"""

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=150
        )

        result = json.loads(response.choices[0].message.content)

        is_grounded = result.get('is_grounded', False)
        confidence = result.get('confidence', 0.0)
        issues = result.get('issues', '')

        disclaimer = ""
        if not is_grounded and issues:
            disclaimer = f"\n\n⚠️ **Verification Note**: {issues} (confidence: {confidence:.0%})"

        return is_grounded, confidence, disclaimer

    except Exception as e:
        print(f"⚠️  Quick verification failed: {e}")
        return True, 1.0, ""  # Optimistic fallback


if __name__ == "__main__":
    # Test the verification system
    test_answer = """System Database is the central data repository in Niagara 4.
    It uses the Fox protocol on port 1911 to sync data between stations.
    Sync happens every 30 seconds by default, but this can be configured."""

    test_citations = [
        {"content": "System Database provides centralized data storage across the Niagara network."},
        {"content": "The Fox protocol is used for inter-station communication in System Database."},
        {"content": "Default sync interval is 60 seconds, configurable via the SystemDB config."}
    ]

    result = verify_answer_grounding(
        question="How does System Database work?",
        answer=test_answer,
        citations=test_citations
    )

    print("\n" + generate_grounding_report(result))
