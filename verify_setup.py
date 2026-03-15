#!/usr/bin/env python3
"""
Setup verification script for Quiz Wiz AI Backend

This script checks that all dependencies are installed and MongoDB is accessible.
"""

import sys
import os
from pathlib import Path


def check_python_version():
    """Check Python version is 3.10+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print(f"❌ Python 3.10+ required (found {version.major}.{version.minor})")
        return False
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    return True


def check_virtual_env():
    """Check if running in virtual environment"""
    in_venv = hasattr(sys, 'real_prefix') or (
        hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
    )
    if not in_venv:
        print("⚠ Not running in virtual environment")
        print("  Recommendation: source venv/bin/activate")
        return False
    print("✓ Virtual environment active")
    return True


def check_required_packages():
    """Check all required packages are installed"""
    required_packages = [
        'fastapi',
        'uvicorn',
        'motor',
        'pymongo',
        'bcrypt',
        'jose',
        'pydantic',
        'PIL',
        'fitz',
        'httpx',
        'dotenv'
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✓ {package}")
        except ImportError:
            missing.append(package)
            print(f"❌ {package}")

    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        print("  Run: pip install -r requirements.txt")
        return False
    return True


def check_mongodb_connection():
    """Check MongoDB is accessible"""
    try:
        from pymongo import MongoClient
        client = MongoClient('mongodb://localhost:27017', serverSelectionTimeoutMS=2000)
        client.admin.command('ping')
        client.close()
        print("✓ MongoDB accessible at mongodb://localhost:27017")
        return True
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        print("  Make sure MongoDB is running:")
        print("    brew services start mongodb-community  # macOS")
        print("    mongod &                               # Manual")
        return False


def check_env_file():
    """Check .env file exists"""
    env_path = Path('.env')
    if env_path.exists():
        print("✓ .env file exists")
        return True
    else:
        print("⚠ .env file not found")
        print("  Creating from .env.example...")
        example_path = Path('.env.example')
        if example_path.exists():
            with open(example_path) as f:
                with open('.env', 'w') as out:
                    out.write(f.read())
            print("✓ Created .env from .env.example")
            return True
        else:
            print("❌ .env.example not found")
            return False


def check_file_structure():
    """Check required file structure"""
    required_files = [
        'requirements.txt',
        '.env.example',
        'app/main.py',
        'app/config.py',
        'app/database.py',
        'app/dependencies.py',
        'app/routers/auth.py',
        'app/routers/scan.py',
        'app/routers/tests.py',
        'app/routers/results.py',
        'app/routers/progress.py',
        'app/services/ai_stub.py'
    ]

    all_exist = True
    for file_path in required_files:
        if Path(file_path).exists():
            print(f"✓ {file_path}")
        else:
            print(f"❌ {file_path}")
            all_exist = False

    return all_exist


def main():
    """Run all checks"""
    print("=" * 60)
    print("Quiz Wiz AI Backend - Setup Verification")
    print("=" * 60)

    checks = [
        ("Python Version", check_python_version),
        ("Virtual Environment", check_virtual_env),
        ("Required Packages", check_required_packages),
        ("File Structure", check_file_structure),
        ("Environment File", check_env_file),
        ("MongoDB Connection", check_mongodb_connection),
    ]

    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        print("-" * 40)
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Check failed: {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("Summary:")
    print("=" * 60)

    all_passed = True
    for name, result in results:
        status = "✓ PASS" if result else "❌ FAIL"
        print(f"{status:8} - {name}")
        if not result:
            all_passed = False

    print("=" * 60)

    if all_passed:
        print("\n✓ All checks passed! Ready to start the server:")
        print("\n  uvicorn app.main:app --reload")
        print("\n  Then visit: http://localhost:8000/docs")
        return 0
    else:
        print("\n❌ Some checks failed. Please fix the issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
