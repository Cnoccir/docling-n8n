# RAG Improvements - Deployment & Validation Guide

**Status**: ✅ Code Committed | ✅ Migrations Applied | ✅ Tests Created
**Date**: December 1, 2025

---

## What's Been Deployed

### Committed Code (Commit: 2fcdbdf)
- ✅ 6 utility modules (answer verification, adaptive retrieval, cache, memory, multi-hop, metrics)
- ✅ 2 database migrations (query_cache, retrieval_metrics tables)
- ✅ Integration scaffolding in chat_multimodal.py
- ✅ Seeded accuracy test suite
- ✅ Complete documentation

### Database Changes Applied
- ✅ `query_cache` table (with semantic matching)
- ✅ `retrieval_metrics` table (with analytics views)
- ✅ Helper views: `low_coverage_queries`, `daily_retrieval_summary`, `category_performance`

---

## Quick Validation (5 minutes)

### 1. Verify Database Migrations

```bash
# Check tables exist
python -c "
from database.db_client import DatabaseClient
db = DatabaseClient()
with db.conn.cursor() as cur:
    cur.execute(\"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('query_cache', 'retrieval_metrics')\")
    tables = [r[0] for r in cur.fetchall()]
    print(f'Tables created: {tables}')
    if len(tables) == 2:
        print('SUCCESS: All tables exist')
    else:
        print('ERROR: Missing tables')
"
```

Expected output:
```
Tables created: ['query_cache', 'retrieval_metrics']
SUCCESS: All tables exist
```

### 2. Verify Imports Work

```bash
# Test module imports
python -c "
import sys
sys.path.insert(0, '.')
from backend.app.utils.answer_verifier import quick_verify
from backend.app.utils.adaptive_retrieval import adaptive_retrieval_params
from backend.app.utils.query_cache import QueryCache
from backend.app.utils.multi_hop_retriever import multi_hop_retrieve
from backend.app.utils.retrieval_metrics import RetrievalMetrics
print('SUCCESS: All modules import correctly')
"
```

Expected output:
```
SUCCESS: All modules import correctly
```

### 3. Test Adaptive Retrieval

```bash
# Test adaptive retrieval logic
python -c "
import sys
sys.path.insert(0, '.')
from backend.app.utils.adaptive_retrieval import adaptive_retrieval_params

# Simple query
top_k, window, complexity = adaptive_retrieval_params('What is System Database?', 'definition')
print(f'Simple query: top_k={top_k}, window={window}, complexity={complexity}')
assert complexity == 'simple', 'Complexity detection failed'
assert top_k <= 3, 'top_k should be small for simple queries'

# Complex query
top_k, window, complexity = adaptive_retrieval_params('Compare System Database vs point-to-point and explain which to use', 'comparison')
print(f'Complex query: top_k={top_k}, window={window}, complexity={complexity}')
assert complexity == 'complex', 'Complexity detection failed'
assert top_k >= 6, 'top_k should be large for complex queries'

print('SUCCESS: Adaptive retrieval working correctly')
"
```

---

## Running Seeded Accuracy Tests

### Prerequisites
1. Set test document ID:
   ```bash
   export TEST_DOC_ID='your-document-id-here'
   ```

2. Ensure you have a processed document in the database

### Run Tests

```bash
python test_accuracy_seeded.py
```

### Expected Output

```
================================================================================
SEEDED ACCURACY TEST - RAG IMPROVEMENTS
================================================================================
Testing against document: doc_xxxxx
Total test queries: 5

================================================================================
Testing: What is System Database in Niagara?...
================================================================================

1. QUERY CLASSIFICATION
   Categories: ['architecture']
   Expected: ['architecture']
   Match: YES

2. QUERY REWRITING
   Original: What is System Database in Niagara?...
   Rewritten: System Database in Niagara 4 BAS/HVAC centralized data...

3. ADAPTIVE RETRIEVAL
   Complexity: simple (expected: simple)
   top_k: 3 (expected: 3)
   window: 1

4. CACHE CHECK
   Cache hit: NO

5. RETRIEVAL
   Retrieved: 3 chunks
   Top score: 0.852
   Avg score: 0.791
   Topics: ['system_database', 'architecture']

...

================================================================================
TEST REPORT
================================================================================

Accuracy Metrics:
  Category Classification: 5/5 (100%)
  Complexity Detection: 5/5 (100%)
  Top-K Prediction: 5/5 (100%)
  Ground Truth Coverage: 75.0%

Cache Performance:
  Cache Hits: 0/5 (0%) [First run - expected]

Retrieval Quality:
  Avg Top Score: 0.850
  Avg Overall Score: 0.780

Detailed results saved to: test_accuracy_results.json

OVERALL: PASS - System meeting accuracy targets
```

### Second Run (Test Cache)

Run the same test again immediately:
```bash
python test_accuracy_seeded.py
```

Expected:
```
Cache Performance:
  Cache Hits: 5/5 (100%)
  Estimated Tokens Saved: 7500
```

