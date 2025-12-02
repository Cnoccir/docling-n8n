"""Enhanced conversation manager with sliding window summaries.

Extends the existing conversation_manager.py with:
- Long conversation summarization
- Sliding window with summary compression
- Better entity tracking across long sessions
"""
from typing import List, Dict, Any, Tuple, Optional
import os
from openai import OpenAI

openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def build_conversation_summary(
    chat_history: List[Dict[str, str]],
    model: str = "gpt-4o-mini"
) -> str:
    """Summarize older conversation messages for context compression.

    Args:
        chat_history: Full chat history
        model: OpenAI model to use for summarization

    Returns:
        Concise summary of the conversation (2-3 sentences)
    """
    if len(chat_history) < 6:
        return ""  # No need to summarize short conversations

    # Summarize everything except last 4 messages
    messages_to_summarize = chat_history[:-4]

    if not messages_to_summarize:
        return ""

    conversation_text = "\n".join([
        f"{msg['role'].upper()}: {msg['content'][:300]}"
        for msg in messages_to_summarize
    ])

    prompt = f"""Summarize this technical conversation in 2-3 sentences. Focus on:
1. User's main goal or task
2. Key technical entities discussed (systems, components, settings)
3. Important decisions made or conclusions reached

Conversation:
{conversation_text}

Concise summary (2-3 sentences):"""

    try:
        response = get_openai_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a technical conversation summarizer. Be concise and focus on facts."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.2
        )

        summary = response.choices[0].message.content.strip()
        print(f"   ✓ Generated conversation summary ({len(summary)} chars)")
        return summary

    except Exception as e:
        print(f"⚠️  Conversation summarization failed: {e}")
        return ""


def format_chat_history_with_summary(
    chat_history: List[Dict[str, str]],
    max_recent_messages: int = 4,
    model: str = "gpt-4o-mini"
) -> Tuple[Optional[str], List[Dict[str, str]]]:
    """Format chat history with summary for long conversations.

    Uses sliding window approach:
    - Long conversations (>4 messages): Generate summary + keep last 4
    - Short conversations (≤4 messages): Return all messages

    Args:
        chat_history: Full chat history
        max_recent_messages: Number of recent messages to keep verbatim
        model: OpenAI model for summarization

    Returns:
        (summary_text, recent_messages)
        - summary_text: None for short convos, summary string for long convos
        - recent_messages: Last N messages to include verbatim
    """
    if not chat_history or len(chat_history) <= max_recent_messages:
        return None, chat_history

    # Generate summary of older messages
    summary = build_conversation_summary(chat_history, model)

    # Keep recent messages verbatim
    recent_messages = chat_history[-max_recent_messages:]

    return summary, recent_messages


def extract_key_entities_from_history(
    chat_history: List[Dict[str, str]],
    max_entities: int = 10
) -> List[str]:
    """Extract key technical entities from conversation history.

    Args:
        chat_history: Chat history messages
        max_entities: Maximum entities to return

    Returns:
        List of key technical entities (most frequently mentioned)
    """
    import re
    from collections import Counter

    entity_counts = Counter()

    # Combine all conversation text
    all_text = " ".join([msg.get('content', '') for msg in chat_history])

    # Extract technical terms
    technical_terms = re.findall(r'\b(?:[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*|[A-Z]{2,})\b', all_text)
    entity_counts.update([t.lower() for t in technical_terms if len(t) > 2])

    # Extract known BAS/HVAC terms
    bas_terms = [
        'system database', 'system db', 'multi-tier', 'supervisor', 'jace',
        'station', 'px', 'graphics', 'navigation', 'tag dictionary',
        'bacnet', 'modbus', 'lon', 'n2', 'provisioning', 'backup',
        'alarm', 'fault', 'schedule', 'sequence', 'ahu', 'vav', 'fcu',
        'chiller', 'boiler', 'point', 'control', 'network', 'protocol',
        'fox', 'niagara', 'tridium', 'workbench', 'web profile'
    ]

    for term in bas_terms:
        count = all_text.lower().count(term)
        if count > 0:
            entity_counts[term] = count

    # Return most common entities
    return [entity for entity, count in entity_counts.most_common(max_entities)]


def build_conversation_context_enhanced(
    chat_history: List[Dict[str, str]],
    current_question: str
) -> Dict[str, Any]:
    """Build enhanced conversation context including summary and entities.

    Args:
        chat_history: Full chat history
        current_question: Current user question

    Returns:
        Enhanced context dict with summary, entities, and metadata
    """
    from backend.app.utils.conversation_manager import extract_conversation_context

    # Use existing context extraction
    base_context = extract_conversation_context(chat_history)

    # Add key entities from full history (better than just last few messages)
    key_entities = extract_key_entities_from_history(chat_history, max_entities=10)

    # Generate summary if conversation is long
    summary = None
    if len(chat_history) > 6:
        summary = build_conversation_summary(chat_history)

    # Enhanced context
    enhanced_context = {
        **base_context,
        'key_entities': key_entities,
        'conversation_summary': summary,
        'message_count': len(chat_history),
        'is_long_conversation': len(chat_history) > 6
    }

    return enhanced_context


def should_use_conversation_summary(chat_history: List[Dict[str, str]]) -> bool:
    """Determine if conversation summary should be used.

    Args:
        chat_history: Chat history

    Returns:
        True if summary recommended
    """
    # Use summary for conversations longer than 6 messages
    return len(chat_history) > 6


def get_conversation_stats(chat_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """Get conversation statistics for monitoring.

    Args:
        chat_history: Chat history

    Returns:
        Stats dict
    """
    user_messages = [m for m in chat_history if m.get('role') == 'user']
    assistant_messages = [m for m in chat_history if m.get('role') == 'assistant']

    avg_user_length = sum(len(m.get('content', '')) for m in user_messages) / max(len(user_messages), 1)
    avg_assistant_length = sum(len(m.get('content', '')) for m in assistant_messages) / max(len(assistant_messages), 1)

    return {
        'total_messages': len(chat_history),
        'user_messages': len(user_messages),
        'assistant_messages': len(assistant_messages),
        'avg_user_msg_length': int(avg_user_length),
        'avg_assistant_msg_length': int(avg_assistant_length),
        'conversation_length_chars': sum(len(m.get('content', '')) for m in chat_history)
    }


if __name__ == "__main__":
    # Test conversation summarization
    test_history = [
        {"role": "user", "content": "How do I configure System Database?"},
        {"role": "assistant", "content": "System Database is configured via the SystemDB station..."},
        {"role": "user", "content": "What about multi-tier setup?"},
        {"role": "assistant", "content": "For multi-tier, you'll use Enterprise Supervisors..."},
        {"role": "user", "content": "How do I configure graphics?"},
        {"role": "assistant", "content": "Graphics are configured using PX views..."},
        {"role": "user", "content": "What about tag dictionaries?"},
        {"role": "assistant", "content": "Tag dictionaries map point names..."},
        {"role": "user", "content": "Tell me more about navigation"},
    ]

    print("Testing Conversation Enhancement:")
    print("=" * 60)

    # Test summary generation
    summary, recent = format_chat_history_with_summary(test_history)

    if summary:
        print(f"\nSummary: {summary}")
        print(f"\nRecent messages: {len(recent)}")

    # Test entity extraction
    entities = extract_key_entities_from_history(test_history)
    print(f"\nKey entities: {entities}")

    # Test stats
    stats = get_conversation_stats(test_history)
    print(f"\nStats: {stats}")
