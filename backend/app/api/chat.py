"""Chat API endpoint with RAG using existing Supabase functions."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import sys
from pathlib import Path
import os
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient
from utils.embeddings import EmbeddingGenerator

router = APIRouter()

# OpenAI client
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


class ChatMessage(BaseModel):
    """Single message in chat history."""
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    """Chat request with document context."""
    doc_id: str
    question: str
    chat_history: List[ChatMessage] = []
    top_k: int = 15  # Increased for better recall
    use_hybrid_search: bool = True
    semantic_weight: float = 0.5  # Balanced for technical docs
    keyword_weight: float = 0.5


class Citation(BaseModel):
    """Citation with chunk reference."""
    chunk_id: str
    content: str
    page_number: int
    section_id: Optional[str]
    similarity_score: float


class ChatResponse(BaseModel):
    """Chat response with answer and citations."""
    answer: str
    citations: List[Citation]
    tokens_used: int
    search_results_count: int


@router.post("/", response_model=ChatResponse)
async def chat_with_document(request: ChatRequest):
    """
    Chat with a document using RAG (Retrieval Augmented Generation).

    Process:
    1. Generate embedding for user question
    2. Search relevant chunks using hybrid search (semantic + keyword)
    3. Build context from top chunks
    4. Generate answer using OpenAI with citations
    5. Return answer + clickable citations with page numbers
    """
    db = DatabaseClient()
    embedding_gen = EmbeddingGenerator()

    try:
        with db:
            # Step 1: Get document info
            doc = db.get_document_details(request.doc_id)
            if not doc:
                raise HTTPException(status_code=404, detail="Document not found")

            # Step 2: Generate embedding for question
            question_embedding = embedding_gen.generate_embeddings([request.question])[0]

            # Step 3: Search relevant chunks using hybrid search
            if request.use_hybrid_search:
                search_results = db.search_chunks_hybrid(
                    query_embedding=question_embedding,
                    query_text=request.question,
                    doc_id=request.doc_id,
                    semantic_weight=request.semantic_weight,
                    keyword_weight=request.keyword_weight,
                    top_k=request.top_k
                )
            else:
                # Fallback to semantic-only search
                search_results = db.search_chunks(
                    query_embedding=question_embedding,
                    doc_id=request.doc_id,
                    top_k=request.top_k
                )

            if not search_results:
                raise HTTPException(
                    status_code=404,
                    detail="No relevant content found in document"
                )

            # Step 4: Build context from chunks with citations
            context_parts = []
            citations = []

            for idx, result in enumerate(search_results, 1):
                chunk_content = result['content']
                page_num = result.get('page_number', 0)
                chunk_id = result['id']
                section_id = result.get('section_id')

                # Get similarity score (from hybrid or semantic search)
                similarity = result.get('combined_score') or result.get('similarity', 0)

                # Add to context with citation marker
                context_parts.append(
                    f"[{idx}] (Page {page_num}): {chunk_content}"
                )

                # Store citation
                citations.append(Citation(
                    chunk_id=chunk_id,
                    content=chunk_content[:200] + "..." if len(chunk_content) > 200 else chunk_content,
                    page_number=page_num,
                    section_id=section_id,
                    similarity_score=float(similarity)
                ))

            context = "\n\n".join(context_parts)

            # Step 5: Build chat messages for OpenAI
            messages = []

            # System prompt with instructions
            # Detect if this is a procedural "how to" question
            is_procedural = any(word in request.question.lower() for word in [
                'how to', 'how do', 'steps', 'procedure', 'process', 'workflow'
            ])

            system_prompt = f"""You are an expert technical documentation assistant for "{doc['title']}".

The user is asking: "{request.question}"

You have access to {len(search_results)} relevant sections from the document. Each section is marked with [N] (Page X).

CRITICAL INSTRUCTIONS:
1. {"Provide clear, numbered step-by-step instructions" if is_procedural else "Provide a precise, well-organized answer"}
2. Quote EXACT button names, menu paths, field names, and UI elements from the document
3. ALWAYS cite sources using format: [N] or "on page X [N]"
4. Include multiple citations when synthesizing information from different sections
5. If procedures span multiple pages, organize steps sequentially with page references
6. Include warnings, notes, or prerequisites if mentioned in the source material
7. If the retrieved content lacks sufficient detail, explicitly state what's missing
8. Be comprehensive but direct - technical users need complete accurate information

Retrieved Content (ordered by relevance):
{context}

Answer with precision, completeness, and proper citations."""

            messages.append({"role": "system", "content": system_prompt})

            # Add chat history
            for msg in request.chat_history[-4:]:  # Keep last 4 messages for context
                messages.append({"role": msg.role, "content": msg.content})

            # Add current question
            messages.append({"role": "user", "content": request.question})

            # Step 6: Generate answer with OpenAI
            response = openai_client.chat.completions.create(
                model=os.getenv('CHAT_MODEL', 'gpt-4o-mini'),
                messages=messages,
                temperature=0.2,  # Very low temperature for factual technical answers
                max_tokens=1200  # Increased for comprehensive procedural answers
            )

            answer = response.choices[0].message.content
            tokens_used = response.usage.total_tokens

            # Return only top 5 most relevant citations to user
            # (but all were used for context generation)
            top_citations = sorted(citations, key=lambda x: x.similarity_score, reverse=True)[:5]

            return ChatResponse(
                answer=answer,
                citations=top_citations,
                tokens_used=tokens_used,
                search_results_count=len(search_results)
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{doc_id}/history")
async def get_chat_history(doc_id: str, limit: int = 50):
    """
    Get chat history for a document (if we implement storage later).
    For now, returns empty - client handles history in state.
    """
    return {
        "doc_id": doc_id,
        "messages": [],
        "message": "Chat history stored client-side"
    }
