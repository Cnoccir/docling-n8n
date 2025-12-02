"""Multimodal Chat API with Golden Chunk strategy and context expansion."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import sys
from pathlib import Path
import os
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from src.database.db_client import DatabaseClient
from src.utils.embeddings import EmbeddingGenerator
from app.utils.cost_tracker import CostTracker
from app.utils.query_classifier import classify_query
from app.utils.query_rewriter import rewrite_query
from app.utils.prompt_builder import detect_question_mode, build_system_prompt, build_user_message
from app.utils.conversation_manager import (
    extract_conversation_context,
    enhance_query_with_context,
    should_expand_context_window,
    format_chat_history_for_llm
)

# NEW: Import improvements
from app.utils.answer_verifier import quick_verify
from app.utils.adaptive_retrieval import adaptive_retrieval_params, needs_multi_hop as check_multi_hop
from app.utils.query_cache import QueryCache
from app.utils.conversation_manager_enhanced import format_chat_history_with_summary
from app.utils.multi_hop_retriever import multi_hop_retrieve
from app.utils.retrieval_metrics import RetrievalMetrics

router = APIRouter()

# OpenAI client
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
# NEW: Initialize cache and metrics
query_cache = QueryCache(db_client=None, ttl_hours=24)
retrieval_metrics = RetrievalMetrics(db_client=None)



# NEW: Phase 3 - Import topic mapping
from app.utils.topic_constants import CATEGORY_TO_TOPIC_MAP

def map_categories_to_topics(categories: List[str]) -> List[str]:
    """Map query categories to relevant topic list for boosting.
    
    Args:
        categories: List of query categories (e.g., ['architecture', 'graphics'])
        
    Returns:
        List of relevant topics (for graduated boosting, not filtering)
    
    Strategy: NO HARD EXCLUSIONS. Use soft boosting instead.
    - Primary match (exact category→topic): 1.5x boost
    - Secondary match (related topics): 1.2x boost  
    - No match: 1.0x (still searchable)
    """
    relevant_topics = []
    for category in categories:
        topics = CATEGORY_TO_TOPIC_MAP.get(category, [])
        relevant_topics.extend(topics)
    
    # Remove duplicates
    return list(set(relevant_topics))


class ChatMessage(BaseModel):
    """Single message in chat history."""
    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat request with multimodal support."""
    doc_id: str
    question: str
    chat_history: List[ChatMessage] = []
    top_k: int = 5  # Fewer golden chunks, but enriched
    use_images: bool = True
    use_tables: bool = True
    context_window: int = 2  # ±2 surrounding chunks
    model: str = "gpt-4o-mini"  # User can choose: gpt-4o-mini (cost-effective) or gpt-4o (deeper reasoning)
    temperature: Optional[float] = None  # Auto-set based on mode if None


class ImageReference(BaseModel):
    """Image reference in citation."""
    id: str
    url: str
    caption: Optional[str]
    page_number: int


class TableReference(BaseModel):
    """Table reference in citation."""
    id: str
    description: Optional[str]
    markdown: str
    page_number: int


class EnrichedCitation(BaseModel):
    """Citation with expanded context and multimodal references."""
    chunk_id: str
    content: str
    page_number: int
    section_id: Optional[str]
    section_path: List[str]
    similarity_score: float
    context_before: Optional[str] = None
    context_after: Optional[str] = None
    images: List[ImageReference] = []
    tables: List[TableReference] = []


class ChatResponse(BaseModel):
    """Multimodal chat response."""
    answer: str
    citations: List[EnrichedCitation]
    images_used: List[str]  # S3 URLs
    tables_used: int
    tokens_used: int
    search_results_count: int
    model_used: str


