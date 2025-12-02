"""Run new migrations for improved RAG system.

Applies migrations 010-011:
- 010: Query cache table
- 011: Retrieval metrics table

Usage:
    python run_new_migrations.py
"""
import psycopg2
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()


def run_migration(conn, migration_file: Path):
    """Run a single migration file.

    Args:
        conn: Database connection
        migration_file: Path to SQL migration file
    """
    print(f"\n📝 Running migration: {migration_file.name}")

    with open(migration_file, 'r') as f:
        sql = f.read()

    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()
        print(f"   ✅ Migration {migration_file.name} completed successfully")
        return True

    except Exception as e:
        print(f"   ❌ Migration {migration_file.name} failed: {e}")
        conn.rollback()
        return False


def main():
    """Run all new migrations."""
    print("=" * 80)
    print("APPLYING NEW RAG IMPROVEMENTS MIGRATIONS")
    print("=" * 80)

    # Connect to database
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("❌ DATABASE_URL not found in environment")
        return

    conn = psycopg2.connect(db_url)
    print("✅ Connected to database")

    # Get migration files
    migrations_dir = Path(__file__).parent / 'migrations'
    new_migrations = [
        migrations_dir / '010_add_query_cache.sql',
        migrations_dir / '011_add_retrieval_metrics.sql'
    ]

    # Run migrations
    success_count = 0
    for migration_file in new_migrations:
        if not migration_file.exists():
            print(f"⚠️  Migration file not found: {migration_file}")
            continue

        if run_migration(conn, migration_file):
            success_count += 1

    # Summary
    print("\n" + "=" * 80)
    print(f"MIGRATION SUMMARY: {success_count}/{len(new_migrations)} successful")
    print("=" * 80)

    if success_count == len(new_migrations):
        print("✅ All migrations completed successfully!")
        print("\nNew features enabled:")
        print("  • Query caching (reduces cost for repeated queries)")
        print("  • Retrieval quality metrics (monitors performance)")
    else:
        print("⚠️  Some migrations failed. Check errors above.")

    conn.close()


if __name__ == "__main__":
    main()
