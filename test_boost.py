import sys
sys.path.insert(0, '/app/src')

from database.db_client import DatabaseClient
from utils.embeddings import EmbeddingGenerator

db = DatabaseClient()
emb = EmbeddingGenerator()

query = 'design system with multiple supervisors and graphics'
print(f"Query: {query}\n")

embedding = emb.generate_embeddings([query])[0]

results = db.search_chunks_hybrid_with_topics(
    embedding, 
    query, 
    'video_hV9-1RgkTk8', 
    ['system_database', 'multi_tier_architecture', 'graphics'], 
    None, 
    0.5, 
    0.5, 
    5
)

print(f"Results: {len(results)}\n")
for i, r in enumerate(results[:5], 1):
    boost = r.get('topic_boost', 1.0)
    topics = r.get('topics', [])
    score = r.get('final_score', 0)
    print(f"{i}. boost={boost:.1f}x topics={topics} score={score:.4f}")
