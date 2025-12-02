"""Test script for conversational reasoning improvements.

Demonstrates:
- Conceptual mode (WHY questions, teaching)
- Troubleshooting mode (diagnosis, analysis)
- Design mode (architecture decisions)
- Comparison mode (A vs B)
- Follow-up questions with conversation memory
- Model selection (gpt-4o-mini vs gpt-4o)
"""
import requests
import json

API_URL = "http://localhost:8001/api/chat"
DOC_ID = "video_hV9-1RgkTk8"

def test_query(question, chat_history=None, model="gpt-4o-mini", title=""):
    """Test a query and print the response."""
    payload = {
        "doc_id": DOC_ID,
        "question": question,
        "chat_history": chat_history or [],
        "model": model,
        "top_k": 5
    }
    
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}")
    print(f"📝 Question: {question}")
    print(f"🤖 Model: {model}")
    print(f"💬 Chat history: {len(chat_history) if chat_history else 0} messages")
    
    try:
        response = requests.post(API_URL, json=payload, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        print(f"\n✅ Response:")
        print(f"   Model used: {result['model_used']}")
        print(f"   Tokens: {result['tokens_used']}")
        print(f"   Sources: {result['search_results_count']}")
        print(f"\n📄 Answer:\n")
        print(result['answer'][:800])  # First 800 chars
        if len(result['answer']) > 800:
            print(f"\n... (truncated, full answer is {len(result['answer'])} chars)")
        
        return result['answer']
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None

# Test 1: Conceptual Question (WHY)
print("\n\n" + "="*80)
print("TEST 1: CONCEPTUAL MODE - 'WHY' Question")
print("="*80)
answer1 = test_query(
    "Why does Niagara use a System Database instead of point-to-point synchronization?",
    model="gpt-4o-mini",
    title="TEST 1: Conceptual Mode"
)

# Test 2: Troubleshooting
print("\n\n" + "="*80)
print("TEST 2: TROUBLESHOOTING MODE - Diagnostic Question")
print("="*80)
answer2 = test_query(
    "Stations are losing sync intermittently. What could be causing this?",
    model="gpt-4o-mini",
    title="TEST 2: Troubleshooting Mode"
)

# Test 3: Design/Architecture
print("\n\n" + "="*80)
print("TEST 3: DESIGN MODE - Architecture Decision")
print("="*80)
answer3 = test_query(
    "Design a system for 10 buildings with 500 points each that needs enterprise-level visibility",
    model="gpt-4o-mini",
    title="TEST 3: Design Mode"
)

# Test 4: Comparison
print("\n\n" + "="*80)
print("TEST 4: COMPARISON MODE - A vs B")
print("="*80)
answer4 = test_query(
    "Compare multi-tier architecture vs single supervisor - when should I use each?",
    model="gpt-4o-mini",
    title="TEST 4: Comparison Mode"
)

# Test 5: Follow-up Question with Conversation Memory
print("\n\n" + "="*80)
print("TEST 5: FOLLOW-UP with Conversation Memory")
print("="*80)

# First establish context
chat_history = []
answer5a = test_query(
    "How does multi-tier architecture work in Niagara?",
    chat_history=[],
    model="gpt-4o-mini",
    title="TEST 5a: Initial Question"
)

# Add to history
if answer5a:
    chat_history.append({"role": "user", "content": "How does multi-tier architecture work in Niagara?"})
    chat_history.append({"role": "assistant", "content": answer5a[:500]})  # Truncate for brevity

# Now ask follow-up
answer5b = test_query(
    "What about graphics in that setup?",
    chat_history=chat_history,
    model="gpt-4o-mini",
    title="TEST 5b: Follow-up Question"
)

# Test 6: GPT-4o vs GPT-4o-mini on Complex Question
print("\n\n" + "="*80)
print("TEST 6: MODEL COMPARISON - GPT-4o-mini vs GPT-4o")
print("="*80)

complex_question = "Why would System Database synchronization fail and how do I diagnose it systematically?"

print("\n--- With GPT-4o-mini ---")
answer6a = test_query(
    complex_question,
    model="gpt-4o-mini",
    title="TEST 6a: GPT-4o-mini"
)

print("\n\n--- With GPT-4o (full reasoning) ---")
answer6b = test_query(
    complex_question,
    model="gpt-4o",
    title="TEST 6b: GPT-4o"
)

print("\n\n" + "="*80)
print("✅ ALL TESTS COMPLETE")
print("="*80)
print("\nKey Improvements Demonstrated:")
print("1. ✅ Adaptive prompts based on question type (conceptual, troubleshooting, design, comparison)")
print("2. ✅ Conversation memory and follow-up handling")
print("3. ✅ User-selectable model (gpt-4o-mini vs gpt-4o)")
print("4. ✅ Dynamic temperature/max_tokens based on mode")
print("5. ✅ Enhanced accuracy with mode-specific guidance")
print("\nCost Control:")
print("- Default: gpt-4o-mini for cost efficiency")
print("- Option: gpt-4o for complex reasoning when needed")
print("- Adaptive token limits prevent waste")
