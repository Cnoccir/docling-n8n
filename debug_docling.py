#!/usr/bin/env python3
"""
Enhanced debugging script for Docling Extractor components.
Tests core functionality and displays sample content from extraction.
"""

import os
import sys
import importlib
import traceback
import asyncio
import json
from pathlib import Path

# Set this environment variable to prevent symlink errors on Windows
os.environ['HF_HUB_DISABLE_SYMLINKS_WARNING'] = '1'
# Also disable symlinks completely
os.environ['HF_HUB_DISABLE_SYMLINKS'] = '1'

# Determine if we're running in Docker by checking environment
IN_DOCKER = os.environ.get('PYTHONPATH', '').endswith('/app/api')

# Set up paths for both environments
if IN_DOCKER:
    # In Docker, PYTHONPATH is already set correctly
    DOC_PROCESSOR_PREFIX = "document_processor"
    UTILS_PREFIX = "utils"
else:
    # In local development, we need to simulate the Docker environment
    # by making 'api' directory accessible as if it were the root
    script_dir = os.path.dirname(os.path.abspath(__file__))
    api_dir = os.path.join(script_dir, "api")

    # Insert api directory at the beginning of sys.path
    # This makes modules in api/ accessible as top-level modules
    sys.path.insert(0, api_dir)

    # Now use the Docker-style prefixes
    DOC_PROCESSOR_PREFIX = "document_processor"
    UTILS_PREFIX = "utils"

async def test_imports():
    """Test all the critical imports to identify dependency issues."""
    print("\n=== Testing Module Imports ===")
    print(f"Environment: {'Docker' if IN_DOCKER else 'Local Development'}")
    print(f"Python path includes: {sys.path[0]}")
    print(f"Document processor prefix: {DOC_PROCESSOR_PREFIX}")
    print(f"Utils prefix: {UTILS_PREFIX}")

    modules_to_test = [
        # Core Python modules
        "asyncio", "json", "re", "uuid",

        # Direct dependencies
        "tiktoken",
        "fastapi",
        "docling.document_converter",
        "langchain_text_splitters",

        # Our package modules with dynamic prefixes
        f"{UTILS_PREFIX}.tokenization",
        f"{UTILS_PREFIX}.extraction",
        f"{UTILS_PREFIX}.processing",
        f"{DOC_PROCESSOR_PREFIX}.core",
        f"{DOC_PROCESSOR_PREFIX}.adapter"
    ]

    success_count = 0
    fail_count = 0

    for module in modules_to_test:
        try:
            importlib.import_module(module)
            print(f"✅ Successfully imported {module}")
            success_count += 1
        except ImportError as e:
            print(f"❌ Failed to import {module}: {str(e)}")
            fail_count += 1
        except SyntaxError as e:
            print(f"❌ Syntax error in {module}: {str(e)}")
            fail_count += 1
            # Show syntax error location
            traceback.print_exc(limit=1)
            print()

    print(f"\nImport Results: {success_count} succeeded, {fail_count} failed")
    return fail_count == 0

async def test_core_functions():
    """Test core document processing functionality."""
    print("\n=== Testing Core Functions ===")

    try:
        # Import our modules using the correct prefixes
        tokenization_module = importlib.import_module(f"{UTILS_PREFIX}.tokenization")
        extraction_module = importlib.import_module(f"{UTILS_PREFIX}.extraction")
        core_module = importlib.import_module(f"{DOC_PROCESSOR_PREFIX}.core")

        get_tokenizer = getattr(tokenization_module, "get_tokenizer")
        extract_technical_terms = getattr(extraction_module, "extract_technical_terms")
        ProcessingConfig = getattr(core_module, "ProcessingConfig")
        DocumentProcessor = getattr(core_module, "DocumentProcessor")

        # Test the tokenizer
        print("Testing tokenizer...")
        tokenizer = get_tokenizer("text-embedding-3-small")
        test_text = "This is a test document for processing."
        tokens = tokenizer.encode(test_text)
        print(f"✅ Tokenizer works: '{test_text}' → {len(tokens)} tokens")

        # Test extraction
        print("\nTesting technical term extraction...")
        test_technical_text = "The API uses Python functions and the PageRank algorithm with TensorFlow models."
        terms = extract_technical_terms(test_technical_text)
        print(f"✅ Technical term extraction works: {terms}")

        # Test config creation
        print("\nTesting ProcessingConfig creation...")
        config = ProcessingConfig(
            pdf_id="test_doc_123",
            chunk_size=500,
            chunk_overlap=100,
            extract_technical_terms=True
        )
        print(f"✅ ProcessingConfig created successfully: {config.dict()}")

        # Test DocumentProcessor initialization
        print("\nTesting DocumentProcessor initialization...")
        processor = DocumentProcessor(
            pdf_id="test_doc_123",
            config=config
        )
        print(f"✅ DocumentProcessor initialized successfully")

        return True
    except Exception as e:
        print(f"❌ Core function test failed: {str(e)}")
        traceback.print_exc()
        return False

