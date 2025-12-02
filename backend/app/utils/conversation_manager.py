"""Conversation manager for chat history processing.

Extracts context from conversation history to improve retrieval and responses.
"""
from typing import List, Dict, Any
import re


def extract_conversation_context(chat_history: List[Dict[str, str]]) -> Dict[str, Any]:
    """Extract useful context from chat history for retrieval boost.
    
    Args:
        chat_history: List of messages [{"role": "user/assistant", "content": "..."}]
        
    Returns:
        Dict with extracted context:
        {
            'is_followup': bool,
            'entities': List[str],  # Technical terms mentioned
            'topics': List[str],  # Discussed topics
            'last_user_question': str
        }
    """
    if not chat_history or len(chat_history) == 0:
        return {
            'is_followup': False,
            'entities': [],
            'topics': [],
            'last_user_question': ''
        }
    
    # Extract entities (technical terms) from conversation
    entities = set()
    topics = set()
    
    for msg in chat_history:
        content = msg.get('content', '')
        
        # Extract technical entities
        # Look for patterns like: JACE, System Database, BACnet, etc.
        technical_terms = re.findall(r'\b(?:[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*|[A-Z]{2,})\b', content)
        entities.update([t.lower() for t in technical_terms if len(t) > 2])
        
        # Extract common BAS/HVAC terms
        bas_terms = [
            'system database', 'system db', 'multi-tier', 'supervisor', 'jace',
            'station', 'px', 'graphics', 'navigation', 'tag dictionary',
            'bacnet', 'modbus', 'lon', 'n2', 'provisioning', 'backup',
            'alarm', 'fault', 'schedule', 'sequence', 'ahu', 'vav', 'fcu',
            'chiller', 'boiler', 'point', 'control', 'network', 'protocol'
        ]
        for term in bas_terms:
            if term in content.lower():
                entities.add(term)
    
    # Detect if current question is a follow-up
    is_followup = False
    last_user_question = ''
    
    # Get last user message
    user_messages = [m for m in chat_history if m.get('role') == 'user']
    if user_messages:
        last_user_question = user_messages[-1].get('content', '')
        
        # Follow-up indicators
        followup_patterns = [
            r'^(what about|how about|and|also|additionally)',
            r'^(can you|could you|please)',
            r'\b(that|this|it|they|them)\b',  # Pronouns referring to previous context
            r'^(more|further|additional)',
        ]
        
        for pattern in followup_patterns:
            if re.search(pattern, last_user_question.lower()):
                is_followup = True
                break
        
        # Short questions often mean follow-ups
        if len(last_user_question.split()) < 8 and len(chat_history) > 2:
            is_followup = True
    
    return {
        'is_followup': is_followup,
        'entities': list(entities)[:20],  # Limit to top 20
        'topics': list(topics),
        'last_user_question': last_user_question
    }


def enhance_query_with_context(
    question: str,
    conversation_context: Dict[str, Any]
) -> str:
    """Enhance query with conversation context for better retrieval.
    
    Args:
        question: Original user question
        conversation_context: Context from extract_conversation_context()
        
    Returns:
        Enhanced query string
    """
    if not conversation_context['is_followup']:
        return question
    
    # For follow-ups, append relevant entities for context
    entities = conversation_context['entities'][:5]  # Top 5 most relevant
    
    if entities:
        # Add entities as context without changing the question structure
        context_hint = ' '.join(entities)
        return f"{question} {context_hint}"
    
    return question


def should_expand_context_window(conversation_context: Dict[str, Any]) -> bool:
    """Determine if we should expand context window for this query.
    
    Args:
        conversation_context: Context from extract_conversation_context()
        
    Returns:
        True if we should expand context window (more chunks, wider sibling window)
    """
    # Expand context for follow-ups to provide continuity
    if conversation_context['is_followup']:
        return True
    
    # Expand if many entities are in play (complex discussion)
    if len(conversation_context['entities']) > 10:
        return True
    
    return False


def format_chat_history_for_llm(
    chat_history: List[Dict[str, str]],
    max_messages: int = 4
) -> List[Dict[str, str]]:
    """Format chat history for LLM consumption.
    
    Args:
        chat_history: Raw chat history
        max_messages: Maximum number of message pairs to include
        
    Returns:
        Formatted chat history (last N messages, truncated if needed)
    """
    if not chat_history or len(chat_history) == 0:
        return []
    
    # Get last N messages
    recent_history = chat_history[-max_messages:]
    
    # Truncate very long messages
    formatted = []
    for msg in recent_history:
        content = msg.get('content', '')
        if len(content) > 500:
            content = content[:497] + "..."
        
        formatted.append({
            'role': msg['role'],
            'content': content
        })
    
    return formatted