def get_sibling_chunks(
    db: DatabaseClient,
    doc_id: str,
    chunk_id: str,
    window: int = 2
) -> Dict[str, List[Dict]]:
    """
    Get surrounding chunks (siblings) for context expansion.

    Args:
        db: Database client
        doc_id: Document ID
        chunk_id: Target chunk ID
        window: Number of chunks before/after to retrieve

    Returns:
        Dict with 'before' and 'after' lists of chunks
    """
    with db.conn.cursor() as cur:
        # Get all chunks for this doc, ordered by ID
        # Chunk IDs are like: docID_chunk_000123
        cur.execute("""
            SELECT id, content, page_number, section_id, section_path
            FROM chunks
            WHERE doc_id = %s
            ORDER BY id
        """, (doc_id,))

        all_chunks = cur.fetchall()

    # Find current chunk index
    current_idx = None
    for i, chunk in enumerate(all_chunks):
        if chunk[0] == chunk_id:
            current_idx = i
            break

    if current_idx is None:
        return {'before': [], 'after': []}

    # Get siblings
    before = all_chunks[max(0, current_idx - window):current_idx]
    after = all_chunks[current_idx + 1:min(len(all_chunks), current_idx + 1 + window)]

    def chunk_to_dict(chunk):
        return {
            'id': chunk[0],
            'content': chunk[1],
            'page_number': chunk[2],
            'section_id': chunk[3],
            'section_path': chunk[4] if chunk[4] else []
        }

    return {
        'before': [chunk_to_dict(c) for c in before],
        'after': [chunk_to_dict(c) for c in after]
    }


def expand_chunk_context(
    db: DatabaseClient,
    chunk: Dict,
    doc_id: str,
    include_images: bool = True,
    include_tables: bool = True,
    context_window: int = 2
) -> Dict[str, Any]:
    """
    Expand a golden chunk with hierarchical and multimodal context.

    This is the core of the Golden Chunk strategy:
    - Chunk + surrounding context (siblings)
    - Section hierarchy path
    - Images on the same page
    - Tables on the same page

    Args:
        db: Database client
        chunk: The golden chunk from search
        doc_id: Document ID
        include_images: Whether to fetch images
        include_tables: Whether to fetch tables
        context_window: Number of chunks before/after to include

    Returns:
        Enriched context dictionary
    """
    page_num = chunk.get('page_number', 0)
    section_path = chunk.get('section_path', [])

    # Get sibling chunks for context
    siblings = get_sibling_chunks(db, doc_id, chunk['id'], window=context_window)

    # Get images on this page
    images = []
    if include_images and page_num > 0:
        images = db.get_images_by_pages(doc_id, [page_num])

    # Get tables on this page
    tables = []
    if include_tables and page_num > 0:
        tables = db.get_tables_by_pages(doc_id, [page_num])

    return {
        'chunk': chunk,
        'section_path': section_path if section_path else ['Unknown Section'],
        'previous_chunks': siblings['before'],
        'next_chunks': siblings['after'],
        'images': images,
        'tables': tables
    }


