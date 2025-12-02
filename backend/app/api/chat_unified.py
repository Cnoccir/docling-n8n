"""Unified chat API - queries across PDFs, YouTube videos, and other sources."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Literal, Union
import sys
from pathlib import Path
import os
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient
from utils.embeddings import EmbeddingGenerator
from app.utils.cost_tracker import CostTracker

router = APIRouter()

# OpenAI client
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


class ChatHistoryMessage(BaseModel):
    """Chat history message for conversation context."""
    role: Literal['user', 'assistant']
    content: str


class UnifiedChatRequest(BaseModel):
    """Multi-source chat request."""
    question: str
    source_types: List[Literal['pdf', 'youtube', 'all']] = ['all']
    doc_ids: List[str] = []  # Specific documents, or empty = search all
    top_k_per_source: int = 5
    use_images: bool = False  # Include screenshots/images in context
    semantic_weight: float = 0.5
    keyword_weight: float = 0.5
    chat_history: List[ChatHistoryMessage] = []  # Conversation history for follow-ups


class PDFCitation(BaseModel):
    """Citation from PDF document."""
    source_type: Literal['pdf'] = 'pdf'
    doc_id: str
    doc_title: str
    chunk_id: str
    content: str
    page_number: int
    section_path: List[str]
    similarity_score: float


class YouTubeCitation(BaseModel):
    """Citation from YouTube video."""
    source_type: Literal['youtube'] = 'youtube'
    doc_id: str
    doc_title: str
    chunk_id: str
    content: str
    timestamp: float
    timestamp_formatted: str
    video_url: str
    section_path: List[str]
    similarity_score: float
    thumbnail_url: Optional[str] = None


class RelatedImage(BaseModel):
    """Image related to the answer."""
    url: str
    caption: Optional[str] = None
    image_type: Optional[str] = None
    page_number: Optional[int] = None
    timestamp: Optional[float] = None


class UnifiedChatResponse(BaseModel):
    """Unified chat response with multi-source citations."""
    answer: str
    citations: List[Union[PDFCitation, YouTubeCitation]]
    sources_searched: List[str]
    total_sources_found: int
    model_used: str
    tokens_used: int
    related_images: List[RelatedImage] = []  # Images relevant to the answer
    follow_up_suggestions: List[str] = []  # Suggested follow-up questions


def format_timestamp(seconds: float) -> str:
    """Format timestamp as MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


def generate_follow_up_suggestions(question: str, answer: str, query_type: str, citations: list) -> List[str]:
    """Generate contextual follow-up suggestions based on the query and response."""
    suggestions = []
    question_lower = question.lower()
    
    # Base suggestions by query type
    if query_type == 'definition' or 'what is' in question_lower or 'what are' in question_lower:
        suggestions.append("How do I configure this?")
        suggestions.append("Show me a step-by-step setup procedure")
        suggestions.append("What are common issues with this?")
    
    elif query_type == 'example' or 'how to' in question_lower or 'how do' in question_lower:
        suggestions.append("What if this doesn't work?")
        suggestions.append("Are there alternative approaches?")
        suggestions.append("Show me the verification steps")
    
    elif query_type == 'troubleshooting' or any(w in question_lower for w in ['error', 'issue', 'problem', 'not working']):
        suggestions.append("What are other possible causes?")
        suggestions.append("How do I prevent this in the future?")
        suggestions.append("Show me the diagnostic steps")
    
    elif query_type == 'comparison' or 'vs' in question_lower or 'difference' in question_lower:
        suggestions.append("Which one should I use for my setup?")
        suggestions.append("How do I migrate from one to the other?")
        suggestions.append("What are the performance implications?")
    
    else:
        # General follow-ups
        suggestions.append("Can you show me the implementation steps?")
        suggestions.append("What related topics should I know about?")
        suggestions.append("Are there any common pitfalls?")
    
    # Add citation-based suggestions if we have specific sources
    if citations:
        # Get unique document titles
        doc_titles = list(set(c.doc_title for c in citations[:3] if hasattr(c, 'doc_title')))
        if doc_titles:
            suggestions.append(f"Tell me more from {doc_titles[0][:40]}...")
    
    # Limit to 3 suggestions
    return suggestions[:3]


