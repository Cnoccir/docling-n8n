#!/bin/bash

# Test Script for AME RAG Agent V3 (FIXED)
# This script tests all error handling and execution paths

# CONFIGURATION
WEBHOOK_URL="https://your-n8n-instance.com/webhook/rag-chat-v3"
USER_ID="test_user_$(date +%s)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "========================================="
echo "AME RAG Agent V3 (FIXED) - Test Suite"
echo "========================================="
echo ""
echo "Testing URL: $WEBHOOK_URL"
echo "User ID: $USER_ID"
echo ""

# Test counter
TESTS_PASSED=0
TESTS_FAILED=0

# Helper function to run test
run_test() {
    local test_name="$1"
    local query="$2"
    local expected_field="$3"
    local expected_value="$4"

    echo -e "${BLUE}TEST: $test_name${NC}"
    echo "Query: \"$query\""

    response=$(curl -s -X POST "$WEBHOOK_URL" \
        -H "Content-Type: application/json" \
        -d "{\"query\": \"$query\", \"user_id\": \"$USER_ID\"}")

    echo "Response preview: ${response:0:200}..."

    if [[ -n "$expected_field" ]]; then
        if echo "$response" | jq -e ".$expected_field" > /dev/null 2>&1; then
            actual_value=$(echo "$response" | jq -r ".$expected_field")
            if [[ "$actual_value" == "$expected_value" ]]; then
                echo -e "${GREEN}✅ PASS${NC} - Field '$expected_field' = '$expected_value'"
                ((TESTS_PASSED++))
            else
                echo -e "${RED}❌ FAIL${NC} - Expected '$expected_value', got '$actual_value'"
                ((TESTS_FAILED++))
            fi
        else
            echo -e "${RED}❌ FAIL${NC} - Field '$expected_field' not found"
            ((TESTS_FAILED++))
        fi
    else
        echo -e "${YELLOW}ℹ INFO${NC} - Manual verification needed"
    fi

    echo ""
    echo "---"
    echo ""
}

# ===========================================
# TEST 1: Empty Query (Error Handling)
# ===========================================
run_test "Empty Query Error Handling" \
    "" \
    "error" \
    "true"

# ===========================================
# TEST 2: Greeting (Fast Path)
# ===========================================
run_test "Greeting Fast Path" \
    "Hello" \
    "metadata.queryType" \
    "greeting"

# ===========================================
# TEST 3: Vague Query (Clarification Path)
# ===========================================
run_test "Vague Query Clarification" \
    "How does it work?" \
    "clarification_needed" \
    "true"

# ===========================================
# TEST 4: Ambiguous Query (Clarification Path)
# ===========================================
run_test "Ambiguous Term Clarification" \
    "Configure the pump" \
    "clarification_needed" \
    "true"

# ===========================================
# TEST 5: Normal Technical Query (Full RAG)
# ===========================================
echo -e "${BLUE}TEST: Normal Technical Query (Full RAG Pipeline)${NC}"
echo "Query: \"How to configure KitControl PID loop for temperature control?\""

response=$(curl -s -X POST "$WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"query\": \"How to configure KitControl PID loop for temperature control?\", \"user_id\": \"$USER_ID\"}")

echo "Full response:"
echo "$response" | jq '.'

# Check multiple fields
checks=0
if echo "$response" | jq -e '.answer' > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Has answer field"
    ((checks++))
fi

if echo "$response" | jq -e '.citations' > /dev/null 2>&1; then
    citations_count=$(echo "$response" | jq '.citations | length')
    echo -e "${GREEN}✅${NC} Has $citations_count citations"
    ((checks++))
fi

if echo "$response" | jq -e '.golden_chunks' > /dev/null 2>&1; then
    chunks_count=$(echo "$response" | jq '.golden_chunks | length')
    echo -e "${GREEN}✅${NC} Has $chunks_count golden chunks"
    ((checks++))
fi

if echo "$response" | jq -e '.metadata.fusion_stats' > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Has fusion stats"
    ((checks++))
fi

if echo "$response" | jq -e '.metadata.reranking_stats' > /dev/null 2>&1; then
    rerank_failed=$(echo "$response" | jq -r '.metadata.reranking_stats.reranking_failed // false')
    if [[ "$rerank_failed" == "false" ]]; then
        echo -e "${GREEN}✅${NC} Reranking succeeded"
    else
        echo -e "${YELLOW}⚠${NC} Reranking failed, used fallback"
    fi
    ((checks++))
fi

if echo "$response" | jq -e '.debug.pipeline' > /dev/null 2>&1; then
    pipeline=$(echo "$response" | jq -r '.debug.pipeline')
    echo -e "${GREEN}✅${NC} Pipeline: $pipeline"
    ((checks++))
fi

if [[ $checks -ge 5 ]]; then
    echo -e "${GREEN}✅ PASS${NC} - Full RAG pipeline executed successfully"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC} - Only $checks/6 checks passed"
    ((TESTS_FAILED++))
fi

echo ""
echo "---"
echo ""

# ===========================================
# TEST 6: Query with Visual Request
# ===========================================
run_test "Query Requesting Visuals" \
    "Show me the wiring diagram for analog output" \
    "metadata.query_type" \
    "technical"

# ===========================================
# TEST 7: Very Short Query (Edge Case)
# ===========================================
run_test "Very Short Query" \
    "PID" \
    "clarification_needed" \
    "true"

# ===========================================
# SUMMARY
# ===========================================
echo "========================================="
echo "TEST SUMMARY"
echo "========================================="
echo -e "Total Tests: $((TESTS_PASSED + TESTS_FAILED))"
echo -e "${GREEN}Passed: $TESTS_PASSED${NC}"
echo -e "${RED}Failed: $TESTS_FAILED${NC}"
echo ""

if [[ $TESTS_FAILED -eq 0 ]]; then
    echo -e "${GREEN}🎉 ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}⚠️  SOME TESTS FAILED${NC}"
    echo "Review the output above for details."
    exit 1
fi