async def check_syntax():
    """Check for syntax errors in key files."""
    print("\n=== Checking for Syntax Errors ===")

    # Use different paths depending on environment
    path_prefix = "" if IN_DOCKER else "api/"

    files_to_check = [
        f"{path_prefix}document_processor/core.py",
        f"{path_prefix}document_processor/adapter.py",
        f"{path_prefix}utils/processing.py",
        f"{path_prefix}utils/extraction.py",
        f"{path_prefix}utils/tokenization.py"
    ]

    error_count = 0

    for file_path in files_to_check:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()

            # Try to compile the code to check for syntax errors
            compile(code, file_path, 'exec')
            print(f"✅ No syntax errors in {file_path}")
        except SyntaxError as e:
            print(f"❌ Syntax error in {file_path}:")
            print(f"   Line {e.lineno}, column {e.offset}: {e.text.strip()}")
            error_count += 1
        except FileNotFoundError:
            print(f"❓ File not found: {file_path}")
            error_count += 1

    return error_count == 0

async def test_process_document():
    """Test the complete document processing pipeline with a sample PDF."""
    print("\n=== Testing Document Processing Pipeline ===")

    try:
        sample_path = "sample.pdf"
        if not os.path.exists(sample_path):
            print("ℹ️ No sample.pdf found. Skipping document processing test.")
            return True

        # Import the document processing function
        core_module = importlib.import_module(f"{DOC_PROCESSOR_PREFIX}.core")
        process_technical_document = getattr(core_module, "process_technical_document")

        print(f"Testing processing with {sample_path}...")

        # Read the sample file
        with open(sample_path, "rb") as f:
            content = f.read()

        # Process the document
        result = await process_technical_document(
            pdf_id="test_123",
            config={
                "extract_technical_terms": True,
                "extract_procedures": True,
                "process_images": True,
                "process_tables": True,
                "chunk_size": 500,
                "chunk_overlap": 100
            },
            content=content
        )

        print(f"✅ Document processing completed successfully!")
        print(f"  - Generated {len(result.chunks if hasattr(result, 'chunks') else [])} chunks")
        print(f"  - Extracted {len(result.concept_network.primary_concepts if hasattr(result, 'concept_network') and result.concept_network else [])}")
        print(f"  - Generated markdown content with {len(result.markdown_content if hasattr(result, 'markdown_content') else '')}")

        return True
    except Exception as e:
        print(f"❌ Document processing test failed: {str(e)}")
        traceback.print_exc()
        return False