def detect_document_type(doc_title: str, content_sample: str = "") -> str:
    """Detect if document is technical, prose, or mixed based on indicators."""
    technical_indicators = [
        'api', 'spec', 'specification', 'reference', 'sdk', 'protocol',
        'configuration', 'config', 'installation', 'setup', 'troubleshooting',
        'debug', 'error', 'guide', 'manual', 'documentation', 'technical',
        'system', 'architecture', 'design', 'implementation', 'code',
        'programming', 'software', 'hardware', 'network', 'database'
    ]

    title_lower = doc_title.lower()

    # Check title for technical indicators
    technical_score = sum(1 for indicator in technical_indicators if indicator in title_lower)

    # Check content sample if provided
    if content_sample:
        content_lower = content_sample.lower()
        technical_score += sum(1 for indicator in technical_indicators if indicator in content_lower)

    # Scoring: 3+ indicators = technical, 1-2 = mixed, 0 = prose
    if technical_score >= 3:
        return 'technical'
    elif technical_score >= 1:
        return 'mixed'
    else:
        return 'prose'


def classify_query_type(question: str) -> str:
    """Classify query type to optimize retrieval strategy."""
    question_lower = question.lower()

    # Definition queries
    if any(q in question_lower for q in ['what is', 'what are', 'define', 'explain', 'meaning of', 'definition']):
        return 'definition'

    # Example/How-to queries
    if any(q in question_lower for q in ['example', 'how to', 'how do', 'how can', 'show me', 'demo', 'tutorial']):
        return 'example'

    # Comparison queries
    if any(q in question_lower for q in ['compare', 'comparison', 'difference', 'vs', 'versus', 'better', 'which']):
        return 'comparison'

    # Troubleshooting queries
    if any(q in question_lower for q in ['error', 'fix', 'debug', 'issue', 'problem', 'not working', 'failed', 'troubleshoot']):
        return 'troubleshooting'

    # Reference queries (spec lookups)
    if any(q in question_lower for q in ['default', 'spec', 'parameter', 'argument', 'return', 'value', 'setting']):
        return 'reference'

    return 'general'


def determine_optimal_weights(doc_type: str, query_type: str) -> tuple[float, float]:
    """Determine optimal semantic/keyword weights based on document and query type."""

    # Baseline weights by document type
    if doc_type == 'technical':
        # Technical docs need precise keyword matching
        base_semantic = 0.35
        base_keyword = 0.65
    elif doc_type == 'prose':
        # Prose benefits from semantic understanding
        base_semantic = 0.6
        base_keyword = 0.4
    else:  # 'mixed'
        base_semantic = 0.5
        base_keyword = 0.5

    # Adjust based on query type
    if query_type == 'reference':
        # Reference queries need exact term matching
        semantic = base_semantic - 0.1
        keyword = base_keyword + 0.1
    elif query_type == 'troubleshooting':
        # Error queries need precise error codes/messages
        semantic = base_semantic - 0.05
        keyword = base_keyword + 0.05
    elif query_type == 'definition':
        # Definitions benefit from both semantic and keyword
        semantic = base_semantic + 0.05
        keyword = base_keyword - 0.05
    else:
        semantic = base_semantic
        keyword = base_keyword

    # Normalize to sum to 1.0
    total = semantic + keyword
    return (semantic / total, keyword / total)


def build_unified_context(results: List[dict]) -> str:
    """Build context string from multi-source results."""
    context_parts = []

    for i, result in enumerate(results, 1):
        source_type = result['source_type']

        context_parts.append(f"\n## Source [{i}] - {source_type.upper()}: {result['doc_title']}\n")

        if source_type == 'pdf':
            context_parts.append(f"**Page {result['page_number']}**\n")
        elif source_type == 'youtube':
            timestamp_fmt = format_timestamp(result['timestamp_start'])
            context_parts.append(f"**Timestamp {timestamp_fmt}**\n")

        # Section path
        if result['section_path']:
            section_str = " > ".join(result['section_path'])
            context_parts.append(f"**Section**: {section_str}\n")

        # Content
        context_parts.append(f"\n{result['content']}\n")
        context_parts.append("\n" + "="*80 + "\n")

    return "".join(context_parts)



