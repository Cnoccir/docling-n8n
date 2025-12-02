"""Test contamination reduction with mixed query."""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent / 'backend'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_client import DatabaseClient
from utils.embeddings import EmbeddingGenerator


def test_contamination():
    """Test that provisioning is excluded from architecture queries."""
    print("=" * 80)
    print("CONTAMINATION REDUCTION TEST")
    print("=" * 80)
    
    # Query that might accidentally pull provisioning content
    query = "system architecture backup provisioning"
    
    print(f"\nQuery: {query}")
    print("(Contains both 'architecture' and 'provisioning' keywords)")
    
    embedding_gen = EmbeddingGenerator()
    query_embedding = embedding_gen.generate_embeddings([query])[0]
    
    # Baseline search (no filtering)
    print(f"\n" + "=" * 80)
    print("BASELINE SEARCH (no topic filtering)")
    print("=" * 80)
    db = DatabaseClient()
    try:
        baseline = db.search_chunks_hybrid(
            query_embedding=query_embedding,
            query_text=query,
            doc_id=None,
            semantic_weight=0.5,
            keyword_weight=0.5,
            top_k=10
        )
        
        prov_count = sum(1 for r in baseline[:5] if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or []))
        print(f"\nTop 5 results:")
        for i, r in enumerate(baseline[:5], 1):
            topic = r.get('topic', 'N/A')
            flag = " ⚠️ PROVISIONING" if topic == 'provisioning' or 'provisioning' in (r.get('topics') or []) else ""
            print(f"  {i}. topic={topic}{flag}")
        
        print(f"\nProvisioning contamination: {prov_count}/5 ({prov_count*20}%)")
    finally:
        db.conn.close()
    
    # Phase 3 search (exclude provisioning for architecture queries)
    print(f"\n" + "=" * 80)
    print("PHASE 3 SEARCH (exclude provisioning)")
    print("=" * 80)
    db = DatabaseClient()
    try:
        phase3 = db.search_chunks_hybrid_with_topics(
            query_embedding=query_embedding,
            query_text=query,
            doc_id=None,
            include_topics=['system_database', 'multi_tier_architecture'],
            exclude_topics=['provisioning'],  # KEY: Exclude provisioning
            semantic_weight=0.5,
            keyword_weight=0.5,
            top_k=10
        )
        
        prov_count = sum(1 for r in phase3[:5] if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or []))
        print(f"\nTop 5 results:")
        for i, r in enumerate(phase3[:5], 1):
            topic = r.get('topic', 'N/A')
            boost = r.get('topic_boost', 1.0)
            boost_str = f", boost={boost:.1f}x" if boost > 1.0 else ""
            flag = " ⚠️ PROVISIONING" if topic == 'provisioning' or 'provisioning' in (r.get('topics') or []) else " ✅"
            print(f"  {i}. topic={topic}{boost_str}{flag}")
        
        print(f"\nProvisioning contamination: {prov_count}/5 ({prov_count*20}%)")
    finally:
        db.conn.close()
    
    # Summary
    baseline_prov = sum(1 for r in baseline[:5] if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or []))
    phase3_prov = sum(1 for r in phase3[:5] if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or []))
    
    print(f"\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"\nBaseline: {baseline_prov}/5 provisioning chunks ({baseline_prov*20}%)")
    print(f"Phase 3:  {phase3_prov}/5 provisioning chunks ({phase3_prov*20}%)")
    
    if phase3_prov < baseline_prov:
        reduction = ((baseline_prov - phase3_prov) / baseline_prov * 100) if baseline_prov > 0 else 0
        print(f"\n🎉 {reduction:.0f}% reduction in contamination!")
        return True
    elif phase3_prov == 0:
        print(f"\n✅ Perfect! 0% contamination in Phase 3")
        return True
    else:
        print(f"\n⚠️ No improvement")
        return False


if __name__ == "__main__":
    success = test_contamination()
    sys.exit(0 if success else 1)
