"""Phase 3 End-to-End Test: Niagara Multi-Tier Query with Topic-Aware Search."""
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent / 'backend'))
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_client import DatabaseClient
from utils.embeddings import EmbeddingGenerator
from app.utils.query_classifier import classify_query
from app.utils.query_rewriter import rewrite_query


# Category to topic mapping (from chat_multimodal.py)
CATEGORY_TO_TOPIC_MAP = {
    'architecture': ['system_database', 'multi_tier_architecture'],
    'graphics': ['graphics'],
    'provisioning': ['provisioning'],
    'troubleshooting': ['troubleshooting'],
    'configuration': ['configuration'],
    'hardware': ['hardware']
}

def map_categories_to_topics(categories):
    """Map query categories to include/exclude topic lists."""
    include_topics = []
    for category in categories:
        topics = CATEGORY_TO_TOPIC_MAP.get(category, [])
        include_topics.extend(topics)
    
    include_topics = list(set(include_topics))
    
    exclude_topics = []
    if 'architecture' in categories or 'graphics' in categories:
        if 'provisioning' not in categories:
            exclude_topics.append('provisioning')
    
    return include_topics, exclude_topics


def test_niagara_query():
    """Test the failing Niagara multi-tier architecture query."""
    print("=" * 80)
    print("PHASE 3 TEST: Niagara Multi-Tier Architecture Query")
    print("=" * 80)
    
    # The failing query from the plan
    query = "design system that spans multiple supervisors and rolls up to one virtual machine help me determine how to accomplish this correctly and design the system and graphics"
    
    print(f"\n📝 Original Query:")
    print(f"   {query}")
    
    # Step 1: Classify query
    print(f"\n📊 Step 1: Query Classification")
    categories = classify_query(query, use_llm=False)  # Use keyword for speed
    print(f"   Categories: {categories}")
    
    # Step 2: Rewrite query
    print(f"\n✍️  Step 2: Query Rewriting")
    rewritten = rewrite_query(query, categories)
    print(f"   Original:  {query[:80]}...")
    print(f"   Rewritten: {rewritten[:80]}...")
    
    # Step 3: Map to topics
    print(f"\n🔖 Step 3: Topic Mapping")
    include_topics, exclude_topics = map_categories_to_topics(categories)
    print(f"   Include topics: {include_topics}")
    print(f"   Exclude topics: {exclude_topics}")
    
    # Step 4: Generate embedding
    print(f"\n🧮 Step 4: Generate Query Embedding")
    embedding_gen = EmbeddingGenerator()
    query_embedding = embedding_gen.generate_embeddings([query])[0]
    print(f"   Embedding generated: {len(query_embedding)} dimensions")
    
    # Step 5: Search WITHOUT topics (baseline)
    print(f"\n🔍 Step 5: BASELINE Search (no topic filtering)")
    db = DatabaseClient()
    try:
        baseline_results = db.search_chunks_hybrid(
            query_embedding=query_embedding,
            query_text=rewritten,
            doc_id=None,
            semantic_weight=0.5,
            keyword_weight=0.5,
            top_k=10
        )
        
        print(f"   Found {len(baseline_results)} results")
        print(f"\n   Top 5 results (BASELINE - no filtering):")
        for i, result in enumerate(baseline_results[:5], 1):
            topic = result.get('topic', 'N/A')
            topics = result.get('topics', [])
            score = result.get('combined_score', 0)
            content_preview = result['content'][:80].replace('\n', ' ')
            
            # Check if contaminated (provisioning in architecture query)
            is_contaminated = topic == 'provisioning' or 'provisioning' in (topics or [])
            contamination_flag = " ⚠️  CONTAMINATION" if is_contaminated else ""
            
            print(f"   {i}. score={score:.3f}, topic={topic}, topics={topics}{contamination_flag}")
            print(f"      \"{content_preview}...\"")
        
        # Count contamination
        provisioning_count = sum(
            1 for r in baseline_results[:5] 
            if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or [])
        )
        contamination_rate = (provisioning_count / 5) * 100 if baseline_results else 0
        print(f"\n   ⚠️  Contamination rate (top 5): {contamination_rate:.0f}% ({provisioning_count}/5 chunks)")
    
    finally:
        db.conn.close()
    
    # Step 6: Search WITH topics (Phase 3)
    print(f"\n🚀 Step 6: PHASE 3 Search (with topic filtering/boosting)")
    db = DatabaseClient()
    try:
        phase3_results = db.search_chunks_hybrid_with_topics(
            query_embedding=query_embedding,
            query_text=rewritten,
            doc_id=None,
            include_topics=include_topics,
            exclude_topics=exclude_topics,
            semantic_weight=0.5,
            keyword_weight=0.5,
            top_k=10
        )
        
        print(f"   Found {len(phase3_results)} results")
        print(f"\n   Top 5 results (PHASE 3 - with filtering/boosting):")
        for i, result in enumerate(phase3_results[:5], 1):
            topic = result.get('topic', 'N/A')
            topics = result.get('topics', [])
            boost = result.get('topic_boost', 1.0)
            score = result.get('final_score', 0)
            content_preview = result['content'][:80].replace('\n', ' ')
            
            boost_indicator = " 🚀" if boost > 1.0 else ""
            
            print(f"   {i}. score={score:.3f}, boost={boost:.1f}x{boost_indicator}, topic={topic}, topics={topics}")
            print(f"      \"{content_preview}...\"")
        
        # Count contamination
        provisioning_count = sum(
            1 for r in phase3_results[:5] 
            if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or [])
        )
        contamination_rate = (provisioning_count / 5) * 100 if phase3_results else 0
        print(f"\n   ✅ Contamination rate (top 5): {contamination_rate:.0f}% ({provisioning_count}/5 chunks)")
    
    finally:
        db.conn.close()
    
    # Step 7: Compare results
    print(f"\n" + "=" * 80)
    print("RESULTS COMPARISON")
    print("=" * 80)
    
    baseline_contamination = sum(
        1 for r in baseline_results[:5] 
        if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or [])
    )
    phase3_contamination = sum(
        1 for r in phase3_results[:5] 
        if r.get('topic') == 'provisioning' or 'provisioning' in (r.get('topics') or [])
    )
    
    print(f"\n📊 Baseline (no topic filtering):")
    print(f"   Provisioning contamination: {baseline_contamination}/5 ({(baseline_contamination/5)*100:.0f}%)")
    
    print(f"\n✅ Phase 3 (topic-aware search):")
    print(f"   Provisioning contamination: {phase3_contamination}/5 ({(phase3_contamination/5)*100:.0f}%)")
    
    if phase3_contamination < baseline_contamination:
        reduction = ((baseline_contamination - phase3_contamination) / baseline_contamination * 100) if baseline_contamination > 0 else 0
        print(f"\n🎉 Improvement: {reduction:.0f}% reduction in contamination!")
        print(f"✅ Phase 3 topic-aware search is working!")
        return True
    elif phase3_contamination == 0 and baseline_contamination == 0:
        print(f"\n✅ No contamination in either search - topics working correctly!")
        return True
    else:
        print(f"\n⚠️  No improvement detected")
        return False


if __name__ == "__main__":
    success = test_niagara_query()
    sys.exit(0 if success else 1)