def build_unified_context_with_images(results: List[dict], use_images: bool = False) -> str:
    """Build context string from multi-source results WITH screenshot OCR."""
    context_parts = []

    for i, result in enumerate(results, 1):
        source_type = result['source_type']

        context_parts.append(f"\n## Source [{i}] - {source_type.upper()}: {result['doc_title']}\n")

        if source_type == 'pdf':
            context_parts.append(f"**Page {result['page_number']}**\n")
        elif source_type == 'youtube':
            timestamp_fmt = format_timestamp(result['timestamp_start'])
            context_parts.append(f"**Timestamp {timestamp_fmt}**\n")

        # Section path
        if result['section_path']:
            section_str = " > ".join(result['section_path'])
            context_parts.append(f"**Section**: {section_str}\n")

        # Content (transcript or text)
        context_parts.append(f"\n{result['content']}\n")

        # Add screenshot OCR text if available (CRITICAL for multimodal!)
        if use_images and result.get('screenshots'):
            context_parts.append(f"\n**Visual Context:**\n")
            for screenshot in result['screenshots']:
                if screenshot.get('ocr_text'):
                    context_parts.append(f"  - Screenshot OCR: {screenshot['ocr_text']}\n")
                if screenshot.get('basic_summary'):
                    context_parts.append(f"    ({screenshot['basic_summary']})\n")

        context_parts.append("\n" + "="*80 + "\n")

    return "".join(context_parts)


