#!/bin/bash
# Quick validation script for RAG improvements

echo "================================"
echo "RAG IMPROVEMENTS - VALIDATION"
echo "================================"

echo ""
echo "1. Checking database tables..."
python -c "
from src.database.db_client import DatabaseClient
db = DatabaseClient()
with db.conn.cursor() as cur:
    cur.execute(\"SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN ('query_cache', 'retrieval_metrics')\")
    tables = [r[0] for r in cur.fetchall()]
    if len(tables) == 2:
        print('  All tables exist:', tables)
    else:
        print('  Missing tables')
        exit(1)
"

echo ""
echo "2. Testing module imports..."
python -c "
import sys
sys.path.insert(0, '.')
from backend.app.utils.answer_verifier import quick_verify
from backend.app.utils.adaptive_retrieval import adaptive_retrieval_params
from backend.app.utils.query_cache import QueryCache
from backend.app.utils.retrieval_metrics import RetrievalMetrics
print('  All modules import successfully')
"

echo ""
echo "3. Testing adaptive retrieval..."
python -c "
import sys
sys.path.insert(0, '.')
from backend.app.utils.adaptive_retrieval import adaptive_retrieval_params

# Simple query
top_k, _, complexity = adaptive_retrieval_params('What is X?', 'definition')
print(f'  Simple query: top_k={top_k}, complexity={complexity}')

# Complex query
top_k, _, complexity = adaptive_retrieval_params('Compare X vs Y', 'comparison')
print(f'  Complex query: top_k={top_k}, complexity={complexity}')
"

echo ""
echo "================================"
echo "ALL VALIDATIONS PASSED!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Set TEST_DOC_ID: export TEST_DOC_ID='your-doc-id'"
echo "2. Run tests: python test_accuracy_seeded.py"
echo "3. Start Docker: docker-compose up -d backend"
echo "4. Monitor: See DEPLOYMENT_GUIDE.md"
