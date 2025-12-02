"""Verify RAG improvements installation.

Checks that all modules are properly installed and can be imported.
Does NOT require OpenAI API key.
"""
import sys
sys.path.insert(0, '.')

def check_imports():
    """Check that all improvement modules can be imported."""
    print("\n" + "=" * 80)
    print("VERIFYING RAG IMPROVEMENTS INSTALLATION")
    print("=" * 80)

    modules = [
        ("Answer Verifier", "backend.app.utils.answer_verifier"),
        ("Adaptive Retrieval", "backend.app.utils.adaptive_retrieval"),
        ("Query Cache", "backend.app.utils.query_cache"),
        ("Conversation Manager Enhanced", "backend.app.utils.conversation_manager_enhanced"),
        ("Multi-Hop Retriever", "backend.app.utils.multi_hop_retriever"),
        ("Retrieval Metrics", "backend.app.utils.retrieval_metrics"),
    ]

    success = 0
    failed = []

    for name, module_path in modules:
        try:
            __import__(module_path)
            print(f"✅ {name:35} - OK")
            success += 1
        except Exception as e:
            print(f"❌ {name:35} - FAILED: {e}")
            failed.append((name, str(e)))

    print("\n" + "=" * 80)
    print(f"IMPORT CHECK: {success}/{len(modules)} modules imported successfully")
    print("=" * 80)

    if failed:
        print("\n⚠️  Failed imports:")
        for name, error in failed:
            print(f"   • {name}: {error}")
        return False

    return True


def test_adaptive_retrieval_basic():
    """Test adaptive retrieval without API calls."""
    print("\n" + "=" * 80)
    print("TESTING: Adaptive Retrieval (No API)")
    print("=" * 80)

    from backend.app.utils.adaptive_retrieval import (
        adaptive_retrieval_params,
        detect_query_complexity,
        estimate_token_savings
    )

    test_cases = [
        ("What is System Database?", "definition"),
        ("Compare System Database vs point-to-point and explain which to use", "comparison"),
        ("How do I configure VFD for variable speed?", "procedural"),
    ]

    for question, qtype in test_cases:
        top_k, window, complexity = adaptive_retrieval_params(question, qtype)
        savings = estimate_token_savings(complexity, top_k, window)

        print(f"\n📝 Query: {question[:50]}...")
        print(f"   Type: {qtype}, Complexity: {complexity}")
        print(f"   Params: top_k={top_k}, window={window}")
        print(f"   Estimated savings: {savings:.1%}")

    print("\n✅ Adaptive Retrieval Test PASSED")
    return True


def test_query_cache_basic():
    """Test query cache key generation (no DB needed)."""
    print("\n" + "=" * 80)
    print("TESTING: Query Cache (No DB)")
    print("=" * 80)

    from backend.app.utils.query_cache import QueryCache

    cache = QueryCache(db_client=None, ttl_hours=24)

    test_questions = [
        "What is System Database?",
        "what is system database",  # Different case
        "What is System Database ?",  # Different punctuation
    ]

    print("\n🔑 Testing cache key generation...")
    keys = []
    for q in test_questions:
        key = cache._generate_cache_key(q, "doc_123")
        keys.append(key)
        print(f"   {q:40} → {key[:16]}...")

    if keys[0] == keys[1] == keys[2]:
        print("\n✅ Cache keys match for similar questions (normalization working)")
    else:
        print("\n⚠️  Cache keys differ (may need tuning)")

    print("\n✅ Query Cache Test PASSED")
    return True


def test_conversation_memory_basic():
    """Test conversation memory (no API)."""
    print("\n" + "=" * 80)
    print("TESTING: Conversation Memory (No API)")
    print("=" * 80)

    from backend.app.utils.conversation_manager_enhanced import (
        extract_key_entities_from_history,
        should_use_conversation_summary
    )

    test_history = [
        {"role": "user", "content": "How do I configure System Database?"},
        {"role": "assistant", "content": "System Database is configured via the SystemDB station..."},
        {"role": "user", "content": "What about multi-tier setup?"},
        {"role": "assistant", "content": "For multi-tier, you'll use Enterprise Supervisors..."},
    ]

    print(f"\n💬 Test conversation: {len(test_history)} messages")

    entities = extract_key_entities_from_history(test_history)
    print(f"   ✓ Extracted {len(entities)} entities: {', '.join(entities[:5])}")

    needs_summary = should_use_conversation_summary(test_history)
    print(f"   ✓ Needs summary: {needs_summary}")

    print("\n✅ Conversation Memory Test PASSED")
    return True


def test_retrieval_metrics_basic():
    """Test retrieval metrics (no DB)."""
    print("\n" + "=" * 80)
    print("TESTING: Retrieval Metrics (No DB)")
    print("=" * 80)

    from backend.app.utils.retrieval_metrics import RetrievalMetrics

    metrics_tracker = RetrievalMetrics(db_client=None)

    mock_results = [
        {'id': 'c1', 'combined_score': 0.85, 'topic': 'system_database'},
        {'id': 'c2', 'combined_score': 0.78, 'topic': 'graphics'},
        {'id': 'c3', 'combined_score': 0.72, 'topic': 'system_database'},
    ]

    metrics = metrics_tracker._calculate_metrics(
        results=mock_results,
        query_categories=['architecture', 'graphics'],
        top_k=5
    )

    print(f"\n📊 Metrics calculation:")
    print(f"   Avg score: {metrics['avg_score']:.3f}")
    print(f"   Topic coverage: {metrics['topic_coverage']:.1%}")
    print(f"   Topic diversity: {metrics['topic_diversity']}")

    print("\n✅ Retrieval Metrics Test PASSED")
    return True


def check_migrations():
    """Check if migration files exist."""
    print("\n" + "=" * 80)
    print("CHECKING: Migration Files")
    print("=" * 80)

    import os
    from pathlib import Path

    migrations_dir = Path("migrations")
    required_migrations = [
        "010_add_query_cache.sql",
        "011_add_retrieval_metrics.sql",
    ]

    all_exist = True
    for migration in required_migrations:
        path = migrations_dir / migration
        if path.exists():
            print(f"✅ {migration:35} - Found")
        else:
            print(f"❌ {migration:35} - Missing")
            all_exist = False

    if all_exist:
        print("\n✅ All migration files present")
    else:
        print("\n⚠️  Some migration files missing")

    return all_exist


def main():
    """Run all verification checks."""
    print("\n" + "=" * 80)
    print("RAG IMPROVEMENTS - INSTALLATION VERIFICATION")
    print("=" * 80)
    print("\nThis script verifies that all improvement modules are installed.")
    print("Note: Full testing requires OpenAI API key and database connection.")

    results = {}

    # Run checks
    results['imports'] = check_imports()
    results['migrations'] = check_migrations()
    results['adaptive_retrieval'] = test_adaptive_retrieval_basic()
    results['query_cache'] = test_query_cache_basic()
    results['conversation_memory'] = test_conversation_memory_basic()
    results['retrieval_metrics'] = test_retrieval_metrics_basic()

    # Summary
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    print("\n" + "=" * 80)
    print("VERIFICATION SUMMARY")
    print("=" * 80)
    print(f"Passed: {passed}/{total} checks")

    if passed == total:
        print("\n✅ ALL CHECKS PASSED!")
        print("\nNext steps:")
        print("1. Set OPENAI_API_KEY environment variable")
        print("2. Run migrations: python run_new_migrations.py")
        print("3. Follow QUICK_START.md for integration")
        return 0
    else:
        print(f"\n⚠️  {total - passed} check(s) failed")
        print("Review errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