---

## Monitoring Dashboards

### Check Cache Performance

```sql
-- Cache hit rate over time
SELECT
    DATE(created_at) as date,
    COUNT(*) as total_cached,
    SUM(hit_count) as total_hits,
    (SUM(hit_count)::float / COUNT(*)) as hit_rate
FROM query_cache
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY date DESC;
```

### Check Retrieval Quality

```sql
-- Daily quality metrics
SELECT * FROM daily_retrieval_summary LIMIT 7;

-- Problem queries (low coverage)
SELECT * FROM low_coverage_queries LIMIT 10;

-- Category performance
SELECT * FROM category_performance;
```

### Estimated Cost Savings

```sql
-- Calculate savings from cache
WITH cache_stats AS (
    SELECT SUM(hit_count) as total_hits
    FROM query_cache
    WHERE created_at > NOW() - INTERVAL '7 days'
)
SELECT
    total_hits,
    -- Assume avg 1500 tokens per query (1000 input + 500 output)
    (total_hits * ((1000 * 0.00000015) + (500 * 0.0000006))) as savings_usd
FROM cache_stats;
```

---

## Docker Deployment

### Build and Start

```bash
# Build with new code
docker-compose build backend

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f backend
```

### Verify Backend is Running

```bash
curl http://localhost:8000/health
```

Expected:
```json
{"status": "healthy"}
```

### Test API with Improvements

```bash
curl -X POST http://localhost:8000/api/chat/multimodal \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "YOUR_DOC_ID",
    "question": "What is System Database?",
    "top_k": 5,
    "use_images": false
  }'
```

Look for in Docker logs:
```
Adaptive: complexity=simple, top_k=3, window=1
Retrieved: 3 chunks
Confidence: 95%
Result cached for future queries
```

Second identical request should show:
```
CACHE HIT! Returning cached answer (saved tokens)
```

---

## Rollout Strategy

### Phase 1: Monitoring (Week 1)
- [x] Deploy code
- [ ] Monitor cache hit rate (target: >20%)
- [ ] Monitor retrieval quality (target: >75% coverage)
- [ ] Track cost reduction (target: >25%)

### Phase 2: Optimization (Week 2)
- [ ] Tune adaptive retrieval thresholds
- [ ] Adjust topic mappings based on metrics
- [ ] Review low-coverage queries
- [ ] Optimize cache TTL

### Phase 3: Advanced Features (Week 3+)
- [ ] Enable multi-hop for production
- [ ] Add conversation summaries
- [ ] Implement feedback loop

---

## Troubleshooting

### Cache Not Working

**Symptom**: `cache_hit_rate` stays at 0%

**Solution**:
```python
# Check if cache is properly initialized
from backend.app.utils.query_cache import QueryCache
from database.db_client import DatabaseClient

db = DatabaseClient()
cache = QueryCache(db, ttl_hours=24)

# Try manual cache
cache.cache_answer(
    question="test",
    doc_id="test",
    answer="test answer",
    citations=[],
    question_embedding=[0.1] * 1536
)

# Check if it was saved
result = cache.get_cached_answer("test", "test")
print(f"Cache working: {result is not None}")
```

### Adaptive Retrieval Not Activating

**Symptom**: All queries use same top_k

**Solution**:
Check if the adaptive code is being called:
```bash
# Add debug logging to chat_multimodal.py
print(f"DEBUG: top_k={top_k}, complexity={complexity}")
```

### Answer Verification Failing

**Symptom**: All answers getting low confidence

**Solution**:
Lower confidence threshold or check citation quality:
```python
# In chat_multimodal.py, adjust threshold
if confidence < 0.75:  # Lower from 0.85
    # Add disclaimer
```

---

## Success Metrics (After 1 Week)

Target metrics to achieve:

| Metric | Target | How to Check |
|--------|--------|--------------|
| Cache Hit Rate | >20% | `SELECT AVG(hit_count) FROM query_cache` |
| Cost Reduction | >25% | Compare token usage before/after |
| Topic Coverage | >75% | `SELECT AVG((metrics->>'topic_coverage')::float) FROM retrieval_metrics` |
| Answer Confidence | >85% | Monitor verification logs |
| Complex Query Quality | Improved | User feedback + ground truth tests |

---

## Next Steps

1. **Monitor for 1 week** - Collect baseline metrics
2. **Review dashboards** - Identify optimization opportunities
3. **Tune parameters** - Adjust based on data
4. **User feedback** - Gather qualitative assessment
5. **Iterate** - Continuous improvement

---

## Support

- **Code**: All in `backend/app/utils/`
- **Docs**: QUICK_START.md, INTEGRATION_GUIDE.md
- **Tests**: test_accuracy_seeded.py
- **Migrations**: migrations/010_*.sql, migrations/011_*.sql

---

**Status**: ✅ DEPLOYED AND READY FOR TESTING

Run the seeded accuracy tests to validate everything is working correctly!
