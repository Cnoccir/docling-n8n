"""Adaptive retrieval system that adjusts parameters based on query complexity.

Optimizes cost and performance by:
- Using fewer chunks for simple queries
- Expanding context for complex/comparison queries
- Adjusting context window based on question type
"""
from typing import Tuple, List
import re


def count_technical_entities(question: str) -> int:
    """Count distinct technical entities mentioned in question.

    Args:
        question: User's question

    Returns:
        Number of distinct technical entities (capitalized terms, acronyms)
    """
    # Extract potential entities: Capitalized words, acronyms, technical terms
    entities = set()

    # Find acronyms (2+ capital letters)
    acronyms = re.findall(r'\b[A-Z]{2,}\b', question)
    entities.update(acronyms)

    # Find capitalized terms (but not sentence starts)
    capitalized = re.findall(r'(?<!^)(?<!\. )\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', question)
    entities.update(capitalized)

    return len(entities)


def detect_query_complexity(question: str, query_type: str) -> str:
    """Classify query complexity based on structure and content.

    Args:
        question: User's question
        query_type: Query type from classifier (definition, comparison, etc.)

    Returns:
        Complexity level: 'simple', 'moderate', 'complex'
    """
    # Complexity indicators
    word_count = len(question.split())
    entity_count = count_technical_entities(question)

    # Check for complexity patterns
    has_multiple_questions = question.count('?') > 1
    has_compound_clauses = any(word in question.lower() for word in ['and', 'or', 'but', 'also'])
    has_comparison = any(word in question.lower() for word in ['compare', 'difference', 'vs', 'versus', 'better', 'which'])
    has_multi_step = any(word in question.lower() for word in ['step', 'procedure', 'process', 'sequence'])

    # Simple queries
    if query_type == 'definition' and word_count < 10 and entity_count <= 1:
        return 'simple'

    if word_count < 8 and entity_count <= 1 and not has_compound_clauses:
        return 'simple'

    # Complex queries
    if has_multiple_questions or entity_count >= 3:
        return 'complex'

    if query_type in ['comparison', 'design', 'troubleshooting'] and word_count > 15:
        return 'complex'

    if has_comparison and entity_count >= 2:
        return 'complex'

    if has_multi_step and word_count > 12:
        return 'complex'

    # Moderate (default)
    return 'moderate'


def adaptive_top_k(question: str, query_type: str, complexity: str = None) -> int:
    """Determine optimal top_k based on query characteristics.

    Args:
        question: User's question
        query_type: Query type from classifier
        complexity: Pre-computed complexity level (optional)

    Returns:
        Optimal top_k value (2-10)
    """
    if complexity is None:
        complexity = detect_query_complexity(question, query_type)

    # Base top_k by complexity
    base_k = {
        'simple': 3,
        'moderate': 5,
        'complex': 7
    }[complexity]

    # Adjustments by query type
    if query_type == 'comparison':
        # Comparisons need sources for both sides
        return min(base_k + 2, 10)

    if query_type == 'troubleshooting':
        # Troubleshooting may need multiple diagnostic paths
        return min(base_k + 1, 8)

    if query_type == 'design':
        # Design questions benefit from diverse perspectives
        return min(base_k + 2, 10)

    if query_type == 'definition' and complexity == 'simple':
        # Simple definitions don't need many sources
        return 2

    return base_k


def adaptive_context_window(question: str, query_type: str, complexity: str = None) -> int:
    """Determine optimal context window (surrounding chunks) based on query.

    Args:
        question: User's question
        query_type: Query type from classifier
        complexity: Pre-computed complexity level (optional)

    Returns:
        Optimal context window size (0-4 chunks before/after)
    """
    if complexity is None:
        complexity = detect_query_complexity(question, query_type)

    # Base window by complexity
    base_window = {
        'simple': 1,      # ±1 chunk
        'moderate': 2,    # ±2 chunks
        'complex': 3      # ±3 chunks
    }[complexity]

    # Adjustments by query type
    if query_type == 'procedural':
        # Procedures need sequential context
        return min(base_window + 1, 4)

    if query_type == 'troubleshooting':
        # Troubleshooting needs surrounding context
        return min(base_window + 1, 4)

    if query_type == 'definition' and complexity == 'simple':
        # Definitions often self-contained
        return 1

    return base_window