def build_multimodal_messages(
    expanded_contexts: List[Dict],
    question: str,
    doc_title: str,
    question_mode: str,
    chat_history: List[ChatMessage] = None,
    include_images: bool = True
) -> tuple[List[Dict], List[str], List[Dict]]:
    """
    Build GPT-4o messages with adaptive prompts based on question mode.

    Args:
        expanded_contexts: List of enriched contexts from expand_chunk_context
        question: User's question
        doc_title: Document title
        question_mode: Mode detected (conceptual, troubleshooting, design, procedural, comparison)
        chat_history: Optional chat history for conversation context
        include_images: Whether to include images in vision mode

    Returns:
        Tuple of (messages, images_used, tables_used)
    """
    messages = []

    # Use adaptive system prompt based on question mode
    has_chat_history = chat_history is not None and len(chat_history) > 0
    system_content = build_system_prompt(
        mode=question_mode,
        doc_title=doc_title,
        has_chat_history=has_chat_history
    )
    
    # Add critical note about not wrapping response in code fences
    system_content = f"""IMPORTANT: Return ONLY the formatted markdown content. Do NOT wrap your entire response in code fences (```). Your response should start directly with content (like ## Heading or text), not with ```.

{system_content}"""

    messages.append({"role": "system", "content": system_content})

    # Build rich context for each golden chunk
    context_parts = []
    all_images = []
    all_tables = []

    for idx, ctx in enumerate(expanded_contexts, 1):
        # Section hierarchy
        section_path = " > ".join(ctx['section_path'])
        context_parts.append(f"\n## Source [{idx}]: {section_path}\n")
        context_parts.append(f"**Page {ctx['chunk']['page_number']}**\n\n")

        # Context before (previous chunks)
        if ctx['previous_chunks']:
            context_parts.append("**Context (preceding):**\n")
            for prev in ctx['previous_chunks']:
                preview = prev['content'][:200].replace('\n', ' ')
                context_parts.append(f"- {preview}...\n")
            context_parts.append("\n")

        # GOLDEN CHUNK (the main search result)
        context_parts.append(f"**Main Content:**\n")
        context_parts.append(ctx['chunk']['content'])
        context_parts.append("\n")

        # Context after (next chunks)
        if ctx['next_chunks']:
            context_parts.append("\n**Context (following):**\n")
            for nxt in ctx['next_chunks']:
                preview = nxt['content'][:200].replace('\n', ' ')
                context_parts.append(f"- {preview}...\n")

        # Images on this page
        if ctx['images']:
            context_parts.append(f"\n**Images on Page {ctx['chunk']['page_number']}:**\n")
            for img in ctx['images']:
                caption = img.get('caption', 'No caption')
                summary = img.get('basic_summary', 'No description')
                s3_url = img.get('s3_url', '')
                context_parts.append(f"- Image: {caption}\n")
                context_parts.append(f"  Description: {summary}\n")
                context_parts.append(f"  S3 URL: {s3_url}\n")
                context_parts.append(f"  [IMPORTANT: Embed this image in your response using: ![{caption}]({s3_url})]\n")
                all_images.append(img)

        # Tables on this page
        if ctx['tables']:
            context_parts.append(f"\n**Tables on Page {ctx['chunk']['page_number']}:**\n")
            for tbl in ctx['tables']:
                desc = tbl.get('description', 'No description')
                insights = tbl.get('key_insights', [])
                context_parts.append(f"- Table: {desc}\n")
                if insights:
                    context_parts.append(f"  Key insights: {', '.join(insights)}\n")
                context_parts.append(f"\n**TABLE MARKDOWN (include this EXACTLY in your response):**\n")
                context_parts.append(f"{tbl['markdown']}\n\n")
                all_tables.append(tbl)

        context_parts.append("\n" + "="*80 + "\n")

    # Combine text context
    text_context = "".join(context_parts)

    # Convert chat_history from ChatMessage objects to dicts if needed
    history_dicts = []
    if chat_history:
        history_dicts = [{"role": msg.role, "content": msg.content} for msg in chat_history]
    
    # Build user message with conversation context
    user_text = build_user_message(
        question=question,
        context=text_context,
        chat_history=history_dicts if history_dicts else None
    )

    # Build multimodal content for user message
    user_content = [
        {
            "type": "text",
            "text": user_text
        }
    ]

    # Add images (GPT-4o vision)
    # Limit to 5 images for cost control
    if include_images and all_images:
        for img in all_images[:5]:
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": img['s3_url'],
                    "detail": "low"  # or "high" for better quality
                }
            })

    messages.append({
        "role": "user",
        "content": user_content
    })

    return messages, [img['s3_url'] for img in all_images[:5]], all_tables


