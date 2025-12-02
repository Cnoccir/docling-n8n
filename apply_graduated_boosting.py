"""Apply graduated boosting migration to Supabase."""
import os
import psycopg2

# Read the migration file
with open('migrations/009_add_topic_aware_search.sql', 'r', encoding='utf-8') as f:
    migration_sql = f.read()

# Connect to database
conn = psycopg2.connect(os.getenv('DATABASE_URL'))

try:
    with conn.cursor() as cur:
        print("🔄 Applying graduated boosting migration...")
        cur.execute(migration_sql)
        conn.commit()
        print("✅ Migration applied successfully!")
        
        # Test the function exists
        cur.execute("""
            SELECT proname, prosrc 
            FROM pg_proc 
            WHERE proname = 'search_chunks_hybrid_with_topics'
        """)
        result = cur.fetchone()
        
        if result:
            print(f"✅ Function '{result[0]}' exists")
            print(f"📝 Function contains 'graduated': {'graduated' in result[1]}")
            print(f"📝 Function contains '1.5::float': {'1.5::float' in result[1]}")
        else:
            print("❌ Function not found!")
            
finally:
    conn.close()