async def display_content_samples(result):
    """Display sample content of each type to verify extraction quality."""
    print("\n=== Content Samples ===")

    # 1. Display a text chunk with metadata
    text_chunks = result.get('text_chunks', [])
    if text_chunks:
        print("\n🔍 TEXT CHUNK SAMPLE:")
        sample_chunk = text_chunks[0]
        print(f"Content (first 200 chars): {sample_chunk.get('content', '')[:200]}...")
        print("\nMetadata:")
        metadata = sample_chunk.get('metadata', {})
        print(f"  - File ID: {metadata.get('file_id', 'N/A')}")
        print(f"  - Hierarchy Level: {metadata.get('hierarchy_level', 'N/A')}")
        print(f"  - Section Headers: {metadata.get('section_headers', [])}")
        print(f"  - Technical Terms: {metadata.get('technical_terms', [])[:5]}...")
        print(f"  - Page Numbers: {metadata.get('page_numbers', [])}")
        print(f"  - Has Code: {metadata.get('has_code', False)}")
        print(f"  - Has Table: {metadata.get('has_table', False)}")
        print(f"  - Has Image: {metadata.get('has_image', False)}")
        print(f"  - Context ID: {metadata.get('context_id', 'N/A')}")
    else:
        print("❌ No text chunks found!")

    # 2. Display an image with metadata
    images = result.get('images', [])
    if images:
        print("\n🖼️ IMAGE SAMPLE:")
        sample_image = images[0]
        print(f"Image ID: {sample_image.get('image_id', 'N/A')}")
        print(f"Caption: {sample_image.get('caption', 'N/A')}")
        print(f"Path: {sample_image.get('path', 'N/A')}")
        print(f"Page Number: {sample_image.get('page_number', 'N/A')}")
        print(f"Section Headers: {sample_image.get('section_headers', [])}")
        print(f"Dimensions: {sample_image.get('width', 'N/A')}x{sample_image.get('height', 'N/A')}")
        print(f"Technical Terms: {sample_image.get('technical_terms', [])}")

        # Display analysis if available
        analysis = sample_image.get('analysis', {})
        if analysis:
            print("Analysis:")
            print(f"  - Type: {analysis.get('type', 'unknown')}")
            print(f"  - Description: {analysis.get('description', 'N/A')}")
    else:
        print("❌ No images found!")

    # 3. Display a table with metadata
    tables = result.get('tables', [])
    if tables:
        print("\n📊 TABLE SAMPLE:")
        sample_table = tables[0]
        print(f"Table ID: {sample_table.get('table_id', 'N/A')}")
        print(f"Caption: {sample_table.get('caption', 'N/A')}")
        print(f"Page Number: {sample_table.get('page_number', 'N/A')}")
        print(f"Section Headers: {sample_table.get('section_headers', [])}")

        # Display headers and a sample row
        headers = sample_table.get('headers', [])
        data = sample_table.get('data', [])
        if headers:
            print(f"Headers: {headers}")
        if data and len(data) > 0:
            print(f"Sample Row: {data[0]}")

        print(f"CSV Path: {sample_table.get('csv_path', 'N/A')}")
        print(f"Context ID: {sample_table.get('context_id', 'N/A')}")
    else:
        print("❌ No tables found!")

    # 4. Display a procedure
    procedures = result.get('procedures', [])
    if procedures:
        print("\n📝 PROCEDURE SAMPLE:")
        sample_proc = procedures[0]
        print(f"Procedure ID: {sample_proc.get('procedure_id', 'N/A')}")
        print(f"Title: {sample_proc.get('title', 'N/A')}")

        # Display content or steps
        if 'content' in sample_proc:
            print(f"Content (first 200 chars): {sample_proc.get('content', '')[:200]}...")

        steps = sample_proc.get('steps', [])
        if steps:
            print(f"Steps: {len(steps)} steps")
            if len(steps) > 0:
                print(f"First Step: {steps[0].get('content', '')[:100]}...")
    else:
        print("❌ No procedures found!")

    print("\nSummary of Content Types:")
    print(f"- Text Chunks: {len(text_chunks)}")
    print(f"- Images: {len(images)}")
    print(f"- Tables: {len(tables)}")
    print(f"- Procedures: {len(procedures)}")

    # Display document metadata
    doc_meta = result.get('document_metadata', {})
    if doc_meta:
        print("\n📄 DOCUMENT METADATA:")
        print(f"Domain Category: {result.get('domain_category', 'N/A')}")
        print(f"Page Count: {doc_meta.get('page_count', 'N/A')}")
        print(f"Primary Technical Terms: {doc_meta.get('primary_technical_terms', [])[:10]}...")
        print(f"Content Types: {doc_meta.get('content_types', [])}")

    print("\n✅ Sample content verification complete!")

