#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app/src')
from database.db_client import DatabaseClient

db = DatabaseClient()
with db:
    with db.conn.cursor() as cur:
        cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
        print("\nJob counts by status:")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]}")
