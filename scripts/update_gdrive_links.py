"""
Batch update Google Drive links for existing documents.

Usage:
    python scripts/update_gdrive_links.py

This script will:
1. Find all documents without Google Drive links
2. Allow you to manually add Google Drive links
3. Update the database
"""
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from database.db_client import DatabaseClient


def extract_file_id_from_url(url: str) -> str:
    """Extract file ID from Google Drive URL."""
    # Format 1: https://drive.google.com/file/d/{file_id}/view
    if '/file/d/' in url:
        parts = url.split('/file/d/')
        if len(parts) > 1:
            file_id = parts[1].split('/')[0]
            return file_id

    # Format 2: https://drive.google.com/open?id={file_id}
    if 'id=' in url:
        parts = url.split('id=')
        if len(parts) > 1:
            file_id = parts[1].split('&')[0]
            return file_id

    raise ValueError(f"Could not extract file ID from URL: {url}")


def update_document_gdrive(doc_id: str, gdrive_url: str):
    """Update a document's Google Drive information."""
    try:
        file_id = extract_file_id_from_url(gdrive_url)

        # Normalize URL
        normalized_url = f"https://drive.google.com/file/d/{file_id}/view"

        db = DatabaseClient()
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    UPDATE document_index
                    SET gdrive_file_id = %s,
                        gdrive_link = %s
                    WHERE id = %s
                """, (file_id, normalized_url, doc_id))
                db.conn.commit()

        print(f"✅ Updated {doc_id}")
        print(f"   File ID: {file_id}")
        print(f"   Link: {normalized_url}")
        return True

    except Exception as e:
        print(f"❌ Failed to update {doc_id}: {e}")
        return False


def list_documents_without_gdrive():
    """List all documents that don't have Google Drive links."""
    db = DatabaseClient()

    try:
        with db:
            with db.conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, filename, created_at
                    FROM document_index
                    WHERE gdrive_link IS NULL
                    ORDER BY created_at DESC
                """)

                docs = cur.fetchall()

                if not docs:
                    print("✅ All documents have Google Drive links!")
                    return []

                print(f"\n📄 Found {len(docs)} documents without Google Drive links:\n")

                result = []
                for row in docs:
                    doc_info = {
                        'id': row[0],
                        'title': row[1],
                        'filename': row[2],
                        'created_at': row[3]
                    }
                    result.append(doc_info)
                    print(f"{len(result)}. {doc_info['title']}")
                    print(f"   ID: {doc_info['id']}")
                    print(f"   File: {doc_info['filename']}")
                    print(f"   Created: {doc_info['created_at']}")
                    print()

                return result

    except Exception as e:
        print(f"❌ Error: {e}")
        return []


def interactive_update():
    """Interactive mode to update documents one by one."""
    docs = list_documents_without_gdrive()

    if not docs:
        return

    print("\n" + "="*60)
    print("Interactive Update Mode")
    print("="*60)
    print("\nEnter Google Drive URLs for each document.")
    print("Press Enter to skip a document.")
    print("Type 'quit' to exit.\n")

    updated_count = 0

    for i, doc in enumerate(docs, 1):
        print(f"\n[{i}/{len(docs)}] {doc['title']}")
        print(f"    Document ID: {doc['id']}")

        url = input("    Google Drive URL: ").strip()

        if url.lower() == 'quit':
            print("\n👋 Exiting...")
            break

        if not url:
            print("    ⏭️  Skipped")
            continue

        if update_document_gdrive(doc['id'], url):
            updated_count += 1

    print(f"\n✅ Updated {updated_count} out of {len(docs)} documents")


def batch_update_from_file(csv_file: str):
    """
    Batch update from CSV file.

    CSV format:
    doc_id,gdrive_url
    docProvisioning_c0a072cb,https://drive.google.com/file/d/xxx/view
    """
    import csv

    print(f"\n📁 Reading from {csv_file}...")

    updated_count = 0
    failed_count = 0

    try:
        with open(csv_file, 'r') as f:
            reader = csv.DictReader(f)

            for row in reader:
                doc_id = row.get('doc_id', '').strip()
                gdrive_url = row.get('gdrive_url', '').strip()

                if not doc_id or not gdrive_url:
                    print(f"⚠️  Skipping invalid row: {row}")
                    continue

                if update_document_gdrive(doc_id, gdrive_url):
                    updated_count += 1
                else:
                    failed_count += 1

        print(f"\n✅ Updated {updated_count} documents")
        if failed_count > 0:
            print(f"❌ Failed to update {failed_count} documents")

    except FileNotFoundError:
        print(f"❌ File not found: {csv_file}")
    except Exception as e:
        print(f"❌ Error reading CSV: {e}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Update Google Drive links for documents')
    parser.add_argument('--csv', type=str, help='CSV file with doc_id,gdrive_url')
    parser.add_argument('--list', action='store_true', help='List documents without links')
    parser.add_argument('--interactive', action='store_true', help='Interactive mode')
    parser.add_argument('--doc-id', type=str, help='Update specific document by ID')
    parser.add_argument('--url', type=str, help='Google Drive URL (use with --doc-id)')

    args = parser.parse_args()

    if args.csv:
        batch_update_from_file(args.csv)
    elif args.list:
        list_documents_without_gdrive()
    elif args.doc_id and args.url:
        update_document_gdrive(args.doc_id, args.url)
    elif args.interactive or (not args.csv and not args.list):
        interactive_update()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