@router.post("/", response_model=UnifiedChatResponse)
async def chat_unified(request: UnifiedChatRequest):
    """
    Unified chat endpoint that searches across all content types.

    Supports:
    - PDF documents
    - YouTube videos
    - Future: audio files, web pages, etc.

    Query flow:
    1. Generate embedding for question
    2. Search each source type (pdf, youtube) separately
    3. Merge results by relevance score
    4. Build unified context
    5. Call LLM with combined context
    6. Return answer with source-specific citations
    """
    db = DatabaseClient()
    embedding_gen = EmbeddingGenerator()

    with CostTracker(
        query_type='unified_chat',
        query_text=request.question
    ) as tracker:
        try:
            with db:
                # Determine which source types to search
                search_types = []
                if 'all' in request.source_types:
                    search_types = ['pdf', 'youtube']
                else:
                    search_types = request.source_types

                # Generate question embedding
                question_embedding = embedding_gen.generate_embeddings([request.question])[0]

                # Classify query type for optimal retrieval
                query_type = classify_query_type(request.question)

                # Detect document type (if searching specific docs)
                doc_type = 'mixed'  # Default
                if request.doc_ids and len(request.doc_ids) > 0:
                    # Get first document to detect type
                    with db.conn.cursor() as cur:
                        cur.execute("SELECT title FROM document_index WHERE id = %s", (request.doc_ids[0],))
                        row = cur.fetchone()
                        if row:
                            doc_type = detect_document_type(row[0])

                # Determine optimal weights
                semantic_weight, keyword_weight = determine_optimal_weights(doc_type, query_type)

                # Search each source type
                all_results = []
                sources_found = {}

                for source_type in search_types:
                    # Use database function for multi-source search
                    with db.conn.cursor() as cur:
                        cur.execute("""
                            SELECT * FROM search_chunks_multi_source(
                                %s::vector(1536),
                                %s,
                                ARRAY[%s]::TEXT[],
                                %s::TEXT[],
                                %s,
                                %s,
                                %s
                            )
                        """, (
                            question_embedding,
                            request.question,
                            source_type,
                            request.doc_ids if request.doc_ids else None,
                            semantic_weight,  # Use computed weight
                            keyword_weight,   # Use computed weight
                            request.top_k_per_source
                        ))

                        results = cur.fetchall()

                    # Convert to dict
                    for row in results:
                        all_results.append({
                            'chunk_id': row[0],
                            'doc_id': row[1],
                            'doc_title': row[2],
                            'source_type': row[3],
                            'content': row[4],
                            'page_number': row[5],
                            'timestamp_start': row[6],
                            'timestamp_end': row[7],
                            'video_url_with_timestamp': row[8],
                            'section_path': row[9] or [],
                            'similarity': row[10]
                        })

                    sources_found[source_type] = len(results)

                if not all_results:
                    raise HTTPException(
                        status_code=404,
                        detail="No relevant content found in any source"
                    )

                # Sort by relevance across all sources
                all_results.sort(key=lambda x: x['similarity'], reverse=True)

                # Take top results
                top_results = all_results[:15]

                # Build unified context
                context = build_unified_context_with_images(top_results, use_images=request.use_images)

                # Build technical-aware system prompt
                is_technical = doc_type in ['technical', 'mixed']

                system_prompt = f"""You are a Senior BAS/HVAC/Niagara Technical Expert at AME, providing hands-on implementation guidance to field technicians.

**YOUR ROLE:**
You are the technician's mentor - not just answering questions, but ensuring they can SUCCESSFULLY IMPLEMENT solutions. Your knowledge comes from ingested technical documents, training videos, and system manuals.

**AVAILABLE SOURCES:**
- 📄 PDF Technical Documents (cite as "[N]" with page reference)
- 🎥 Video Tutorials & Training (cite as "[N]" with timestamp)

**RESPONSE STRUCTURE - ALWAYS FOLLOW THIS:**

## 1. Direct Answer (2-3 sentences)
- Answer the core question immediately with key facts
- Include specific values, settings, or parameters
- Cite sources: "The master supervisor connects via Fox protocol [1]"

## 2. Implementation Details (THE REAL VALUE)
- **Exact navigation paths**: "Go to `Station > Config > Services > FoxService`"
- **Specific settings**: "Set `broadcastInterval` to `30000` (30 seconds)"
- **What you'll see**: "The status should change from 'Disabled' to 'Running'"
- **Reference visuals**: "As shown in the System Database diagram [2]"

## 3. Step-by-Step Procedure (when applicable)
Provide numbered steps with:
1. **Action**: What to click/configure
2. **Verification**: What should happen ("You should see...")
3. **Common mistakes**: ⚠️ Watch out for X

## 4. Related Concepts
Briefly mention related topics the tech might need:
- "This connects to building graphics via..."
- "For multi-site setups, also consider..."

## 5. Engagement (ALWAYS END WITH THIS)
Offer specific next steps:
- "Would you like me to walk through the graphics configuration next?"
- "Should I explain how to troubleshoot if the connection fails?"
- "Want me to show the exact Px view setup for this?"

**CITATION REQUIREMENTS:**
- EVERY technical claim needs [N] citation
- Page refs: "as documented on page 45 [2]"
- Video refs: "demonstrated at 5:32 [1]"
- Conflicting info: "[1] shows X for v4.8, while [2] indicates Y for v4.10"

**TECHNICAL ACCURACY IS PARAMOUNT:**
- Use exact terminology from sources (Niagara, Tridium, N4, AX, etc.)
- Preserve model numbers, version strings exactly
- Include units: "5 meters", "30 seconds", "100ms"
- If sources conflict or info is missing: "The sources don't specify this; I recommend..."

**MARKDOWN FORMATTING:**
- Use ## and ### for clear sections
- Use **bold** for key terms and actions
- Use `code` for paths, settings, values
- Use > blockquotes for important warnings
- Use numbered lists for procedures
- Use bullet lists for options/alternatives

**DO NOT:**
- Give surface-level overviews without implementation detail
- Skip the engagement/follow-up prompt at the end
- Assume settings or defaults not in sources
- Provide generic advice - be SPECIFIC to the documented systems
"""

                # Build messages with conversation history
                messages = [{"role": "system", "content": system_prompt}]
                
                # Add conversation history if provided (last 4 messages for context)
                if request.chat_history:
                    history_messages = request.chat_history[-4:]  # Limit to last 4 messages
                    for msg in history_messages:
                        messages.append({"role": msg.role, "content": msg.content})
                
                # Add current question with context
                messages.append({"role": "user", "content": f"Question: {request.question}\n\nContext from sources:\n{context}"})

                # Call GPT-4o-mini with increased tokens for detailed guidance
                response = openai_client.chat.completions.create(
                    model=os.getenv('CHAT_MODEL', 'gpt-4o-mini'),
                    messages=messages,
                    temperature=0.3,  # Slightly higher for better teaching explanations
                    max_tokens=2500   # More room for detailed implementation steps
                )

                # Track tokens
                tracker.add_tokens(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    model="gpt-4o-mini"
                )

                # Build citations and collect related images
                citations = []
                related_images = []

                for result in top_results:
                    if result['source_type'] == 'pdf':
                        citations.append(PDFCitation(
                            doc_id=result['doc_id'],
                            doc_title=result['doc_title'],
                            chunk_id=result['chunk_id'],
                            content=result['content'][:300] + "..." if len(result['content']) > 300 else result['content'],
                            page_number=result['page_number'],
                            section_path=result['section_path'],
                            similarity_score=float(result['similarity'])
                        ))

                        # Collect images from this chunk (same page)
                        try:
                            chunk_images = db.get_images_for_chunk(result['chunk_id'])
                            for img in chunk_images:
                                if img.get('s3_url'):
                                    related_images.append(RelatedImage(
                                        url=img['s3_url'],
                                        caption=img.get('caption') or img.get('ocr_text'),
                                        image_type=img.get('image_type'),
                                        page_number=img.get('page_number')
                                    ))
                        except Exception as e:
                            print(f"Error fetching images for chunk {result['chunk_id']}: {e}")

                    elif result['source_type'] == 'youtube':
                        citations.append(YouTubeCitation(
                            doc_id=result['doc_id'],
                            doc_title=result['doc_title'],
                            chunk_id=result['chunk_id'],
                            content=result['content'][:300] + "..." if len(result['content']) > 300 else result['content'],
                            timestamp=result['timestamp_start'],
                            timestamp_formatted=format_timestamp(result['timestamp_start']),
                            video_url=result['video_url_with_timestamp'] or '',
                            section_path=result['section_path'],
                            similarity_score=float(result['similarity']),
                            thumbnail_url=f"https://img.youtube.com/vi/{result['doc_id'].replace('video_', '')}/maxresdefault.jpg"
                        ))

                        # Collect screenshots from timestamp range
                        try:
                            screenshots = db.get_screenshots_for_timestamp(
                                result['doc_id'],
                                result['timestamp_start'],
                                result['timestamp_end']
                            )
                            for screenshot in screenshots:
                                if screenshot.get('s3_url'):
                                    related_images.append(RelatedImage(
                                        url=screenshot['s3_url'],
                                        caption=screenshot.get('ocr_text') or screenshot.get('caption'),
                                        image_type='screenshot',
                                        timestamp=screenshot.get('timestamp')
                                    ))
                        except Exception as e:
                            print(f"Error fetching screenshots for {result['doc_id']}: {e}")

                # Deduplicate images by URL
                unique_images = {img.url: img for img in related_images}

                # Clean up response
                answer = response.choices[0].message.content.strip()

                # Remove code fence wrapper if present
                if answer.startswith('```') and answer.endswith('```'):
                    lines = answer.split('\n')
                    if lines[0].startswith('```'):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == '```':
                        lines = lines[:-1]
                    answer = '\n'.join(lines).strip()

                # Generate follow-up suggestions based on query type
                follow_ups = generate_follow_up_suggestions(
                    request.question, 
                    answer, 
                    query_type, 
                    citations
                )

                return UnifiedChatResponse(
                    answer=answer,
                    citations=citations,
                    sources_searched=search_types,
                    total_sources_found=len(all_results),
                    model_used="gpt-4o-mini",
                    tokens_used=response.usage.total_tokens,
                    related_images=list(unique_images.values())[:10],
                    follow_up_suggestions=follow_ups
                )

        except HTTPException:
            raise
        except Exception as e:
            import traceback
            print(f"Error in unified chat: {e}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