async def test_multimodal_extraction():
    """Test the multi-modal extraction pipeline with Supabase preparation."""
    print("\n=== Testing Multi-Modal Extraction Pipeline ===")

    try:
        # Find a sample PDF or create a simple one
        sample_path = "sample.pdf"
        if not os.path.exists(sample_path):
            print("ℹ️ No sample.pdf found. Creating simple test PDF...")
            # Create a simple PDF for testing
            try:
                from reportlab.pdfgen import canvas
                c = canvas.Canvas("sample.pdf")
                c.drawString(100, 750, "Test Document")
                c.drawString(100, 700, "This is a test document with some technical terms.")
                c.drawString(100, 650, "API, module, function, database")
                c.save()
                print("✓ Created simple test PDF")
            except ImportError:
                print("❌ Could not create test PDF (reportlab not installed)")
                return True

        # Import the processor with the correct prefix
        adapter_module = importlib.import_module(f"{DOC_PROCESSOR_PREFIX}.adapter")
        APIDocumentProcessor = getattr(adapter_module, "APIDocumentProcessor")

        # Read the sample file
        with open(sample_path, "rb") as f:
            content = f.read()

        print("Creating processor...")
        processor = APIDocumentProcessor(
            pdf_id="test_multimodal",
            config={
                "extract_technical_terms": True,
                "extract_procedures": True,
                "extract_relationships": True,
                "process_images": True,
                "process_tables": True,
                "chunk_size": 500,
                "chunk_overlap": 100
            }
        )

        print("Processing document...")
        result = await processor.process_document(content)

        # Verify structure
        print("\nVerifying result structure:")
        print(f"✓ file_id: {result.get('file_id', 'MISSING')}")

        # Check if we have actual content
        text_chunks = result.get('text_chunks', [])
        print(f"✓ text_chunks: {len(text_chunks)} items")
        if len(text_chunks) == 0:
            print("⚠️ Warning: No text chunks extracted")

        images = result.get('images', [])
        print(f"✓ images: {len(images)} items")

        tables = result.get('tables', [])
        print(f"✓ tables: {len(tables)} items")

        procedures = result.get('procedures', [])
        print(f"✓ procedures: {len(procedures)} items")

        print(f"✓ domain_category: {result.get('domain_category', 'MISSING')}")

        # Fail the test if no content was extracted
        if len(text_chunks) == 0:
            print("❌ Test considered failed: No text content extracted")
            return False

        # Check context IDs for relationships
        print("\nChecking context IDs for relationships:")
        if text_chunks:
            context_id = text_chunks[0]['metadata'].get('context_id', 'MISSING')
            print(f"✓ Text chunk context_id: {context_id}")
        if images:
            context_id = images[0].get('context_id', 'MISSING')
            print(f"✓ Image context_id: {context_id}")
        if tables:
            context_id = tables[0].get('context_id', 'MISSING')
            print(f"✓ Table context_id: {context_id}")

        # NEW: Display content samples
        await display_content_samples(result)

        # Save sample of result to a JSON file for inspection
        try:
            sample_result = {
                "file_id": result.get('file_id', ''),
                "text_chunks": text_chunks[:2] if text_chunks else [],
                "images": images[:1] if images else [],
                "tables": tables[:1] if tables else [],
                "procedures": procedures[:1] if procedures else [],
                "document_metadata": result.get('document_metadata', {})
            }

            with open('extraction_sample.json', 'w', encoding='utf-8') as f:
                json.dump(sample_result, f, indent=2, ensure_ascii=False)
            print("\n✅ Sample result saved to extraction_sample.json")
        except Exception as e:
            print(f"\n⚠️ Failed to save sample result: {e}")

        print("\n✅ Multi-modal extraction test completed successfully!")
        return True
    except Exception as e:
        print(f"❌ Multi-modal extraction test failed: {str(e)}")
        traceback.print_exc()
        return False