def adaptive_retrieval_params(
    question: str,
    query_type: str,
    is_followup: bool = False,
    base_top_k: int = 5,
    base_window: int = 2
) -> Tuple[int, int, str]:
    """Compute all adaptive retrieval parameters.

    Args:
        question: User's question
        query_type: Query type from classifier
        is_followup: Whether this is a follow-up question
        base_top_k: Default top_k if no adaptation
        base_window: Default context window if no adaptation

    Returns:
        (top_k, context_window, complexity_level)
    """
    # Detect complexity
    complexity = detect_query_complexity(question, query_type)

    # Compute adaptive parameters
    top_k = adaptive_top_k(question, query_type, complexity)
    context_window = adaptive_context_window(question, query_type, complexity)

    # Boost for follow-ups (as per existing logic)
    if is_followup:
        top_k = min(top_k + 2, 10)
        context_window = min(context_window + 1, 4)

    return top_k, context_window, complexity


def estimate_token_savings(complexity: str, top_k: int, context_window: int) -> float:
    """Estimate token savings from adaptive retrieval.

    Args:
        complexity: Query complexity level
        top_k: Computed top_k
        context_window: Computed context window

    Returns:
        Estimated % token reduction vs baseline (5 chunks, window=2)
    """
    # Baseline: 5 chunks, window=2
    # Each chunk ~1200 chars = ~300 tokens
    # Context: 2 before + 2 after = 4 additional chunks per golden chunk
    # Total baseline: 5 golden + (5 * 4 context) = 25 chunks = 7500 tokens

    baseline_chunks = 5 + (5 * 2 * 2)  # 5 golden + (5 * 4 context)

    # Actual: top_k golden + (top_k * context_window * 2) context
    actual_chunks = top_k + (top_k * context_window * 2)

    reduction = (baseline_chunks - actual_chunks) / baseline_chunks

    return max(0.0, reduction)


def explain_retrieval_strategy(
    question: str,
    query_type: str,
    top_k: int,
    context_window: int,
    complexity: str
) -> str:
    """Generate human-readable explanation of retrieval strategy.

    Args:
        question: User's question
        query_type: Query type
        top_k: Computed top_k
        context_window: Computed context window
        complexity: Complexity level

    Returns:
        Explanation string
    """
    savings = estimate_token_savings(complexity, top_k, context_window)

    explanation = f"""
🎯 Adaptive Retrieval Strategy:
   • Complexity: {complexity}
   • Query Type: {query_type}
   • Top-K: {top_k} chunks
   • Context Window: ±{context_window} chunks
   • Estimated Token Savings: {savings:.1%} vs baseline
"""

    # Add reasoning
    if complexity == 'simple':
        explanation += "   • Reasoning: Simple query → fewer sources needed\n"
    elif complexity == 'complex':
        explanation += "   • Reasoning: Complex query → broader context needed\n"

    if query_type == 'comparison':
        explanation += "   • Reasoning: Comparison → need sources for multiple topics\n"
    elif query_type == 'definition':
        explanation += "   • Reasoning: Definition → focused retrieval sufficient\n"

    return explanation


def needs_multi_hop(question: str, query_type: str, complexity: str) -> bool:
    """Determine if query needs multi-hop reasoning.

    Multi-hop is needed when:
    - Comparison queries (need to retrieve info about each item separately)
    - Complex queries with multiple entities
    - Questions with multiple sub-questions

    Args:
        question: User's question
        query_type: Query type
        complexity: Complexity level

    Returns:
        True if multi-hop reasoning recommended
    """
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
        'and then', 'after that', 'first.*then', 'step 1.*step 2',
        'difference between.*and', 'compare.*to', 'versus'
    ]

    question_lower = question.lower()
    if any(re.search(pattern, question_lower) for pattern in multi_part_indicators):
        return True

    return False


if __name__ == "__main__":
    # Test cases
    test_cases = [
        ("What is System Database?", "definition"),
        ("How do I configure VFD parameters for variable speed control?", "procedural"),
        ("Compare System Database vs traditional point-to-point and explain which to use for multi-tier", "comparison"),
        ("My JACE is showing alarm 'low water fault' and pump not starting", "troubleshooting"),
        ("Design a multi-tier architecture with 3 supervisors and explain graphics strategy", "design"),
    ]

    print("=" * 80)
    print("ADAPTIVE RETRIEVAL TEST")
    print("=" * 80)

    for question, qtype in test_cases:
        print(f"\nQuestion: {question[:70]}...")
        print(f"Type: {qtype}")

        top_k, window, complexity = adaptive_retrieval_params(question, qtype)

        print(explain_retrieval_strategy(question, qtype, top_k, window, complexity))

        if needs_multi_hop(question, qtype, complexity):
            print("   ⚠️  MULTI-HOP REASONING RECOMMENDED")
