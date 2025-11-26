#!/usr/bin/env python3
"""Clear queued/failed jobs from database."""
import sys

sys.path.insert(0, '/app/src')

from database.db_client import DatabaseClient

db = DatabaseClient()
with db:
    with db.conn.cursor() as cur:
        cur.execute("DELETE FROM jobs WHERE status IN ('queued', 'failed', 'cancelled')")
        db.conn.commit()
        print(f'✅ Deleted {cur.rowcount} jobs')
