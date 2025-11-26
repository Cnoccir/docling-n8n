"""Add semantic search to existing documents.

This script generates summary embeddings for all documents in document_index
that don't already have embeddings, enabling semantic search capability.
"""
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from database.db_client import DatabaseClient
from utils.embeddings import EmbeddingGenerator


def main():
    """Generate embeddings for existing document summaries."""
    db = DatabaseClient()
    emb_gen = EmbeddingGenerator()

    print("📊 Fetching documents without embeddings...")
    print("=" * 60)

    with db:
        with db.conn.cursor() as cur:
            # Find all completed documents that have a summary but no embedding
            cur.execute("""
                SELECT id, title, summary
                FROM document_index
                WHERE status = 'completed'
                  AND summary IS NOT NULL
                  AND summary != ''
                  AND summary_embedding IS NULL
                ORDER BY created_at DESC
            """)
            docs = cur.fetchall()

    if not docs:
        print("✅ All documents already have embeddings!")
        return

    print(f"Found {len(docs)} documents to process\n")

    success_count = 0
    error_count = 0

    for doc_id, title, summary in docs:
        try:
            print(f"Processing: {title}")
            print(f"  Doc ID: {doc_id}")

            # Generate embedding from title + summary
            # This provides better semantic context than summary alone
            text = f"{title}\n\n{summary}"

            print(f"  Generating embedding for {len(text)} characters...")
            embedding = emb_gen.generate_embeddings([text])[0]

            print(f"  Embedding generated: {len(embedding)} dimensions")

            # Update existing row (not insert new!)
            # Create a new connection for each update
            db_update = DatabaseClient()
            with db_update:
                with db_update.conn.cursor() as cur:
                    cur.execute("""
                        UPDATE document_index
                        SET summary_embedding = %s,
                            updated_at = NOW()
                        WHERE id = %s
                    """, (embedding, doc_id))
                    db_update.conn.commit()

            print(f"  ✓ Embedding saved to database\n")
            success_count += 1

        except Exception as e:
            print(f"  ✗ Error: {e}\n")
            error_count += 1
            continue

    print("=" * 60)
    print(f"✅ Complete! {success_count} documents now searchable.")
    if error_count > 0:
        print(f"⚠️  {error_count} documents failed.")
    print("\nSemantic search is now enabled!")
    print("Use the API with: ?search=your_query&semantic=true")


if __name__ == '__main__':
    main()
