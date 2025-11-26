"""Query cost tracking utilities."""
import time
from typing import Optional
from datetime import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'src'))

from database.db_client import DatabaseClient


# OpenAI Pricing (as of 2025)
# https://openai.com/api/pricing/
PRICING = {
    # Chat models
    'gpt-4o': {
        'prompt': 2.50 / 1_000_000,  # $2.50 per 1M tokens
        'completion': 10.00 / 1_000_000  # $10.00 per 1M tokens
    },
    'gpt-4o-mini': {
        'prompt': 0.150 / 1_000_000,  # $0.15 per 1M tokens
        'completion': 0.600 / 1_000_000  # $0.60 per 1M tokens
    },
    # Embedding models
    'text-embedding-3-small': {
        'input': 0.020 / 1_000_000  # $0.02 per 1M tokens
    },
    'text-embedding-3-large': {
        'input': 0.130 / 1_000_000  # $0.13 per 1M tokens
    },
    'text-embedding-ada-002': {
        'input': 0.100 / 1_000_000  # $0.10 per 1M tokens
    }
}


def calculate_cost(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0
) -> float:
    """
    Calculate cost for OpenAI API call.

    Args:
        model: Model name (e.g., 'gpt-4o-mini', 'text-embedding-3-small')
        prompt_tokens: Number of prompt/input tokens
        completion_tokens: Number of completion/output tokens

    Returns:
        Cost in USD
    """
    if model not in PRICING:
        print(f"Warning: Unknown model '{model}', cost calculation may be inaccurate")
        return 0.0

    pricing = PRICING[model]

    # For chat models (have prompt and completion pricing)
    if 'prompt' in pricing:
        prompt_cost = prompt_tokens * pricing['prompt']
        completion_cost = completion_tokens * pricing['completion']
        return prompt_cost + completion_cost

    # For embedding models (only input pricing)
    elif 'input' in pricing:
        return prompt_tokens * pricing['input']

    return 0.0


class CostTracker:
    """Context manager for tracking query costs."""

    def __init__(
        self,
        query_type: str,
        query_text: str = None,
        doc_id: str = None,
        model: str = None
    ):
        self.query_type = query_type
        self.query_text = query_text
        self.doc_id = doc_id
        self.model = model
        self.start_time = None
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.cost_usd = 0.0
        self.success = True
        self.error_message = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Calculate response time
        response_time_ms = int((time.time() - self.start_time) * 1000)

        # Handle errors
        if exc_type is not None:
            self.success = False
            self.error_message = str(exc_val)

        # Save to database
        self._save_to_db(response_time_ms)

        # Don't suppress exceptions
        return False

    def add_tokens(self, prompt_tokens: int, completion_tokens: int, model: str = None):
        """Add token counts and calculate cost."""
        if model:
            self.model = model

        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens

        # Calculate cost
        if self.model:
            self.cost_usd = calculate_cost(
                self.model,
                self.prompt_tokens,
                self.completion_tokens
            )

    def _save_to_db(self, response_time_ms: int):
        """Save query analytics to database."""
        try:
            db = DatabaseClient()
            with db:
                with db.conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO query_analytics (
                            query_type, doc_id, query_text, model_used,
                            tokens_prompt, tokens_completion, tokens_total,
                            cost_usd, response_time_ms, success, error_message
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        self.query_type,
                        self.doc_id,
                        self.query_text[:500] if self.query_text else None,  # Truncate long queries
                        self.model,
                        self.prompt_tokens,
                        self.completion_tokens,
                        self.total_tokens,
                        self.cost_usd,
                        response_time_ms,
                        self.success,
                        self.error_message[:500] if self.error_message else None
                    ))
                    db.conn.commit()
        except Exception as e:
            # Don't fail the request if analytics fails
            print(f"Failed to save query analytics: {e}")


def get_query_summary():
    """Get overall query analytics summary."""
    db = DatabaseClient()
    with db:
        with db.conn.cursor() as cur:
            cur.execute("SELECT * FROM query_analytics_summary")
            row = cur.fetchone()
            if row:
                return {
                    'total_queries': row[0],
                    'total_tokens_used': row[1],
                    'total_cost_usd': float(row[2]) if row[2] else 0.0,
                    'avg_cost_per_query': float(row[3]) if row[3] else 0.0,
                    'avg_response_time_ms': float(row[4]) if row[4] else 0.0,
                    'successful_queries': row[5],
                    'failed_queries': row[6],
                    'last_query_at': row[7]
                }
    return None


def get_daily_costs(days: int = 7):
    """Get daily cost breakdown."""
    db = DatabaseClient()
    with db:
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM daily_query_costs
                WHERE date >= CURRENT_DATE - INTERVAL '%s days'
                ORDER BY date DESC, query_type
            """, (days,))

            results = []
            for row in cur.fetchall():
                results.append({
                    'date': row[0],
                    'query_type': row[1],
                    'query_count': row[2],
                    'total_tokens': row[3],
                    'total_cost_usd': float(row[4]) if row[4] else 0.0,
                    'avg_response_time_ms': float(row[5]) if row[5] else 0.0,
                    'successful_queries': row[6],
                    'failed_queries': row[7]
                })
            return results
    return []
