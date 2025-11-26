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


class UnifiedChatRequest(BaseModel):
    """Multi-source chat request."""
    question: str
    source_types: List[Literal['pdf', 'youtube', 'all']] = ['all']
    doc_ids: List[str] = []  # Specific documents, or empty = search all
    top_k_per_source: int = 5
    use_images: bool = False  # Include screenshots/images in context
    semantic_weight: float = 0.5
    keyword_weight: float = 0.5


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


class UnifiedChatResponse(BaseModel):
    """Unified chat response with multi-source citations."""
    answer: str
    citations: List[Union[PDFCitation, YouTubeCitation]]
    sources_searched: List[str]
    total_sources_found: int
    model_used: str
    tokens_used: int


def format_timestamp(seconds: float) -> str:
    """Format timestamp as MM:SS."""
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes}:{secs:02d}"


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
                            request.semantic_weight,
                            request.keyword_weight,
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
                context = build_unified_context(top_results)

                # Build system prompt
                system_prompt = f"""You are a helpful assistant answering questions based on multiple sources.

Sources available:
- PDF documents (referenced as "Page X")
- YouTube videos (referenced as "Timestamp MM:SS")

CRITICAL INSTRUCTIONS:
1. Answer the question directly and concisely
2. ALWAYS cite your sources using [N] notation
3. When citing videos, mention the timestamp: "as explained at 12:34 [1]"
4. When citing PDFs, mention the page: "as shown on page 45 [2]"
5. If information comes from multiple sources, cite them all: [1][2][3]
6. Use proper markdown formatting
7. Add blank lines between sections

Do NOT wrap your response in code fences.
"""

                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Question: {request.question}\n\nContext from sources:\n{context}"}
                ]

                # Call GPT-4o-mini
                response = openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=1500
                )

                # Track tokens
                tracker.add_tokens(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    model="gpt-4o-mini"
                )

                # Build citations
                citations = []
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

                return UnifiedChatResponse(
                    answer=answer,
                    citations=citations,
                    sources_searched=search_types,
                    total_sources_found=len(all_results),
                    model_used="gpt-4o-mini",
                    tokens_used=response.usage.total_tokens
                )

        except HTTPException:
            raise
        except Exception as e:
            import traceback
            print(f"Error in unified chat: {e}")
            print(traceback.format_exc())
            raise HTTPException(status_code=500, detail=str(e))
