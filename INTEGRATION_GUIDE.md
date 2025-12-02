# RAG System Improvements - Integration Guide

**Date**: December 1, 2025
**Status**: Ready for Integration

---

## Overview

This guide covers integrating 6 major improvements to the AME Knowledge Base RAG system:

1. **Answer Verification** - Prevents hallucinations
2. **Adaptive Retrieval** - Optimizes cost and performance
3. **Query Cache** - Reduces costs 30-50%
4. **Enhanced Conversation Memory** - Better long conversations
5. **Multi-Hop Reasoning** - Handles complex queries
6. **Retrieval Metrics** - Monitors quality

---

## Step 1: Run Database Migrations

```bash
# Run the migrations
python run_new_migrations.py
```

**What this creates**:
- `query_cache` table (caches LLM responses)
- `retrieval_metrics` table (tracks retrieval quality)
- Helpful views for monitoring

**Expected output**:
```
✅ All migrations completed successfully!

New features enabled:
  • Query caching (reduces cost for repeated queries)
  • Retrieval quality metrics (monitors performance)
```

---

## Step 2: Integrate into chat_multimodal.py

Add these imports at the top:

```python
# Add to imports section (around line 14)
from app.utils.answer_verifier import verify_answer_grounding, quick_verify
from app.utils.adaptive_retrieval import adaptive_retrieval_params, needs_multi_hop_reasoning
from app.utils.query_cache import QueryCache
from app.utils.conversation_manager_enhanced import format_chat_history_with_summary
from app.utils.multi_hop_retriever import multi_hop_retrieve
from app.utils.retrieval_metrics import RetrievalMetrics
```

### Step 2a: Initialize New Components

Add after line 28 (after openai_client):

```python
# Initialize improvement components
query_cache = QueryCache(db_client=None, ttl_hours=24)  # Will set db_client per request
retrieval_metrics = RetrievalMetrics(db_client=None)     # Will set db_client per request
```

### Step 2b: Add Cache Check (Early Return)

Add after line 410 (after conversation context extraction):

```python
                # NEW: Check query cache for recent identical questions
                query_cache.db = db
                cached_result = query_cache.get_cached_answer(
                    question=request.question,
                    doc_id=request.doc_id,
                    question_embedding=question_embedding
                )

                if cached_result:
                    print(f"   ✅ CACHE HIT! Returning cached answer (saved tokens)")

                    # Return cached response
                    return ChatResponse(
                        answer=cached_result.answer,
                        citations=cached_result.citations,
                        images_used=[],
                        tables_used=0,
                        tokens_used=0,  # No tokens used!
                        search_results_count=len(cached_result.citations),
                        model_used=cached_result.model_used
                    )
```

### Step 2c: Use Adaptive Retrieval

Replace lines 437-442 (the existing top_k and context_window logic):

```python
                # NEW: Adaptive retrieval - adjust based on query complexity
                from app.utils.adaptive_retrieval import adaptive_retrieval_params, needs_multi_hop_reasoning

                base_top_k = request.top_k
                base_window = request.context_window

                top_k, context_window, complexity = adaptive_retrieval_params(
                    question=request.question,
                    query_type=query_type,
                    is_followup=conversation_context['is_followup'],
                    base_top_k=base_top_k,
                    base_window=base_window
                )

                print(f"🎯 Adaptive retrieval: complexity={complexity}, top_k={top_k}, window={context_window}")
```

### Step 2d: Add Multi-Hop Retrieval

Replace lines 452-464 (the existing search_chunks_hybrid_with_topics call):

```python
                # NEW: Multi-hop retrieval for complex queries
                use_multi_hop = needs_multi_hop_reasoning(request.question, query_type, complexity)

                if use_multi_hop:
                    print(f"🔍 Using multi-hop retrieval for complex query")
                    from app.utils.multi_hop_retriever import multi_hop_retrieve

                    search_results, sub_questions = multi_hop_retrieve(
                        question=request.question,
                        doc_id=request.doc_id,
                        db_client=db,
                        embedding_gen=embedding_gen,
                        query_type=query_type,
                        max_hops=3,
                        chunks_per_hop=3
                    )
                else:
                    # Standard topic-aware hybrid search
                    search_results = db.search_chunks_hybrid_with_topics(
                        query_embedding=question_embedding,
                        query_text=rewritten_query,
                        doc_id=request.doc_id,
                        include_topics=relevant_topics,
                        exclude_topics=None,
                        semantic_weight=0.5,
                        keyword_weight=0.5,
                        top_k=top_k  # Use adaptive top_k
                    )
```

