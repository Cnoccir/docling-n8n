"""Retrieval quality metrics and monitoring.

Tracks retrieval performance to identify issues and measure improvements.
"""
import json
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np


class RetrievalMetrics:
    """Track and analyze retrieval quality metrics."""

    def __init__(self, db_client):
        """Initialize retrieval metrics tracker.

        Args:
            db_client: DatabaseClient instance
        """
        self.db = db_client

    def log_retrieval(
        self,
        question: str,
        query_categories: List[str],
        results: List[Dict[str, Any]],
        top_k: int,
        query_type: str = 'unknown',
        complexity: str = 'moderate',
        doc_id: Optional[str] = None,
        retrieval_strategy: str = 'hybrid',
        additional_metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Log retrieval results for analysis.

        Args:
            question: User's question
            query_categories: Categories from classifier
            results: Retrieved chunks
            top_k: Number of results requested
            query_type: Type of query (definition, comparison, etc.)
            complexity: Query complexity (simple, moderate, complex)
            doc_id: Optional document ID
            retrieval_strategy: Strategy used (hybrid, multi-hop, etc.)
            additional_metadata: Extra metadata to log

        Returns:
            Query ID for tracking
        """
        query_id = str(uuid.uuid4())

        # Calculate metrics
        metrics = self._calculate_metrics(results, query_categories, top_k)

        # Add metadata
        metrics.update({
            'query_type': query_type,
            'complexity': complexity,
            'retrieval_strategy': retrieval_strategy,
            'question_length': len(question),
            'question_word_count': len(question.split())
        })

        if additional_metadata:
            metrics.update(additional_metadata)

        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO retrieval_metrics (
                        query_id,
                        question,
                        doc_id,
                        categories,
                        metrics,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    query_id,
                    question,
                    doc_id,
                    json.dumps(query_categories),
                    json.dumps(metrics),
                    datetime.utcnow()
                ))

                self.db.conn.commit()

            return query_id

        except Exception as e:
            print(f"⚠️  Failed to log retrieval metrics: {e}")
            return query_id

    def _calculate_metrics(
        self,
        results: List[Dict[str, Any]],
        query_categories: List[str],
        top_k: int
    ) -> Dict[str, Any]:
        """Calculate retrieval quality metrics.

        Args:
            results: Retrieved chunks
            query_categories: Query categories
            top_k: Requested top_k

        Returns:
            Metrics dict
        """
        if not results:
            return {
                'results_count': 0,
                'avg_score': 0.0,
                'topic_coverage': 0.0,
                'score_distribution': [],
                'score_variance': 0.0
            }

        # Score distribution (top 5)
        scores = [float(r.get('combined_score') or r.get('similarity') or r.get('final_score', 0)) for r in results]
        top_5_scores = scores[:5]

        # Topic coverage: % of top results matching query categories
        topic_coverage = self._calc_topic_coverage(results, query_categories)

        # Score variance (consistency indicator)
        score_variance = float(np.var(top_5_scores)) if len(top_5_scores) > 1 else 0.0

        # Topic diversity (unique topics in top 5)
        topics_in_top_5 = set()
        for r in results[:5]:
            if r.get('topic'):
                topics_in_top_5.add(r['topic'])
            if r.get('topics'):
                topics_in_top_5.update(r['topics'])

        return {
            'results_count': len(results),
            'requested_top_k': top_k,
            'avg_score': float(np.mean(scores)) if scores else 0.0,
            'max_score': float(max(scores)) if scores else 0.0,
            'min_score': float(min(scores)) if scores else 0.0,
            'score_distribution': top_5_scores,
            'score_variance': score_variance,
            'topic_coverage': topic_coverage,
            'topic_diversity': len(topics_in_top_5),
            'unique_topics': list(topics_in_top_5)
        }

    def _calc_topic_coverage(
        self,
        results: List[Dict[str, Any]],
        query_categories: List[str]
    ) -> float:
        """Calculate what % of top results match query categories.

        Args:
            results: Retrieved chunks
            query_categories: Expected categories

        Returns:
            Coverage score (0.0-1.0)
        """
        if not results or not query_categories:
            return 0.0

        # Map query categories to topics
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent))
        from topic_constants import CATEGORY_TO_TOPIC_MAP

        expected_topics = set()
        for category in query_categories:
            topics = CATEGORY_TO_TOPIC_MAP.get(category, [])
            expected_topics.update(topics)

        if not expected_topics:
            return 1.0  # No topic expectations

        # Check top 5 results
        matched = 0
        for r in results[:5]:
            chunk_topic = r.get('topic')
            chunk_topics = r.get('topics', [])

            if chunk_topic in expected_topics:
                matched += 1
            elif any(t in expected_topics for t in chunk_topics):
                matched += 1

        return matched / min(5, len(results))

    def get_retrieval_stats(
        self,
        days: int = 7,
        doc_id: Optional[str] = None,
        query_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get retrieval statistics for analysis.

        Args:
            days: Number of days to analyze
            doc_id: Optional document filter
            query_type: Optional query type filter

        Returns:
            Statistics dict
        """
        try:
            with self.db.conn.cursor() as cur:
                # Build WHERE clause
                where_clauses = [f"created_at > NOW() - INTERVAL '{days} days'"]
                params = []

                if doc_id:
                    where_clauses.append("doc_id = %s")
                    params.append(doc_id)

                if query_type:
                    where_clauses.append("metrics->>'query_type' = %s")
                    params.append(query_type)

                where_sql = " AND ".join(where_clauses)

                # Get overall stats
                cur.execute(f"""
                    SELECT
                        COUNT(*) as total_queries,
                        AVG((metrics->>'avg_score')::float) as avg_retrieval_score,
                        AVG((metrics->>'topic_coverage')::float) as avg_topic_coverage,
                        AVG((metrics->>'topic_diversity')::float) as avg_topic_diversity,
                        AVG((metrics->>'score_variance')::float) as avg_score_variance
                    FROM retrieval_metrics
                    WHERE {where_sql}
                """, tuple(params))

                row = cur.fetchone()

                if row:
                    stats = {
                        'total_queries': row[0] or 0,
                        'avg_retrieval_score': float(row[1] or 0),
                        'avg_topic_coverage': float(row[2] or 0),
                        'avg_topic_diversity': float(row[3] or 0),
                        'avg_score_variance': float(row[4] or 0),
                        'period_days': days
                    }

                    # Get category breakdown
                    cur.execute(f"""
                        SELECT
                            category,
                            COUNT(*) as query_count,
                            AVG((metrics->>'topic_coverage')::float) as avg_coverage
                        FROM retrieval_metrics,
                             jsonb_array_elements_text(categories) as category
                        WHERE {where_sql}
                        GROUP BY category
                        ORDER BY query_count DESC
                    """, tuple(params))

                    category_stats = []
                    for cat_row in cur.fetchall():
                        category_stats.append({
                            'category': cat_row[0],
                            'query_count': cat_row[1],
                            'avg_coverage': float(cat_row[2] or 0)
                        })

                    stats['category_breakdown'] = category_stats

                    return stats

                return {}

        except Exception as e:
            print(f"⚠️  Failed to get retrieval stats: {e}")
            return {}

    def get_low_quality_queries(
        self,
        min_coverage: float = 0.6,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Find queries with low topic coverage (potential issues).

        Args:
            min_coverage: Coverage threshold (queries below this)
            limit: Maximum queries to return

        Returns:
            List of low-quality query dicts
        """
        try:
            with self.db.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        query_id,
                        question,
                        categories,
                        metrics->>'topic_coverage' as coverage,
                        metrics->>'avg_score' as avg_score,
                        created_at
                    FROM retrieval_metrics
                    WHERE (metrics->>'topic_coverage')::float < %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (min_coverage, limit))

                issues = []
                for row in cur.fetchall():
                    issues.append({
                        'query_id': row[0],
                        'question': row[1],
                        'categories': json.loads(row[2]) if isinstance(row[2], str) else row[2],
                        'coverage': float(row[3]),
                        'avg_score': float(row[4]),
                        'created_at': row[5]
                    })

                return issues

        except Exception as e:
            print(f"⚠️  Failed to get low-quality queries: {e}")
            return []

    def generate_report(self, days: int = 7) -> str:
        """Generate human-readable retrieval quality report.

        Args:
            days: Number of days to analyze

        Returns:
            Formatted report string
        """
        stats = self.get_retrieval_stats(days=days)

        if not stats:
            return "No retrieval data available."

        lines = []
        lines.append("=" * 80)
        lines.append(f"RETRIEVAL QUALITY REPORT (Last {days} days)")
        lines.append("=" * 80)
        lines.append(f"Total Queries: {stats['total_queries']}")
        lines.append(f"Avg Retrieval Score: {stats['avg_retrieval_score']:.3f}")
        lines.append(f"Avg Topic Coverage: {stats['avg_topic_coverage']:.1%}")
        lines.append(f"Avg Topic Diversity: {stats['avg_topic_diversity']:.1f} topics/query")
        lines.append(f"Avg Score Variance: {stats['avg_score_variance']:.4f}")
        lines.append("")

        if stats.get('category_breakdown'):
            lines.append("Category Breakdown:")
            lines.append("-" * 60)
            for cat in stats['category_breakdown'][:10]:
                lines.append(f"  {cat['category']:20} | Queries: {cat['query_count']:4} | Coverage: {cat['avg_coverage']:.1%}")
            lines.append("")

        # Check for issues
        issues = self.get_low_quality_queries(min_coverage=0.6, limit=5)
        if issues:
            lines.append(f"⚠️  LOW COVERAGE QUERIES ({len(issues)} found):")
            lines.append("-" * 60)
            for issue in issues[:5]:
                lines.append(f"  • {issue['question'][:60]}...")
                lines.append(f"    Coverage: {issue['coverage']:.1%} | Categories: {', '.join(issue['categories'])}")
            lines.append("")

        lines.append("=" * 80)

        return "\n".join(lines)


if __name__ == "__main__":
    print("Retrieval Metrics System")
    print("=" * 60)
    print("This module tracks retrieval quality for monitoring and improvement.")
    print("")
    print("Metrics tracked:")
    print("  • Topic coverage (% of results matching query intent)")
    print("  • Score distribution and variance")
    print("  • Topic diversity")
    print("  • Low-quality query detection")
