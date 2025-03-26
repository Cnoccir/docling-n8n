#!/usr/bin/env python3
"""
Debugging script for Docling Extractor components.
Tests core functionality without the full API layer.
"""

import os
import sys
import importlib
import traceback
import asyncio
from pathlib import Path

async def test_imports():
    """Test all the critical imports to identify dependency issues."""
    print("\n=== Testing Module Imports ===")

    modules_to_test = [
        # Core Python modules
        "asyncio", "json", "re", "uuid",

        # Direct dependencies
        "tiktoken",
        "fastapi",
        "docling.document_converter",
        "langchain_text_splitters",

        # Our package modules
        "api.utils.tokenization",
        "api.utils.extraction",
        "api.utils.processing",
        "api.document_processor.core",
        "api.document_processor.adapter"
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
        # Import our modules only after we've checked they can be imported
        from api.utils.tokenization import get_tokenizer
        from api.utils.extraction import extract_technical_terms
        from api.document_processor.core import ProcessingConfig, DocumentProcessor

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

    files_to_check = [
        "api/document_processor/core.py",
        "api/document_processor/adapter.py",
        "api/utils/processing.py",
        "api/utils/extraction.py",
        "api/utils/tokenization.py"
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
        from api.document_processor.core import process_technical_document

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
        print(f"  - Generated {len(result.get('chunks', []))} chunks")
        print(f"  - Extracted {len(result.get('technical_terms', []))} technical terms")
        print(f"  - Generated markdown content with {len(result.get('markdown_content', ''))} characters")

        return True
    except Exception as e:
        print(f"❌ Document processing test failed: {str(e)}")
        traceback.print_exc()
        return False

async def find_core_py_issue():
    """Specifically look for the issue in core.py around line 1941."""
    print("\n=== Finding Issue in core.py ===")

    try:
        core_path = "api/document_processor/core.py"
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

    # Check Python version
    py_version = sys.version.split()[0]
    print(f"Python version: {py_version}")

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
        await test_process_document()
    else:
        print("\n⚠️ Skipping document processing test due to previous errors.")

    print("\n=== Debug Summary ===")
    print(f"Syntax check: {'✅ Passed' if syntax_ok else '❌ Failed'}")
    print(f"Import check: {'✅ Passed' if imports_ok else '❌ Failed'}")
    print(f"Core functions: {'✅ Passed' if core_ok else '❌ Failed' if imports_ok and syntax_ok else '⚠️ Not tested'}")

    if not imports_ok or not syntax_ok or not core_ok:
        print("\n⚠️ Fix the issues above before running the Docker container.")
    else:
        print("\n✅ Basic tests passed. You can try running the Docker container now.")

if __name__ == "__main__":
    asyncio.run(main())
