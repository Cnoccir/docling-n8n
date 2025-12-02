"""Multi-hop reasoning system for complex queries.

Handles queries that require multiple retrieval steps:
- Comparison queries (retrieve info about each item)
- Multi-entity queries (retrieve context for each entity)
- Sequential questions (answer sub-questions in order)
"""
from typing import List, Dict, Any, Tuple
from openai import OpenAI
import os
import json

openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def decompose_query(question: str, model: str = "gpt-4o-mini") -> List[str]:
    """Break complex question into sequential sub-questions.

    Args:
        question: Complex user question
        model: OpenAI model to use

    Returns:
        List of 2-4 sub-questions that can be answered sequentially

    Example:
        Input: "How do I configure System Database for multi-tier and what graphics should I use?"
        Output: [
            "How is System Database configured in multi-tier architecture?",
            "What graphics options are available for multi-tier systems?",
            "How do graphics integrate with System Database in multi-tier setup?"
        ]
    """
    prompt = f"""Break this complex technical question into 2-4 simpler sub-questions that can be answered sequentially.

Original Question: {question}

Rules:
1. Each sub-question should be self-contained and answerable independently
2. Sub-questions should follow a logical order
3. Focus on the key aspects of the original question
4. Avoid redundancy between sub-questions
5. Maximum 4 sub-questions

Output JSON:
{{
    "sub_questions": ["sub-question 1", "sub-question 2", ...]
}}
"""

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a technical question decomposer. Output only JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            max_tokens=300
        )

        result = json.loads(response.choices[0].message.content)
        sub_questions = result.get('sub_questions', [])

        # Limit to 4 sub-questions
        return sub_questions[:4]

    except Exception as e:
        print(f"⚠️  Query decomposition failed: {e}")
        # Fallback: return original question
        return [question]


def needs_multi_hop_reasoning(
    question: str,
    query_type: str,
    complexity: str
) -> bool:
    """Determine if query needs multi-hop reasoning.

    Multi-hop is needed when:
    - Comparison queries (need to retrieve info about each item separately)
    - Complex queries with multiple entities (3+)
    - Questions with multiple sub-questions
    - Explicit multi-part questions

    Args:
        question: User's question
        query_type: Query type from classifier
        complexity: Complexity level from adaptive_retrieval

    Returns:
        True if multi-hop recommended
    """
    import re
    from backend.app.utils.adaptive_retrieval import count_technical_entities

    # Comparison queries almost always need multi-hop
    if query_type == 'comparison':
        return True

    # Complex queries with 3+ entities
    if complexity == 'complex' and count_technical_entities(question) >= 3:
        return True

    # Multiple question marks
    if question.count('?') > 1:
        return True

    # Explicit multi-part questions
    multi_part_indicators = [
        r'and then', r'after that', r'first.*then', r'step.*step',
        r'difference between.*and', r'compare.*to', r'versus',
        r'what about.*and', r'how.*and.*why'
    ]

    question_lower = question.lower()
    if any(re.search(pattern, question_lower) for pattern in multi_part_indicators):
        return True

    return False


