"""Test graduated boosting with cross-domain queries."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_client import DatabaseClient
from utils.embeddings import EmbeddingGenerator
from backend.app.utils.query_classifier import classify_query

# Test queries
TEST_QUERIES = [
    {
        "query": "design system that spans multiple supervisors with graphics roll-up to VM",
        "description": "Cross-domain: architecture + graphics"
    },
    {
        "query": "configure AHU sequence of operation for VAV zones",
        "description": "HVAC + Configuration"
    },
    {
        "query": "wire BACnet sensor to JACE controller",
        "description": "Hardware + Integration"
    }
]

db = DatabaseClient()
embedding_gen = EmbeddingGenerator()

with db:
    print("=" * 80)
    print("TESTING GRADUATED BOOSTING (No Hard Exclusions)")
    print("=" * 80)
    
    for test in TEST_QUERIES:
        query = test["query"]
        desc = test["description"]
        
        print(f"\n🧪 Test: {desc}")
        print(f"📝 Query: {query}")
        
        # Classify
        categories = classify_query(query, use_llm=False)
        print(f"📊 Categories: {categories}")
        
        # Generate embedding
        embedding = embedding_gen.generate_embeddings([query])[0]
        
        # Search with topics (include only, no exclusions)
        results = db.search_chunks_hybrid_with_topics(
            query_embedding=embedding,
            query_text=query,
            doc_id="video_hV9-1RgkTk8",
            include_topics=['system_database', 'multi_tier_architecture', 'graphics', 
                           'configuration', 'hvac_systems', 'hardware', 'integration'],
            exclude_topics=None,  # NO EXCLUSIONS
            top_k=5
        )
        
        print(f"\n🔍 Top 5 Results:")
        for i, r in enumerate(results, 1):
            topics = r.get('topics', [])
            topic_boost = r.get('topic_boost', 1.0)
            final_score = r.get('final_score', 0)
            content_preview = r['content'][:80].replace('\n', ' ')
            
            print(f"  {i}. topics={topics}")
            print(f"     boost={topic_boost:.1f}x, score={final_score:.4f}")
            print(f"     content: {content_preview}...")
        
        # Check diversity
        all_topics = set()
        for r in results:
            all_topics.update(r.get('topics', []))
        
        print(f"\n✅ Topic diversity: {len(all_topics)} unique topics across top 5")
        print(f"   Topics found: {sorted(all_topics)}")
        
        # Check if provisioning got through (should be possible now, just not boosted)
        has_provisioning = any('provisioning' in r.get('topics', []) for r in results)
        print(f"   Provisioning chunks: {'Yes (unboosted)' if has_provisioning else 'No'}")
        
        print("\n" + "-" * 80)

print("\n✅ Test complete! System now allows cross-domain retrieval with graduated boosting.")
