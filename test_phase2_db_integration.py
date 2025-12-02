"""Test Phase 2 database integration: save and retrieve topics."""
import sys
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_client import DatabaseClient
from database.models import Chunk


def test_db_integration():
    """Test saving and retrieving chunks with topics."""
    print("=" * 80)
    print("PHASE 2 DATABASE INTEGRATION TEST")
    print("=" * 80)
    
    db = DatabaseClient()
    test_doc_id = f"test_phase2_{uuid.uuid4().hex[:8]}"
    
    try:
        # Create test chunks with topics
        test_chunks = [
            Chunk(
                id=f"{test_doc_id}_chunk_001",
                doc_id=test_doc_id,
                content="The System Database enables multi-tier architecture coordination.",
                page_number=1,
                section_id="sec_001",
                parent_section_id=None,
                section_path=["System Database", "Overview"],
                section_level=2,
                element_type="text",
                metadata={},
                bbox=None,
                topic="system_database",  # NEW: Phase 2
                topics=["system_database", "multi_tier_architecture"]  # NEW: Phase 2
            ),
            Chunk(
                id=f"{test_doc_id}_chunk_002",
                doc_id=test_doc_id,
                content="Graphics design with PX pages and tag dictionaries.",
                page_number=1,
                section_id="sec_002",
                parent_section_id=None,
                section_path=["Graphics"],
                section_level=1,
                element_type="text",
                metadata={},
                bbox=None,
                topic="graphics",  # NEW: Phase 2
                topics=["graphics"]  # NEW: Phase 2
            ),
            Chunk(
                id=f"{test_doc_id}_chunk_003",
                doc_id=test_doc_id,
                content="Backup and restore using provisioning tools.",
                page_number=2,
                section_id="sec_003",
                parent_section_id=None,
                section_path=["Provisioning"],
                section_level=1,
                element_type="text",
                metadata={},
                bbox=None,
                topic="provisioning",  # NEW: Phase 2
                topics=["provisioning"]  # NEW: Phase 2
            )
        ]
        
        # Generate dummy embeddings (random vectors)
        import numpy as np
        embeddings = [np.random.rand(1536).tolist() for _ in test_chunks]
        
        print(f"\n📝 Saving {len(test_chunks)} test chunks with topics...")
        db.save_chunks(test_chunks, embeddings)
        print(f"✅ Chunks saved successfully")
        
        # Verify chunks were saved with topics
        print(f"\n🔍 Verifying topics in database...")
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT id, topic, topics 
                FROM chunks 
                WHERE doc_id = %s
                ORDER BY id
            """, (test_doc_id,))
            
            rows = cur.fetchall()
            
            if len(rows) != len(test_chunks):
                print(f"❌ Expected {len(test_chunks)} chunks, found {len(rows)}")
                return False
            
            print(f"\n📊 Retrieved {len(rows)} chunks:")
            for row in rows:
                chunk_id, topic, topics = row
                print(f"\n  {chunk_id}")
                print(f"    topic:  {topic}")
                print(f"    topics: {topics}")
                
                # Verify topics match what we saved
                original_chunk = next(c for c in test_chunks if c.id == chunk_id)
                if topic != original_chunk.topic:
                    print(f"    ❌ topic mismatch: expected {original_chunk.topic}, got {topic}")
                    return False
                if topics != original_chunk.topics:
                    print(f"    ❌ topics mismatch: expected {original_chunk.topics}, got {topics}")
                    return False
                
                print(f"    ✅ Topics match")
        
        # Test topic filtering query
        print(f"\n🔍 Testing topic filtering...")
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM chunks 
                WHERE doc_id = %s AND topic = 'system_database'
            """, (test_doc_id,))
            
            count = cur.fetchone()[0]
            print(f"  Chunks with topic='system_database': {count}")
            if count != 1:
                print(f"  ❌ Expected 1 chunk, got {count}")
                return False
            print(f"  ✅ Topic filtering works")
        
        # Test topics array filtering
        print(f"\n🔍 Testing topics array filtering...")
        with db.conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM chunks 
                WHERE doc_id = %s 
                  AND topics && ARRAY['multi_tier_architecture']
            """, (test_doc_id,))
            
            count = cur.fetchone()[0]
            print(f"  Chunks with 'multi_tier_architecture' in topics: {count}")
            if count != 1:
                print(f"  ❌ Expected 1 chunk, got {count}")
                return False
            print(f"  ✅ Topics array filtering works (GIN index)")
        
        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED - Phase 2 database integration verified!")
        print("=" * 80)
        return True
    
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Cleanup
        try:
            with db.conn.cursor() as cur:
                cur.execute("DELETE FROM chunks WHERE doc_id = %s", (test_doc_id,))
                db.conn.commit()
            print(f"\n🧹 Test data cleaned up")
        except Exception as e:
            print(f"⚠️  Cleanup failed: {e}")
        
        db.conn.close()


if __name__ == "__main__":
    success = test_db_integration()
    sys.exit(0 if success else 1)