def multi_hop_retrieve(
    question: str,
    doc_id: str,
    db_client,
    embedding_gen,
    query_type: str = 'general',
    max_hops: int = 3,
    chunks_per_hop: int = 3
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Perform multi-hop retrieval for complex questions.

    Args:
        question: User's question
        doc_id: Document ID
        db_client: DatabaseClient instance
        embedding_gen: EmbeddingGenerator instance
        query_type: Query type from classifier
        max_hops: Maximum number of retrieval hops
        chunks_per_hop: Chunks to retrieve per hop

    Returns:
        (all_unique_chunks, sub_questions_asked)
    """
    print(f"\n🔍 Multi-hop retrieval for: {question[:60]}...")

    # Step 1: Decompose query into sub-questions
    sub_questions = decompose_query(question)

    if len(sub_questions) <= 1:
        # Simple question - fall back to single-shot retrieval
        print("   ℹ️  Only 1 sub-question, using single-shot retrieval")
        embedding = embedding_gen.generate_embeddings([question])[0]
        results = db_client.search_chunks_hybrid(
            query_embedding=embedding,
            query_text=question,
            doc_id=doc_id,
            top_k=5
        )
        return results, [question]

    print(f"   ✓ Decomposed into {len(sub_questions)} sub-questions")

    # Step 2: Retrieve for each sub-question
    all_contexts = []
    hop_summaries = []

    for i, sub_q in enumerate(sub_questions[:max_hops], 1):
        print(f"\n   🔍 Hop {i}/{min(len(sub_questions), max_hops)}: {sub_q[:50]}...")

        # Generate embedding for this sub-question
        embedding = embedding_gen.generate_embeddings([sub_q])[0]

        # Retrieve chunks for this sub-question
        results = db_client.search_chunks_hybrid(
            query_embedding=embedding,
            query_text=sub_q,
            doc_id=doc_id,
            semantic_weight=0.5,
            keyword_weight=0.5,
            top_k=chunks_per_hop
        )

        print(f"      ✓ Retrieved {len(results)} chunks")

        all_contexts.extend(results)

        # Summarize this hop's findings for next hop context
        if results:
            hop_summary = summarize_hop_findings(sub_q, results)
            hop_summaries.append(hop_summary)

    # Step 3: Deduplicate chunks by ID
    unique_chunks = {chunk['id']: chunk for chunk in all_contexts}.values()
    unique_list = list(unique_chunks)

    print(f"\n   ✅ Multi-hop complete: {len(unique_list)} unique chunks from {len(all_contexts)} retrievals")

    return unique_list, sub_questions


def summarize_hop_findings(
    sub_question: str,
    results: List[Dict[str, Any]],
    model: str = "gpt-4o-mini"
) -> str:
    """Summarize findings from a single hop for context in next hop.

    Args:
        sub_question: The sub-question for this hop
        results: Retrieved chunks
        model: OpenAI model

    Returns:
        1-2 sentence summary
    """
    # Combine top results
    content = "\n".join([r.get('content', '')[:200] for r in results[:3]])

    prompt = f"""Summarize the key finding from these chunks for this question in 1-2 sentences.

Question: {sub_question}

Content:
{content}

Brief summary (1-2 sentences):"""

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.2
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"   ⚠️  Hop summarization failed: {e}")
        return f"Retrieved {len(results)} chunks for: {sub_question}"


def synthesize_multi_hop_answer(
    question: str,
    sub_questions: List[str],
    all_chunks: List[Dict[str, Any]],
    model: str = "gpt-4o-mini"
) -> str:
    """Synthesize final answer from multi-hop retrieval results.

    Args:
        question: Original complex question
        sub_questions: Sub-questions asked during multi-hop
        all_chunks: All retrieved chunks from all hops
        model: OpenAI model

    Returns:
        Synthesized answer
    """
    # Build context from all hops
    context_parts = []

    for i, chunk in enumerate(all_chunks[:10], 1):  # Limit to top 10
        context_parts.append(f"[{i}] (Page {chunk.get('page_number', '?')}): {chunk.get('content', '')[:400]}")

    context = "\n\n".join(context_parts)

    # List sub-questions for context
    sub_q_list = "\n".join([f"  {i+1}. {sq}" for i, sq in enumerate(sub_questions)])

    prompt = f"""Answer this complex question using the retrieved context.

Original Question: {question}

Sub-questions explored:
{sub_q_list}

Retrieved Context:
{context}

Provide a comprehensive answer that addresses all aspects of the original question.
Cite sources using [N] notation.

Answer:"""

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a technical expert synthesizing information from multiple sources."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        print(f"⚠️  Answer synthesis failed: {e}")
        return "Unable to synthesize answer from multi-hop retrieval."


if __name__ == "__main__":
    # Test query decomposition
    test_queries = [
        "What's the difference between System Database and traditional point-to-point, and which should I use for multi-tier?",
        "How do I configure graphics for multi-tier and what are the best practices?",
        "Compare AHU vs VAV control sequences and explain when to use each",
    ]

    print("Multi-Hop Query Decomposition Test")
    print("=" * 80)

    for q in test_queries:
        print(f"\nOriginal: {q}")
        sub_qs = decompose_query(q)
        print(f"Sub-questions:")
        for i, sq in enumerate(sub_qs, 1):
            print(f"  {i}. {sq}")
