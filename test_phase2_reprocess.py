"""Test Phase 2: Reprocess a document and verify topic tagging."""
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_client import DatabaseClient


def find_test_document():
    """Find a small test document to reprocess."""
    db = DatabaseClient()
    try:
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT id, title, filename, total_pages, total_chunks 
                FROM document_index 
                WHERE title ILIKE '%system database%' 
                   OR title ILIKE '%multi-tier%'
                ORDER BY total_pages ASC 
                LIMIT 1
            """)
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0],
                    'title': row[1],
                    'filename': row[2],
                    'pages': row[3],
                    'chunks': row[4]
                }
    finally:
        db.conn.close()
    return None


def verify_topics(doc_id: str):
    """Verify topics were tagged correctly."""
    db = DatabaseClient()
    try:
        print(f"\n📊 Verifying topics for document: {doc_id}\n")
        
        # Check chunks
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT topic, topics, COUNT(*) as count
                FROM chunks 
                WHERE doc_id = %s 
                  AND (topic IS NOT NULL OR array_length(topics, 1) > 0)
                GROUP BY topic, topics
                ORDER BY count DESC
            """, (doc_id,))
            
            chunk_results = cur.fetchall()
            print(f"✅ Chunks with topics: {len(chunk_results)} distinct topic combinations")
            for topic, topics, count in chunk_results[:10]:  # Show top 10
                topics_str = ', '.join(topics) if topics else ''
                print(f"   - topic={topic}, topics=[{topics_str}] → {count} chunks")
        
        # Check images
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(topic) as with_topic,
                       COUNT(CASE WHEN array_length(topics, 1) > 0 THEN 1 END) as with_topics
                FROM images 
                WHERE doc_id = %s
            """, (doc_id,))
            
            total, with_topic, with_topics = cur.fetchone()
            print(f"\n✅ Images: {total} total, {with_topic} with topic, {with_topics} with topics array")
        
        # Check tables
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as total,
                       COUNT(topic) as with_topic,
                       COUNT(CASE WHEN array_length(topics, 1) > 0 THEN 1 END) as with_topics
                FROM document_tables 
                WHERE doc_id = %s
            """, (doc_id,))
            
            row = cur.fetchone()
            if row:
                total, with_topic, with_topics = row
                print(f"✅ Tables: {total} total, {with_topic} with topic, {with_topics} with topics array")
        
        # Sample specific chunks
        print("\n📝 Sample chunks with topics:")
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT LEFT(content, 100) as snippet, topic, topics
                FROM chunks 
                WHERE doc_id = %s 
                  AND topic IS NOT NULL
                ORDER BY page_number
                LIMIT 5
            """, (doc_id,))
            
            for snippet, topic, topics in cur.fetchall():
                topics_str = ', '.join(topics) if topics else ''
                print(f"\n   Topic: {topic}")
                print(f"   Topics: [{topics_str}]")
                print(f"   Content: {snippet}...")
        
        return True
    
    except Exception as e:
        print(f"❌ Error verifying topics: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        db.conn.close()


def test_ingestion_with_topics():
    """Test that a document gets processed with topics."""
    print("=" * 80)
    print("PHASE 2 TEST: Document Reprocessing with Topic Tagging")
    print("=" * 80)
    
    # Find test document
    doc = find_test_document()
    if not doc:
        print("❌ No suitable test document found")
        return False
    
    print(f"\n📄 Found test document:")
    print(f"   ID: {doc['id']}")
    print(f"   Title: {doc['title']}")
    print(f"   Pages: {doc['pages']}, Chunks: {doc['chunks']}")
    
    # For now, just verify topics on existing document
    # (Full reprocessing requires uploading file via API)
    print(f"\n⏳ Checking if document already has topics...")
    
    db = DatabaseClient()
    try:
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM chunks 
                WHERE doc_id = %s AND topic IS NOT NULL
            """, (doc['id'],))
            chunks_with_topics = cur.fetchone()[0]
            
            if chunks_with_topics == 0:
                print(f"   ℹ️  Document needs reprocessing (0 chunks have topics)")
                print(f"   ℹ️  Please reprocess via API with reprocess=true")
                return False
            else:
                print(f"   ✅ Document already has topics on {chunks_with_topics} chunks")
                return verify_topics(doc['id'])
    
    finally:
        db.conn.close()


if __name__ == "__main__":
    success = test_ingestion_with_topics()
    sys.exit(0 if success else 1)