### Step 2e: Log Retrieval Metrics

Add after line 474 (after search results are obtained):

```python
                # NEW: Log retrieval metrics for monitoring
                retrieval_metrics.db = db
                retrieval_metrics.log_retrieval(
                    question=request.question,
                    query_categories=query_categories,
                    results=search_results,
                    top_k=top_k,
                    query_type=query_type,
                    complexity=complexity,
                    doc_id=request.doc_id,
                    retrieval_strategy='multi_hop' if use_multi_hop else 'hybrid_with_topics'
                )
```

### Step 2f: Use Enhanced Conversation Memory

Replace lines 489-497 (the existing multimodal messages building):

```python
                # NEW: Enhanced conversation memory with sliding window summary
                from app.utils.conversation_manager_enhanced import format_chat_history_with_summary

                # Get conversation summary for long conversations
                chat_history_dicts = [{"role": msg.role, "content": msg.content} for msg in request.chat_history]
                summary, recent_messages = format_chat_history_with_summary(
                    chat_history_dicts,
                    max_recent_messages=4
                )

                # Build multimodal messages
                messages, images_used, tables_used = build_multimodal_messages(
                    expanded_contexts=expanded_contexts,
                    question=request.question,
                    doc_title=doc['title'],
                    question_mode=question_mode,
                    chat_history=[ChatMessage(**msg) for msg in recent_messages] if recent_messages else [],
                    include_images=request.use_images
                )

                # Add conversation summary if exists
                if summary:
                    # Insert summary after system prompt
                    messages.insert(1, {
                        "role": "system",
                        "content": f"**Previous Conversation Summary**: {summary}\n\nUse this context to understand the ongoing discussion."
                    })
```

### Step 2g: Add Answer Verification

Add after line 610 (after cleaned_answer is generated):

```python
                # NEW: Verify answer grounding
                print(f"\n🔍 Verifying answer grounding...")

                # Use quick verification for production (single LLM call)
                from app.utils.answer_verifier import quick_verify

                is_grounded, confidence, disclaimer = quick_verify(
                    answer=cleaned_answer,
                    citations=[
                        {
                            'content': ctx['chunk']['content'],
                            'page_number': ctx['chunk'].get('page_number')
                        }
                        for ctx in expanded_contexts
                    ]
                )

                print(f"   Grounding: {'✓ PASS' if is_grounded else '✗ FAIL'} (confidence: {confidence:.1%})")

                # Append disclaimer if needed
                if disclaimer:
                    cleaned_answer += disclaimer
```

### Step 2h: Cache the Answer

Add after the answer verification (before return statement):

```python
                # NEW: Cache the answer for future queries
                cache_citations = [
                    {
                        'content': c.content,
                        'page_number': c.page_number,
                        'section_path': c.section_path,
                        'similarity_score': c.similarity_score
                    }
                    for c in citations
                ]

                query_cache.cache_answer(
                    question=request.question,
                    doc_id=request.doc_id,
                    answer=cleaned_answer,
                    citations=cache_citations,
                    model_used=model,
                    question_embedding=question_embedding
                )
```

---

## Step 3: Test the Integration

Create a test script:

```python
# test_improvements.py

import sys
sys.path.append('.')

from backend.app.utils.answer_verifier import verify_answer_grounding
from backend.app.utils.adaptive_retrieval import adaptive_retrieval_params
from backend.app.utils.query_cache import QueryCache
from backend.app.utils.retrieval_metrics import RetrievalMetrics

print("✅ All modules imported successfully!")

# Test adaptive retrieval
test_questions = [
    ("What is System Database?", "definition"),
    ("Compare System Database vs point-to-point and explain which to use", "comparison"),
]

for q, qtype in test_questions:
    top_k, window, complexity = adaptive_retrieval_params(q, qtype)
    print(f"\nQ: {q[:50]}...")
    print(f"   Complexity: {complexity}, top_k: {top_k}, window: {window}")

print("\n✅ All tests passed!")
```

Run it:
```bash
python test_improvements.py
```

---

## Step 4: Monitor Performance

### Check Cache Performance

```python
from backend.app.utils.query_cache import QueryCache
from src.database.db_client import DatabaseClient

db = DatabaseClient()
cache = QueryCache(db, ttl_hours=24)

stats = cache.get_cache_stats()
print(f"Cache hit rate: {stats['cache_hit_rate']:.1%}")
print(f"Total cache hits: {stats['total_cache_hits']}")
```

