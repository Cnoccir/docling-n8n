"""Analytics API endpoints - Query cost tracking and statistics."""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, date

from app.utils.cost_tracker import get_query_summary, get_daily_costs

router = APIRouter()


class QuerySummary(BaseModel):
    """Overall query analytics summary."""
    total_queries: int
    total_tokens_used: int
    total_cost_usd: float
    avg_cost_per_query: float
    avg_response_time_ms: float
    successful_queries: int
    failed_queries: int
    last_query_at: Optional[datetime]


class DailyCostBreakdown(BaseModel):
    """Daily cost breakdown by query type."""
    date: date
    query_type: str
    query_count: int
    total_tokens: int
    total_cost_usd: float
    avg_response_time_ms: float
    successful_queries: int
    failed_queries: int


@router.get("/summary", response_model=QuerySummary)
def get_analytics_summary():
    """
    Get overall query analytics summary.

    Returns:
        - Total queries executed
        - Total tokens used
        - Total cost (USD)
        - Average cost per query
        - Average response time
        - Success/failure counts
        - Last query timestamp
    """
    summary = get_query_summary()
    if not summary:
        return QuerySummary(
            total_queries=0,
            total_tokens_used=0,
            total_cost_usd=0.0,
            avg_cost_per_query=0.0,
            avg_response_time_ms=0.0,
            successful_queries=0,
            failed_queries=0,
            last_query_at=None
        )
    return QuerySummary(**summary)


@router.get("/daily", response_model=List[DailyCostBreakdown])
def get_daily_breakdown(
    days: int = Query(7, ge=1, le=90, description="Number of days to retrieve")
):
    """
    Get daily cost breakdown by query type.

    Args:
        days: Number of days to retrieve (1-90, default: 7)

    Returns:
        List of daily breakdowns showing costs by query type
    """
    daily_costs = get_daily_costs(days=days)
    return [DailyCostBreakdown(**item) for item in daily_costs]


@router.get("/cost-by-type")
def get_cost_by_type():
    """
    Get total cost breakdown by query type.

    Returns:
        Dictionary mapping query types to their total costs
    """
    from database.db_client import DatabaseClient

    db = DatabaseClient()
    with db:
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT
                    query_type,
                    COUNT(*) as query_count,
                    SUM(tokens_total) as total_tokens,
                    SUM(cost_usd) as total_cost_usd,
                    AVG(cost_usd) as avg_cost_usd,
                    AVG(response_time_ms) as avg_response_time_ms
                FROM query_analytics
                GROUP BY query_type
                ORDER BY total_cost_usd DESC
            """)

            results = []
            for row in cur.fetchall():
                results.append({
                    'query_type': row[0],
                    'query_count': row[1],
                    'total_tokens': row[2],
                    'total_cost_usd': float(row[3]) if row[3] else 0.0,
                    'avg_cost_usd': float(row[4]) if row[4] else 0.0,
                    'avg_response_time_ms': float(row[5]) if row[5] else 0.0
                })

            return {
                'query_types': results,
                'total_cost_usd': sum(r['total_cost_usd'] for r in results),
                'total_queries': sum(r['query_count'] for r in results)
            }
