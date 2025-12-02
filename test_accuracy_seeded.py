"""Seeded accuracy test for RAG improvements.

Tests the system with real technical queries to measure:
- Retrieval quality
- Answer grounding
- Cost optimization
- Cache effectiveness
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, '.')
from dotenv import load_dotenv

load_dotenv()

from src.database.db_client import DatabaseClient
from src.utils.embeddings import EmbeddingGenerator
from backend.app.utils.query_classifier import classify_query
from backend.app.utils.query_rewriter import rewrite_query
from backend.app.utils.adaptive_retrieval import adaptive_retrieval_params
from backend.app.utils.query_cache import QueryCache
from backend.app.utils.answer_verifier import quick_verify
from backend.app.utils.retrieval_metrics import RetrievalMetrics

# Seeded test queries (real technical questions)
TEST_QUERIES = [
    {
        "id": "q1_simple_definition",
        "question": "What is System Database in Niagara?",
        "expected_category": ["architecture"],
        "expected_complexity": "simple",
        "expected_top_k": 3,
        "ground_truth_keywords": ["centralized", "data", "repository", "stations"]
    },
    {
        "id": "q2_procedural",
        "question": "How do I configure a multi-tier architecture with System Database?",
        "expected_category": ["architecture"],
        "expected_complexity": "moderate",
        "expected_top_k": 5,
        "ground_truth_keywords": ["Enterprise Supervisor", "JACE", "sync", "configuration"]
    },
    {
        "id": "q3_comparison",
        "question": "What's the difference between System Database and traditional point-to-point configuration, and which should I use for a multi-tier setup?",
        "expected_category": ["architecture", "design"],
        "expected_complexity": "complex",
        "expected_top_k": 7,
        "ground_truth_keywords": ["centralized", "distributed", "multi-tier", "scalability"]
    },
    {
        "id": "q4_troubleshooting",
        "question": "My JACE is showing 'System Database sync failed' alarm. How do I diagnose and fix this?",
        "expected_category": ["troubleshooting"],
        "expected_complexity": "moderate",
        "expected_top_k": 5,
        "ground_truth_keywords": ["alarm", "sync", "network", "diagnostics", "resolution"]
    },
    {
        "id": "q5_graphics",
        "question": "How do PX graphics integrate with System Database tags?",
        "expected_category": ["graphics", "architecture"],
        "expected_complexity": "moderate",
        "expected_top_k": 5,
        "ground_truth_keywords": ["PX", "tags", "binding", "navigation", "tag dictionary"]
    }
]


class AccuracyTest:
    """Accuracy testing framework."""

    def __init__(self):
        self.db = DatabaseClient()
        self.embedding_gen = EmbeddingGenerator()
        self.cache = QueryCache(self.db, ttl_hours=24)
        self.metrics = RetrievalMetrics(self.db)
        self.results = []

    def test_query(self, test_case: dict, doc_id: str) -> dict:
        """Test a single query and return results."""
        question = test_case["question"]
        print(f"\n{'='*80}")
        print(f"Testing: {question[:70]}...")
        print(f"{'='*80}")

        result = {
            "test_id": test_case["id"],
            "question": question,
            "timestamp": datetime.utcnow().isoformat()
        }

        # Step 1: Query Classification
        print("\n1. QUERY CLASSIFICATION")
        categories = classify_query(question)
        result["categories"] = categories
        result["category_match"] = any(c in test_case["expected_category"] for c in categories)
        print(f"   Categories: {categories}")
        print(f"   Expected: {test_case['expected_category']}")
        print(f"   Match: {'YES' if result['category_match'] else 'NO'}")

        # Step 2: Query Rewriting
        print("\n2. QUERY REWRITING")
        rewritten = rewrite_query(question, categories)
        result["rewritten_query"] = rewritten
        print(f"   Original: {question[:60]}...")
        print(f"   Rewritten: {rewritten[:60]}...")

        # Step 3: Adaptive Retrieval
        print("\n3. ADAPTIVE RETRIEVAL")
        top_k, window, complexity = adaptive_retrieval_params(
            question=question,
            query_type=categories[0] if categories else 'general'
        )
        result["complexity"] = complexity
        result["top_k"] = top_k
        result["context_window"] = window
        result["complexity_match"] = (complexity == test_case["expected_complexity"])
        result["top_k_match"] = (top_k == test_case["expected_top_k"])

        print(f"   Complexity: {complexity} (expected: {test_case['expected_complexity']})")
        print(f"   top_k: {top_k} (expected: {test_case['expected_top_k']})")
        print(f"   window: {window}")

        # Step 4: Check Cache
        print("\n4. CACHE CHECK")
        embedding = self.embedding_gen.generate_embeddings([question])[0]
        cached = self.cache.get_cached_answer(question, doc_id, embedding)
        result["cache_hit"] = (cached is not None)
        print(f"   Cache hit: {'YES' if cached else 'NO'}")

        if cached:
            print(f"   Using cached answer (saved tokens!)")
            result["answer"] = cached.answer
            result["citations"] = cached.citations
            result["tokens_saved"] = 1500  # Estimated
        else:
            # Step 5: Retrieval
            print("\n5. RETRIEVAL")
            search_results = self.db.search_chunks_hybrid_with_topics(
                query_embedding=embedding,
                query_text=rewritten,
                doc_id=doc_id,
                include_topics=[],  # Let it be open
                exclude_topics=None,
                semantic_weight=0.5,
                keyword_weight=0.5,
                top_k=top_k
            )

            result["retrieved_chunks"] = len(search_results)
            if search_results:
                result["top_score"] = float(search_results[0].get('final_score', 0))
                result["avg_score"] = sum(float(r.get('final_score', 0)) for r in search_results) / len(search_results)
                result["topics_found"] = list(set(r.get('topic') for r in search_results if r.get('topic')))

            print(f"   Retrieved: {len(search_results)} chunks")
            if search_results:
                print(f"   Top score: {result.get('top_score', 0):.3f}")
                print(f"   Avg score: {result.get('avg_score', 0):.3f}")
                print(f"   Topics: {result.get('topics_found', [])}")

            # Step 6: Answer Generation (simulated - we don't want to call LLM in test)
            print("\n6. ANSWER GENERATION (simulated)")
            # In real test, this would call LLM
            # For now, use top chunk as simulated answer
            if search_results:
                result["answer"] = search_results[0].get('content', '')[:200]
                result["citations"] = [
                    {"content": r.get('content', '')[:100], "page": r.get('page_number')}
                    for r in search_results[:3]
                ]
            else:
                result["answer"] = "No results found"
                result["citations"] = []

            # Step 7: Ground Truth Check
            print("\n7. GROUND TRUTH CHECK")
            answer_text = result.get("answer", "").lower()
            keywords_found = [
                kw for kw in test_case["ground_truth_keywords"]
                if kw.lower() in answer_text or any(kw.lower() in c.get('content', '').lower() for c in result["citations"])
            ]
            result["ground_truth_coverage"] = len(keywords_found) / len(test_case["ground_truth_keywords"])
            result["keywords_found"] = keywords_found

            print(f"   Expected keywords: {test_case['ground_truth_keywords']}")
            print(f"   Found keywords: {keywords_found}")
            print(f"   Coverage: {result['ground_truth_coverage']:.1%}")

            # Step 8: Cache this result
            if not cached:
                print("\n8. CACHING RESULT")
                self.cache.cache_answer(
                    question=question,
                    doc_id=doc_id,
                    answer=result.get("answer", ""),
                    citations=result.get("citations", []),
                    question_embedding=embedding
                )
                print("   Result cached for future queries")

        # Step 9: Log Metrics
        print("\n9. LOGGING METRICS")
        if not cached:
            self.metrics.log_retrieval(
                question=question,
                query_categories=categories,
                results=search_results if not cached else [],
                top_k=top_k,
                query_type=categories[0] if categories else 'unknown',
                complexity=complexity,
                doc_id=doc_id
            )
            print("   Metrics logged")

        return result

    def run_all_tests(self, doc_id: str):
        """Run all seeded tests."""
        print("\n" + "="*80)
        print("SEEDED ACCURACY TEST - RAG IMPROVEMENTS")
        print("="*80)
        print(f"Testing against document: {doc_id}")
        print(f"Total test queries: {len(TEST_QUERIES)}")

        for test_case in TEST_QUERIES:
            result = self.test_query(test_case, doc_id)
            self.results.append(result)

            # Short delay between tests
            import time
            time.sleep(0.5)

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate comprehensive test report."""
        print("\n\n" + "="*80)
        print("TEST REPORT")
        print("="*80)

        total = len(self.results)
        cache_hits = sum(1 for r in self.results if r.get("cache_hit"))
        category_matches = sum(1 for r in self.results if r.get("category_match"))
        complexity_matches = sum(1 for r in self.results if r.get("complexity_match"))
        top_k_matches = sum(1 for r in self.results if r.get("top_k_match"))

        avg_coverage = sum(r.get("ground_truth_coverage", 0) for r in self.results) / total

        print(f"\nAccuracy Metrics:")
        print(f"  Category Classification: {category_matches}/{total} ({category_matches/total:.1%})")
        print(f"  Complexity Detection: {complexity_matches}/{total} ({complexity_matches/total:.1%})")
        print(f"  Top-K Prediction: {top_k_matches}/{total} ({top_k_matches/total:.1%})")
        print(f"  Ground Truth Coverage: {avg_coverage:.1%}")

        print(f"\nCache Performance:")
        print(f"  Cache Hits: {cache_hits}/{total} ({cache_hits/total:.1%})")
        if cache_hits > 0:
            tokens_saved = sum(r.get("tokens_saved", 0) for r in self.results if r.get("cache_hit"))
            print(f"  Estimated Tokens Saved: {tokens_saved}")

        print(f"\nRetrieval Quality:")
        avg_top_score = sum(r.get("top_score", 0) for r in self.results if "top_score" in r) / max(1, total - cache_hits)
        avg_avg_score = sum(r.get("avg_score", 0) for r in self.results if "avg_score" in r) / max(1, total - cache_hits)
        print(f"  Avg Top Score: {avg_top_score:.3f}")
        print(f"  Avg Overall Score: {avg_avg_score:.3f}")

        # Save detailed results
        output_file = Path("test_accuracy_results.json")
        with open(output_file, 'w') as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "summary": {
                    "total_tests": total,
                    "cache_hit_rate": cache_hits/total,
                    "category_accuracy": category_matches/total,
                    "complexity_accuracy": complexity_matches/total,
                    "ground_truth_coverage": avg_coverage,
                    "avg_retrieval_score": avg_avg_score
                },
                "detailed_results": self.results
            }, f, indent=2)

        print(f"\nDetailed results saved to: {output_file}")
        print("\n" + "="*80)

        # Overall assessment
        if avg_coverage >= 0.7 and category_matches/total >= 0.8:
            print("OVERALL: PASS - System meeting accuracy targets")
        else:
            print("OVERALL: NEEDS IMPROVEMENT - Review detailed results")

        print("="*80)


def main():
    """Run seeded accuracy tests."""
    # Get document ID from user or use default
    doc_id = os.getenv('TEST_DOC_ID')

    if not doc_id:
        print("ERROR: Please set TEST_DOC_ID environment variable")
        print("Example: export TEST_DOC_ID='your-document-id'")
        return 1

    tester = AccuracyTest()
    tester.run_all_tests(doc_id)

    return 0


if __name__ == "__main__":
    sys.exit(main())