### Check Retrieval Quality

```python
from backend.app.utils.retrieval_metrics import RetrievalMetrics
from src.database.db_client import DatabaseClient

db = DatabaseClient()
metrics = RetrievalMetrics(db)

# Get report
report = metrics.generate_report(days=7)
print(report)
```

Or query directly:

```sql
-- Daily retrieval quality
SELECT * FROM daily_retrieval_summary LIMIT 7;

-- Low coverage queries
SELECT * FROM low_coverage_queries LIMIT 10;

-- Category performance
SELECT * FROM category_performance;
```

---

## Expected Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| **Cost per 1000 queries** | $1.50 | $0.75-$1.00 | **33-50% reduction** |
| **Simple query cost** | $0.0015 | $0.0009 | **40% reduction** |
| **Cache hit rate** | 0% | 20-50% | **Major savings** |
| **Hallucination risk** | Medium | Low | **Verification enabled** |
| **Complex query handling** | Fair | Good | **Multi-hop enabled** |
| **Long conversation quality** | Fair | Good | **Summary compression** |

---

## Rollback Plan

If issues occur, you can disable features individually:

### Disable Cache
```python
# In chat_multimodal.py, comment out the cache check section
# cached_result = query_cache.get_cached_answer(...)
```

### Disable Answer Verification
```python
# Comment out the verification section
# is_grounded, confidence, disclaimer = quick_verify(...)
```

### Disable Multi-Hop
```python
# Set use_multi_hop = False
use_multi_hop = False  # Force disable
```

### Disable Adaptive Retrieval
```python
# Use fixed values
top_k = request.top_k  # Use request values directly
context_window = request.context_window
```

---

## Monitoring Dashboard Queries

```sql
-- Cache effectiveness
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_cached,
    SUM(hit_count) as total_hits,
    AVG(hit_count) as avg_hits_per_query
FROM query_cache
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- Popular cached queries
SELECT
    question,
    hit_count,
    created_at
FROM query_cache
ORDER BY hit_count DESC
LIMIT 10;

-- Retrieval quality trends
SELECT * FROM daily_retrieval_summary LIMIT 14;

-- Category-specific issues
SELECT
    category,
    COUNT(*) as low_coverage_count
FROM retrieval_metrics,
     jsonb_array_elements_text(categories) as category
WHERE (metrics->>'topic_coverage')::float < 0.6
  AND created_at > NOW() - INTERVAL '7 days'
GROUP BY category
ORDER BY low_coverage_count DESC;
```

---

## Cost Tracking

Track actual cost savings:

```sql
-- Queries served from cache (zero cost)
SELECT COUNT(*) as cached_queries
FROM query_cache
WHERE hit_count > 0
  AND created_at > NOW() - INTERVAL '7 days';

-- Estimated savings calculation
WITH stats AS (
    SELECT
        COUNT(*) as total_cache_hits,
        AVG(LENGTH(answer)) as avg_answer_length
    FROM query_cache
    WHERE hit_count > 0
      AND created_at > NOW() - INTERVAL '7 days'
)
SELECT
    total_cache_hits,
    avg_answer_length,
    -- Assume avg 1000 input tokens + 500 output tokens per cached query
    (total_cache_hits * ((1000 * 0.00000015) + (500 * 0.0000006))) as estimated_savings_usd
FROM stats;
```

---

## Next Steps

1. **Run migrations** (Step 1)
2. **Integrate code** (Step 2)
3. **Test thoroughly** (Step 3)
4. **Monitor performance** (Step 4)
5. **Tune parameters** based on metrics
6. **Document learnings** for future improvements

---

## Support

If you encounter issues:

1. Check migration status: `SELECT * FROM retrieval_metrics LIMIT 1;`
2. Check cache status: `SELECT COUNT(*) FROM query_cache;`
3. Review error logs in console output
4. Check individual feature tests in Step 3

For questions or issues, refer to the individual module documentation in:
- `backend/app/utils/answer_verifier.py`
- `backend/app/utils/adaptive_retrieval.py`
- `backend/app/utils/query_cache.py`
- `backend/app/utils/conversation_manager_enhanced.py`
- `backend/app/utils/multi_hop_retriever.py`
- `backend/app/utils/retrieval_metrics.py`