async def find_core_py_issue():
    """Specifically look for the issue in core.py around line 1941."""
    print("\n=== Finding Issue in core.py ===")

    # Use different path depending on environment
    path_prefix = "" if IN_DOCKER else "api/"
    core_path = f"{path_prefix}document_processor/core.py"

    try:
        if not os.path.exists(core_path):
            print(f"❌ File not found: {core_path}")
            return False

        with open(core_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # Look around line 1941
        start_line = max(0, 1935)
        end_line = min(len(lines), 1945)

        print(f"Examining lines {start_line} to {end_line} in core.py:")
        for i in range(start_line, end_line):
            line_num = i + 1  # Line numbers start at 1
            print(f"{line_num:4d}: {lines[i].rstrip()}")

            # Look for the problematic line
            if "title_match = re.search" in lines[i]:
                print(f"\n⚠️ Potential issue found at line {line_num}:")
                print(f"   {lines[i].strip()}")

                # Check if the string is properly terminated
                if lines[i].count("'") % 2 != 0 and lines[i].count('"') % 2 != 0:
                    print("   Issue: Unterminated string literal")

                    # Try to fix the line
                    corrected = lines[i].replace(
                        "title_match = re.search(r'^#\\s+(.+), text, re.MULTILINE)",
                        "title_match = re.search(r'^#\\s+(.+)$', text, re.MULTILINE)"
                    )

                    print("   Suggested fix:")
                    print(f"   {corrected.strip()}")

                    # Ask if we should fix it
                    response = input("\nWould you like to fix this issue? (y/n): ")
                    if response.lower() == 'y':
                        lines[i] = corrected
                        with open(core_path, 'w', encoding='utf-8') as f:
                            f.writelines(lines)
                        print("✅ Fixed the issue in core.py")

                    return True

        print("No obvious syntax issues found in this section of core.py.")
        return True
    except Exception as e:
        print(f"❌ Error examining core.py: {str(e)}")
        traceback.print_exc()
        return False

async def check_missing_dependencies():
    """Check for missing Python dependencies."""
    print("\n=== Checking for Missing Dependencies ===")

    required_packages = [
        "fastapi",
        "uvicorn",
        "python-multipart",
        "aiofiles",
        "docling",
        "pydantic",
        "openai",
        "tiktoken",
        "pillow",
        "pdf2image",
        "python-magic",
        "pytesseract",
        "langchain-text-splitters"
    ]

    missing = []
    for package in required_packages:
        try:
            importlib.import_module(package.replace('-', '_'))
            print(f"✅ {package} is installed")
        except ImportError:
            missing.append(package)
            print(f"❌ {package} is not installed")

    if missing:
        print("\nMissing packages:")
        command = f"pip install {' '.join(missing)}"
        print(f"Run: {command}")

        response = input("\nInstall missing packages now? (y/n): ")
        if response.lower() == 'y':
            import subprocess
            print(f"Running: {command}")
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print("✅ Successfully installed missing packages")
            else:
                print(f"❌ Installation failed: {result.stderr}")
    else:
        print("\nAll required packages are installed.")

    return len(missing) == 0

async def main():
    """Main debug function."""
    # Make sure we're in the project root
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    print("=== Docling Extractor Debugging Script ===")
    print(f"Current directory: {os.getcwd()}")
    print(f"Running in: {'Docker container' if IN_DOCKER else 'Local environment with Docker-like imports'}")

    # Add the current directory to the Python path
    sys.path.insert(0, os.getcwd())

    # Check for missing dependencies
    await check_missing_dependencies()

    # Find and fix the specific issue in core.py
    await find_core_py_issue()

    # Check for syntax errors
    syntax_ok = await check_syntax()

    # Test imports
    imports_ok = await test_imports()

    # If imports and syntax are ok, test core functions
    if imports_ok and syntax_ok:
        core_ok = await test_core_functions()
    else:
        core_ok = False
        print("\n⚠️ Skipping core function tests due to import or syntax errors.")

    # If everything is ok so far, test document processing
    if imports_ok and syntax_ok and core_ok:
        doc_ok = await test_process_document()
        # Now also test multi-modal extraction
        multimodal_ok = await test_multimodal_extraction()
    else:
        doc_ok = False
        multimodal_ok = False
        print("\n⚠️ Skipping document processing and multi-modal tests due to previous errors.")

    print("\n=== Debug Summary ===")
    print(f"Syntax check: {'✅ Passed' if syntax_ok else '❌ Failed'}")
    print(f"Import check: {'✅ Passed' if imports_ok else '❌ Failed'}")
    print(f"Core functions: {'✅ Passed' if core_ok else '❌ Failed' if imports_ok and syntax_ok else '⚠️ Not tested'}")
    print(f"Document processing: {'✅ Passed' if doc_ok else '❌ Failed' if core_ok else '⚠️ Not tested'}")
    print(f"Multi-modal extraction: {'✅ Passed' if multimodal_ok else '❌ Failed' if core_ok else '⚠️ Not tested'}")

    # Update at the end of the main function
    if not imports_ok or not syntax_ok:
        print("\n⚠️ Critical issues detected. Fix import and syntax errors first.")
    elif not core_ok:
        print("\n⚠️ Core function issues detected. Fix core.py and related modules.")
    elif not doc_ok:
        print("\n⚠️ Document processing issues detected. This might be fixable in Docker environment.")
    elif not multimodal_ok:
        print("\n⚠️ Multi-modal extraction issues detected. Check adapter.py implementation.")
    else:
        print("\n✅ All tests passed. Your Docling Extractor is ready for use!")

if __name__ == "__main__":
    asyncio.run(main())
