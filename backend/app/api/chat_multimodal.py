"""Multimodal Chat API with Golden Chunk strategy and context expansion."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
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
    include_images: bool = True
) -> tuple[List[Dict], List[str], List[Dict]]:
    """
    Build GPT-4o messages with text, images, and tables.

    Args:
        expanded_contexts: List of enriched contexts from expand_chunk_context
        question: User's question
        doc_title: Document title
        include_images: Whether to include images in vision mode

    Returns:
        Tuple of (messages, images_used, tables_used)
    """
    messages = []

    # Detect procedural question
    is_procedural = any(word in question.lower() for word in [
        'how to', 'how do', 'steps', 'procedure', 'process', 'workflow', 'show me'
    ])

    # Build conditional response structure
    if is_procedural:
        question_type = "For procedural questions (how-to, steps, process):"
        response_structure = """1. Start with a brief overview (1-2 sentences)
2. Break down into clear numbered steps:
   **Step 1: [Action Name]**
   - Clear description of what to do
   - Reference UI elements: "Click the **Add** button" or "In the **Username** field..."
   - Include relevant screenshots: "As shown in Figure X below..."
   - Cite source: [N]

3. For each step:
   - **What to do**: Clear action
   - **Where**: Exact location (screen, pane, menu)
   - **Visual reference**: Mention if screenshot shows this step
   - **Expected result**: What happens next

4. End with a summary or verification step"""
    else:
        question_type = "For informational questions:"
        response_structure = """1. Start with a direct answer (1-2 sentences)
2. Organize details into sections with headers:
   **## Topic Name**
   - Key points in bullets
   - Reference screenshots when available
   - Include tables for structured data

3. Use examples and visual references
4. Cite all sources [N]"""

    # System prompt
    system_content = f"""You are an expert technical documentation assistant for "{doc_title}".

IMPORTANT: Return ONLY the formatted markdown content. Do NOT wrap your entire response in code fences (```). Your response should start directly with content (like ## Heading or text), not with ```.

FORMATTING REQUIREMENTS (CRITICAL - Follow EXACTLY):
- Use proper markdown syntax with clear visual hierarchy
- Use ## for main sections, ### for subsections
- Use **bold** for important terms, button names, field names
- Use numbered lists for steps: "1. Step one\n2. Step two\n3. Step three"
- Use bullet points (- or *) for options or features
- Use `backticks` for technical terms, filenames, or values
- CRITICAL: Add BLANK LINES between ALL paragraphs and sections
- CRITICAL: Add BLANK LINES before and after headings
- CRITICAL: Add BLANK LINES before and after lists
- CRITICAL: Add BLANK LINES before and after code blocks
- CRITICAL: Add BLANK LINES before and after tables
- CRITICAL: Add BLANK LINES before and after images

EXAMPLE FORMATTING:
```
## Section Title

This is a paragraph with proper spacing.

Another paragraph after a blank line.

### Subsection

- Bullet point one
- Bullet point two
- Bullet point three

Here's an image:

![Image description](https://s3.url/image.jpg)

The image shows...
```

RESPONSE STRUCTURE:
{question_type}
{response_structure}

CITATION RULES:
- Place citations immediately after the statement: "The user must have admin privileges [1]"
- Reference page numbers when describing location: "as shown on page 70 [2]"
- When showing screenshots: "See Figure 18 below [3]" (the screenshot will appear in the citation)
- Group related citations: "These steps are required [1][2]"

VISUAL CONTENT:
- When images are provided in context, YOU MUST embed them in your response using markdown image syntax
- Format: ![Image caption](EXACT_S3_URL_FROM_CONTEXT)
- The S3 URLs are provided in the context under "Images on Page X" - copy them EXACTLY
- Example: If context shows "s3_url: https://bucket.s3.amazonaws.com/image.jpg", use: ![Caption](https://bucket.s3.amazonaws.com/image.jpg)
- Place images right after describing them: "The dialog contains three fields:\n\n![User Dialog Screenshot](https://...)\n\nAs shown above..."
- For tables: Include the FULL markdown table from context in your response
- Always embed visual content directly - don't just reference it

TONE: Professional, clear, concise. Like a technical manual or official documentation.
"""

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

    # Build multimodal content for user message
    user_content = [
        {
            "type": "text",
            "text": f"Question: {question}\n\nDocument Context:\n{text_context}"
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
    Golden Chunk + Multimodal RAG with hierarchical context expansion.

    This endpoint implements the full multimodal RAG strategy:
    1. Search for top-k "golden chunks" using hybrid search
    2. Expand each chunk with surrounding context (siblings)
    3. Enrich with section hierarchy paths
    4. Add images from the same pages
    5. Add tables from the same pages
    6. Send everything to GPT-4o with vision

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
                # Step 1: Get document info
                doc = db.get_document_details(request.doc_id)
                if not doc:
                    raise HTTPException(status_code=404, detail="Document not found")

                # Step 2: Generate embedding for question
                question_embedding = embedding_gen.generate_embeddings([request.question])[0]

                # Step 3: Search for GOLDEN CHUNKS using hybrid search
                # We use fewer chunks (5 instead of 15) because each will be enriched
                search_resultssearch_results = db.search_chunks_hybrid(
                    query_embedding=question_embedding,
                    query_text=request.question,
                    doc_id=request.doc_id,
                    semantic_weight=0.5,
                    keyword_weight=0.5,
                    top_k=request.top_k
                )

                if not search_results:
                    raise HTTPException(
                        status_code=404,
                        detail="No relevant content found in document"
                    )

                # Step 4: Expand context for each golden chunk
                expanded_contexts = []
                for result in search_results:
                    expanded = expand_chunk_context(
                        db=db,
                        chunk=result,
                        doc_id=request.doc_id,
                        include_images=request.use_images,
                        include_tables=request.use_tables,
                        context_window=request.context_window
                    )
                    expanded_contexts.append(expanded)

                # Step 5: Build multimodal messages
                messages, images_used, tables_used = build_multimodal_messages(
                    expanded_contexts=expanded_contexts,
                    question=request.question,
                    doc_title=doc['title'],
                    include_images=request.use_images
                )

                # Step 6: Call GPT-4o-mini (cheaper with vision + tool calling)
                # GPT-4o-mini now supports vision at much lower cost than GPT-4o
                model = "gpt-4o-mini"  # Supports vision, tool calling, and much cheaper

                response = openai_client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1500
                )

                # Track token usage and cost
                tracker.add_tokens(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    model=model
                )

                # Step 7: Build enriched citations
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

                # Step 8: Clean up the response
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
