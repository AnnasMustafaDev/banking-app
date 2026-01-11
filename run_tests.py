#!/usr/bin/env python
"""
Test runner script for Bank App
Run this to execute all tests and verify functionality
"""

import subprocess
import sys

def run_tests():
    """Run pytest with detailed output"""
    print("=" * 60)
    print("BANK APP - TEST SUITE")
    print("=" * 60)
    print()
    
    cmd = [
        sys.executable, "-m", "pytest",
        "test_main.py",
        "-v",
        "--tb=short",
        "--color=yes"
    ]
    
    result = subprocess.run(cmd)
    
    print()
    print("=" * 60)
    if result.returncode == 0:
        print("✅ ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED!")
    print("=" * 60)
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(run_tests())
