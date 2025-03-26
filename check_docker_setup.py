import os
import sys
import importlib
from pathlib import Path

REQUIRED_DIRS = [
    "api",
    "api/document_processor",
    "api/utils",
]

REQUIRED_FILES = [
    "api/app.py",
    "api/Dockerfile",
    "api/requirements.txt",
    "api/document_processor/adapter.py",
    "api/document_processor/core.py",
    "api/utils/extraction.py",
    "api/utils/processing.py",
    "api/utils/tokenization.py",
]

REQUIRED_IMPORTS = [
    "document_processor.adapter",
    "document_processor.core",
    "utils.extraction",
    "utils.processing",
    "utils.tokenization",
]

EXPECTED_PYTHONPATH = str(Path.cwd() / "api")


def check_structure():
    print("🧱 Checking folder structure...")
    for d in REQUIRED_DIRS:
        if not Path(d).is_dir():
            print(f"❌ Missing directory: {d}")
            return False
    print("✅ Folder structure looks good.")
    return True


def check_files():
    print("\n📄 Checking required files...")
    for f in REQUIRED_FILES:
        if not Path(f).is_file():
            print(f"❌ Missing file: {f}")
            return False
    print("✅ All required files are present.")
    return True


def check_imports():
    print("\n📦 Checking imports (PYTHONPATH = api)...")
    sys.path.insert(0, EXPECTED_PYTHONPATH)
    success = True
    for module in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module)
            print(f"✅ {module}")
        except Exception as e:
            print(f"❌ Failed to import {module}: {e}")
            success = False
    sys.path.pop(0)
    return success


def check_dockerfile():
    print("\n🐳 Checking Dockerfile for correct PYTHONPATH...")
    dockerfile_path = Path("api/Dockerfile")
    if not dockerfile_path.exists():
        print("❌ Dockerfile not found at api/Dockerfile")
        return False
    with open(dockerfile_path, "r") as f:
        contents = f.read()
    if 'ENV PYTHONPATH="/app/api"' not in contents:
        print("❌ Missing or incorrect PYTHONPATH in Dockerfile.")
        return False
    print("✅ Dockerfile PYTHONPATH is set correctly.")
    return True


def main():
    print("=== 🔍 Pre-Docker Setup Checker ===\n")
    passed = all([
        check_structure(),
        check_files(),
        check_imports(),
        check_dockerfile()
    ])

    if passed:
        print("\n🎉 All checks passed. You're good to build and run Docker!")
    else:
        print("\n⚠️ Fix the issues above before building the Docker image.")


if __name__ == "__main__":
    main()
