"""Query cache system for repeated queries.

Caches LLM responses to reduce costs for frequently asked questions.
Implements smart cache key generation with semantic similarity matching.
"""
import hashlib
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass
import numpy as np


@dataclass
class CachedQuery:
    """Cached query result."""
    cache_key: str
    question: str
    doc_id: str
    answer: str
    citations: List[Dict[str, Any]]
    created_at: datetime
    hit_count: int = 1
    model_used: str = "gpt-4o-mini"


class QueryCache:
    """Smart query cache with semantic matching."""

    def __init__(self, db_client, ttl_hours: int = 24, similarity_threshold: float = 0.95):
        """Initialize query cache.

        Args:
            db_client: DatabaseClient instance
            ttl_hours: Cache time-to-live in hours
            similarity_threshold: Minimum similarity to consider cache hit (0.0-1.0)
        """
        self.db = db_client
        self.ttl = timedelta(hours=ttl_hours)
        self.similarity_threshold = similarity_threshold

    def _generate_cache_key(self, question: str, doc_id: str) -> str:
        """Generate cache key from question and doc_id.

        Args:
            question: Normalized question text
            doc_id: Document ID

        Returns:
            SHA256 hash as cache key
        """
        # Normalize question: lowercase, strip whitespace, remove punctuation
        normalized = question.lower().strip()
        normalized = normalized.replace('?', '').replace('.', '').replace(',', '')

        # Create cache key
        key_input = f"{normalized}:{doc_id}"
        return hashlib.sha256(key_input.encode()).hexdigest()

    def get_cached_answer(
        self,
        question: str,
        doc_id: str,
        question_embedding: Optional[List[float]] = None
    ) -> Optional[CachedQuery]:
        """Check cache for identical or similar query.

        Args:
            question: User's question
            doc_id: Document ID
            question_embedding: Optional embedding for semantic matching

        Returns:
            CachedQuery if found, None otherwise
        """
        cache_key = self._generate_cache_key(question, doc_id)

        try:
            with self.db.conn.cursor() as cur:
                # First try exact match
                cur.execute("""
                    SELECT
                        cache_key,
                        question,
                        doc_id,
                        answer,
                        citations,
                        created_at,
                        hit_count,
                        model_used
                    FROM query_cache
                    WHERE cache_key = %s
                      AND doc_id = %s
                      AND created_at > %s
                    LIMIT 1
                """, (cache_key, doc_id, datetime.utcnow() - self.ttl))

                row = cur.fetchone()

                if row:
                    # Exact match found - increment hit count
                    cur.execute("""
                        UPDATE query_cache
                        SET hit_count = hit_count + 1,
                            last_accessed_at = NOW()
                        WHERE cache_key = %s
                    """, (cache_key,))
                    self.db.conn.commit()

                    return CachedQuery(
                        cache_key=row[0],
                        question=row[1],
                        doc_id=row[2],
                        answer=row[3],
                        citations=json.loads(row[4]) if isinstance(row[4], str) else row[4],
                        created_at=row[5],
                        hit_count=row[6],
                        model_used=row[7] or "gpt-4o-mini"
                    )

                # No exact match - try semantic similarity if embedding provided
                if question_embedding is not None:
                    return self._semantic_cache_lookup(question, doc_id, question_embedding)

                return None

        except Exception as e:
            print(f"⚠️  Cache lookup failed: {e}")
            return None

    def _semantic_cache_lookup(
        self,
        question: str,
        doc_id: str,
        question_embedding: List[float]
    ) -> Optional[CachedQuery]:
        """Find semantically similar cached query.

        Args:
            question: User's question
            doc_id: Document ID
            question_embedding: Question embedding vector

        Returns:
            CachedQuery if similar enough, None otherwise
        """
        try:
            with self.db.conn.cursor() as cur:
                # Find top 3 most similar cached queries for this document
                cur.execute("""
                    SELECT
                        cache_key,
                        question,
                        doc_id,
                        answer,
                        citations,
                        created_at,
                        hit_count,
                        model_used,
                        1 - (question_embedding <=> %s::vector) as similarity
                    FROM query_cache
                    WHERE doc_id = %s
                      AND created_at > %s
                      AND question_embedding IS NOT NULL
                    ORDER BY question_embedding <=> %s::vector
                    LIMIT 3
                """, (
                    question_embedding,
                    doc_id,
                    datetime.utcnow() - self.ttl,
                    question_embedding
                ))

                rows = cur.fetchall()

                # Check if any are above similarity threshold
                for row in rows:
                    similarity = row[8]

                    if similarity >= self.similarity_threshold:
                        print(f"   ✓ Semantic cache hit! Similarity: {similarity:.2%}")
                        print(f"     Original: {row[1][:60]}...")
                        print(f"     New:      {question[:60]}...")

                        # Increment hit count
                        cur.execute("""
                            UPDATE query_cache
                            SET hit_count = hit_count + 1,
                                last_accessed_at = NOW()
                            WHERE cache_key = %s
                        """, (row[0],))
                        self.db.conn.commit()

                        return CachedQuery(
                            cache_key=row[0],
                            question=row[1],
                            doc_id=row[2],
                            answer=row[3],
                            citations=json.loads(row[4]) if isinstance(row[4], str) else row[4],
                            created_at=row[5],
                            hit_count=row[6],
                            model_used=row[7] or "gpt-4o-mini"
                        )

                return None

        except Exception as e:
            print(f"⚠️  Semantic cache lookup failed: {e}")
            return None

    def cache_answer(
        self,
        question: str,
        doc_id: str,
        answer: str,
        citations: List[Dict[str, Any]],
        model_used: str = "gpt-4o-mini",
        question_embedding: Optional[List[float]] = None
    ) -> bool:
        """Store query result in cache.

        Args:
            question: User's question
            doc_id: Document ID
            answer: Generated answer
            citations: List of citation dicts
            model_used: Model name used for generation
            question_embedding: Optional question embedding for semantic matching

        Returns:
            True if cached successfully
        """
        cache_key = self._generate_cache_key(question, doc_id)

        # Prepare citations (keep essential fields only)
        citation_data = []
        for c in citations[:10]:  # Limit to 10 citations
            citation_data.append({
                'content': c.get('content', '')[:500],  # Truncate content
                'page_number': c.get('page_number'),
                'doc_title': c.get('doc_title'),
                'section_path': c.get('section_path'),
                'similarity_score': c.get('similarity_score')
            })

        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO query_cache (
                        cache_key,
                        question,
                        doc_id,
                        answer,
                        citations,
                        model_used,
                        question_embedding,
                        created_at,
                        last_accessed_at,
                        hit_count
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector, NOW(), NOW(), 0)
                    ON CONFLICT (cache_key) DO UPDATE
                    SET answer = EXCLUDED.answer,
                        citations = EXCLUDED.citations,
                        model_used = EXCLUDED.model_used,
                        question_embedding = EXCLUDED.question_embedding,
                        created_at = NOW(),
                        last_accessed_at = NOW()
                """, (
                    cache_key,
                    question,
                    doc_id,
                    answer,
                    json.dumps(citation_data),
                    model_used,
                    question_embedding
                ))

                self.db.conn.commit()
                return True

        except Exception as e:
            print(f"⚠️  Cache storage failed: {e}")
            return False

    def get_cache_stats(self, doc_id: Optional[str] = None) -> Dict[str, Any]:
        """Get cache statistics.

        Args:
            doc_id: Optional document ID filter

        Returns:
            Cache statistics dict
        """
        try:
            with self.db.conn.cursor() as cur:
                if doc_id:
                    # Stats for specific document
                    cur.execute("""
                        SELECT
                            COUNT(*) as total_cached,
                            SUM(hit_count) as total_hits,
                            AVG(hit_count) as avg_hits_per_query,
                            MAX(hit_count) as max_hits,
                            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as cached_24h
                        FROM query_cache
                        WHERE doc_id = %s
                          AND created_at > NOW() - INTERVAL '7 days'
                    """, (doc_id,))
                else:
                    # Overall stats
                    cur.execute("""
                        SELECT
                            COUNT(*) as total_cached,
                            SUM(hit_count) as total_hits,
                            AVG(hit_count) as avg_hits_per_query,
                            MAX(hit_count) as max_hits,
                            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as cached_24h
                        FROM query_cache
                        WHERE created_at > NOW() - INTERVAL '7 days'
                    """)

                row = cur.fetchone()

                if row:
                    return {
                        'total_cached_queries': row[0] or 0,
                        'total_cache_hits': row[1] or 0,
                        'avg_hits_per_query': float(row[2] or 0),
                        'max_hits': row[3] or 0,
                        'cached_last_24h': row[4] or 0,
                        'cache_hit_rate': (row[1] or 0) / max(row[0] or 1, 1)
                    }

                return {}

        except Exception as e:
            print(f"⚠️  Cache stats failed: {e}")
            return {}

    def invalidate_doc_cache(self, doc_id: str) -> int:
        """Invalidate all cache entries for a document.

        Use this when a document is updated/reprocessed.

        Args:
            doc_id: Document ID

        Returns:
            Number of entries invalidated
        """
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM query_cache
                    WHERE doc_id = %s
                """, (doc_id,))

                deleted = cur.rowcount
                self.db.conn.commit()

                print(f"   ✓ Invalidated {deleted} cached queries for {doc_id}")
                return deleted

        except Exception as e:
            print(f"⚠️  Cache invalidation failed: {e}")
            return 0

    def cleanup_old_entries(self, days: int = 7) -> int:
        """Remove cache entries older than specified days.

        Args:
            days: Age threshold in days

        Returns:
            Number of entries removed
        """
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    DELETE FROM query_cache
                    WHERE created_at < NOW() - INTERVAL '%s days'
                """, (days,))

                deleted = cur.rowcount
                self.db.conn.commit()

                print(f"   ✓ Cleaned up {deleted} old cache entries (>{days} days)")
                return deleted

        except Exception as e:
            print(f"⚠️  Cache cleanup failed: {e}")
            return 0


if __name__ == "__main__":
    # Test cache key generation
    cache = QueryCache(db_client=None, ttl_hours=24)

    test_questions = [
        "What is System Database?",
        "what is system database",
        "What is System Database ?",  # Different punctuation
        "Explain System Database",    # Different wording
    ]

    print("Cache Key Generation Test:")
    print("=" * 60)
    for q in test_questions:
        key = cache._generate_cache_key(q, "doc_123")
        print(f"{q:40} → {key[:16]}...")
