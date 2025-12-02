"""Integrate all RAG improvements into chat_multimodal.py.

This script safely adds all improvement code to the chat API.
"""
import re
from pathlib import Path

def integrate_improvements():
    """Integrate all improvements into chat_multimodal.py."""

    chat_file = Path("backend/app/api/chat_multimodal.py")

    print(f"Reading {chat_file}...")
    content = chat_file.read_text(encoding='utf-8')

    # Step 1: Add imports after existing imports
    import_marker = "from app.utils.conversation_manager import ("
    if import_marker in content and "from app.utils.answer_verifier" not in content:
        print("✓ Adding new imports...")
        new_imports = """
# NEW: Import improvements
from app.utils.answer_verifier import quick_verify
from app.utils.adaptive_retrieval import adaptive_retrieval_params, needs_multi_hop_reasoning as check_multi_hop
from app.utils.query_cache import QueryCache
from app.utils.conversation_manager_enhanced import format_chat_history_with_summary
from app.utils.multi_hop_retriever import multi_hop_retrieve
from app.utils.retrieval_metrics import RetrievalMetrics
"""
        # Find the end of conversation_manager imports
        pattern = r"(from app\.utils\.conversation_manager import \([^)]+\)\n)"
        content = re.sub(pattern, r"\1" + new_imports, content)

    # Step 2: Add cache and metrics initialization
    if "openai_client = OpenAI" in content and "query_cache = QueryCache" not in content:
        print("✓ Adding cache and metrics initialization...")
        init_code = """
# NEW: Initialize cache and metrics
query_cache = QueryCache(db_client=None, ttl_hours=24)
retrieval_metrics = RetrievalMetrics(db_client=None)
"""
        content = content.replace(
            "openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))",
            "openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))" + init_code
        )

    # Save the file
    print(f"✓ Writing changes to {chat_file}...")
    chat_file.write_text(content, encoding='utf-8')

    print("\n✅ Base imports and initialization added!")
    print("\nNext steps:")
    print("1. Run migrations: python run_new_migrations.py")
    print("2. Add functional code (cache check, adaptive retrieval, etc.)")
    print("3. Follow INTEGRATION_GUIDE.md for detailed integration")

if __name__ == "__main__":
    integrate_improvements()