@router.post("/", response_model=ChatResponse)
async def chat_with_document_multimodal(request: ChatRequest):
    """
    Golden Chunk + Multimodal RAG with query intelligence and hierarchical context expansion.

    This endpoint implements the full multimodal RAG strategy:
    1. Classify query intent (architecture, graphics, provisioning, etc.)
    2. Rewrite query with domain-specific keywords
    3. Search for top-k "golden chunks" using hybrid search
    4. Expand each chunk with surrounding context (siblings)
    5. Enrich with section hierarchy paths
    6. Add images from the same pages
    7. Add tables from the same pages
    8. Send everything to GPT-4o with vision

    Returns enriched answers with multimodal citations.
    """
    db = DatabaseClient()
    embedding_gen = EmbeddingGenerator()

    # Track query cost
    with CostTracker(
        query_type='chat',
        query_text=request.question,
        doc_id=request.doc_id
    ) as tracker:
        try:
            with db:
                # Step 0: Process chat history for conversation context
                conversation_context = extract_conversation_context(
                    [{"role": msg.role, "content": msg.content} for msg in request.chat_history]
                )
                print(f"💬 Conversation context: is_followup={conversation_context['is_followup']}, entities={len(conversation_context['entities'])}")
                
                # Step 1: Classify query intent
                query_categories = classify_query(request.question, use_llm=True)
                print(f"📊 Query categories: {query_categories}")
                
                # Step 1b: Detect question mode for adaptive prompting
                question_mode = detect_question_mode(request.question, query_categories)
                print(f"🎭 Question mode: {question_mode}")
                
                # Step 2: Enhance query with conversation context if follow-up
                enhanced_question = enhance_query_with_context(request.question, conversation_context)
                
                # Step 3: Rewrite query for better keyword matching
                rewritten_query = rewrite_query(enhanced_question, query_categories)
                print(f"📝 Original:  {request.question}")
                print(f"📝 Enhanced:  {enhanced_question}")
                print(f"📝 Rewritten: {rewritten_query}")
                
                # Step 4: Map categories to topics for soft boosting (no exclusions)
                relevant_topics = map_categories_to_topics(query_categories)
                print(f"🔖 Relevant topics (will be boosted): {relevant_topics}")
                
                # Step 5: Adjust retrieval parameters based on conversation context
                top_k = request.top_k
                context_window = request.context_window
                if should_expand_context_window(conversation_context):
                    top_k = min(top_k + 2, 10)  # Expand slightly for follow-ups
                    context_window = min(context_window + 1, 4)  # Wider context window
                    print(f"🔍 Expanded context: top_k={top_k}, window={context_window}")
                
                # Step 6: Get document info
                doc = db.get_document_details(request.doc_id)
                if not doc:
                    raise HTTPException(status_code=404, detail="Document not found")

                # Step 5: Generate embedding for question (use original, not rewritten)
                question_embedding = embedding_gen.generate_embeddings([request.question])[0]

                # Step 6: Search for GOLDEN CHUNKS using topic-aware hybrid search (Phase 3)
                # We use fewer chunks (5 instead of 15) because each will be enriched
                # Use rewritten query for BM25 keyword search + soft topic boosting (NO HARD FILTERS)
                search_results = db.search_chunks_hybrid_with_topics(
                    query_embedding=question_embedding,
                    query_text=rewritten_query,  # Use rewritten for BM25
                    doc_id=request.doc_id,
                    include_topics=relevant_topics,  # Soft boost, not filter
                    exclude_topics=None,  # REMOVED: No hard exclusions
                    semantic_weight=0.5,
                    keyword_weight=0.5,
                    top_k=request.top_k
                )
                
                print(f"\n🔍 Search results with topics:")
                for i, result in enumerate(search_results[:3], 1):
                    print(f"  {i}. topic={result.get('topic')}, topics={result.get('topics')}, boost={result.get('topic_boost', 1.0)}, score={result.get('final_score', 0):.3f}")

                if not search_results:
                    raise HTTPException(
                        status_code=404,
                        detail="No relevant content found in document"
                    )

                # Step 7: Expand context for each golden chunk (use adaptive context_window)
                expanded_contexts = []
                for result in search_results:
                    expanded = expand_chunk_context(
                        db=db,
                        chunk=result,
                        doc_id=request.doc_id,
                        include_images=request.use_images,
                        include_tables=request.use_tables,
                        context_window=context_window  # Use adaptive window
                    )
                    expanded_contexts.append(expanded)

                # Step 8: Build adaptive multimodal messages
                messages, images_used, tables_used = build_multimodal_messages(
                    expanded_contexts=expanded_contexts,
                    question=request.question,
                    doc_title=doc['title'],
                    question_mode=question_mode,
                    chat_history=request.chat_history,
                    include_images=request.use_images
                )

                # Step 9: Configure model based on mode and user selection
                # User can choose model, but we optimize temperature/max_tokens based on mode
                model = request.model  # gpt-4o-mini or gpt-4o
                
                # Adaptive temperature based on question mode
                if request.temperature is not None:
                    temperature = request.temperature  # User override
                else:
                    # Auto-set based on mode
                    if question_mode in ['conceptual', 'design', 'comparison']:
                        temperature = 0.4  # Allow reasoning and creativity
                    elif question_mode == 'troubleshooting':
                        temperature = 0.3  # Balanced
                    else:  # procedural
                        temperature = 0.2  # Precise
                
                # Adaptive max_tokens based on mode
                if question_mode in ['design', 'troubleshooting', 'comparison']:
                    max_tokens = 2500  # Deeper analysis
                elif question_mode == 'conceptual':
                    max_tokens = 2000  # Teaching depth
                else:
                    max_tokens = 1500  # Procedural precision
                
                print(f"🤖 Model config: {model}, temp={temperature}, max_tokens={max_tokens}")

                response = openai_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )

                # Track token usage and cost
                tracker.add_tokens(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    model=model
                )

                # Step 9: Build enriched citations
                citations = []
                for ctx in expanded_contexts:
                    chunk = ctx['chunk']

                    # Get similarity score
                    similarity = chunk.get('combined_score') or chunk.get('similarity', 0)

                    # Format context before/after
                    context_before = None
                    if ctx['previous_chunks']:
                        context_before = " ... ".join([
                            c['content'][:100] for c in ctx['previous_chunks']
                        ])

                    context_after = None
                    if ctx['next_chunks']:
                        context_after = " ... ".join([
                            c['content'][:100] for c in ctx['next_chunks']
                        ])

                    # Format images
                    image_refs = [
                        ImageReference(
                            id=img['id'],
                            url=img['s3_url'],
                            caption=img.get('caption'),
                            page_number=img['page_number']
                        )
                        for img in ctx['images']
                    ]

                    # Format tables
                    table_refs = [
                        TableReference(
                            id=tbl['id'],
                            description=tbl.get('description'),
                            markdown=tbl['markdown'],
                            page_number=tbl['page_number']
                        )
                        for tbl in ctx['tables']
                    ]

                    citations.append(EnrichedCitation(
                        chunk_id=chunk['id'],
                        content=chunk['content'][:300] + "..." if len(chunk['content']) > 300 else chunk['content'],
                        page_number=chunk.get('page_number', 0),
                        section_id=chunk.get('section_id'),
                        section_path=ctx['section_path'],
                        similarity_score=float(similarity),
                        context_before=context_before,
                        context_after=context_after,
                        images=image_refs,
                        tables=table_refs
                    ))

                # Step 10: Clean up the response
                raw_answer = response.choices[0].message.content

                # Remove code fence wrapper if AI wrapped entire response
                if raw_answer.startswith('```') and raw_answer.endswith('```'):
                    # Strip opening fence (with optional language identifier)
                    lines = raw_answer.split('\n')
                    if lines[0].startswith('```'):
                        lines = lines[1:]
                    # Strip closing fence
                    if lines and lines[-1].strip() == '```':
                        lines = lines[:-1]
                    raw_answer = '\n'.join(lines)

                # Clean up the answer
                cleaned_answer = raw_answer.strip()

                return ChatResponse(
                    answer=cleaned_answer,
                    citations=citations,
                    images_used=images_used,
                    tables_used=len(tables_used),
                    tokens_used=response.usage.total_tokens,
                    search_results_count=len(search_results),
                    model_used=model
                )

        except HTTPException:
            raise
        except Exception as e:
            import traceback
            print(f"Error in multimodal chat: {e}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
