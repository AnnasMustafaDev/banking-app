#!/usr/bin/env python
"""
Quick Start Script - Bank App Frontend Testing
Run this to start the server and test the APIs via the web interface
"""

import subprocess
import sys
import time
import webbrowser

def main():
    print("\n" + "="*60)
    print("🏦 BANK APP - STARTING SERVER")
    print("="*60 + "\n")
    
    print("📋 ACCOUNT CREATION:")
    print("   • Just enter any Account ID (e.g., user1, user2, alice, bob)")
    print("   • Click 'Load Account' to create it")
    print("   • Account is automatically created with $0 balance")
    print("   • All API calls will work after that!\n")
    
    print("🌐 ACCESSING THE APP:")
    print("   • Frontend: http://localhost:8000")
    print("   • API Docs: http://localhost:8000/docs\n")
    
    print("⏳ Starting server...")
    print("   Press Ctrl+C to stop\n")
    
    try:
        # Give user a moment to read the info
        time.sleep(2)
        
        # Start the server
        subprocess.run([
            sys.executable, "-m", "uvicorn",
            "main:app",
            "--reload",
            "--port", "8000"
        ], cwd="d:\\bank_app")
        
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped. Goodbye!")
        sys.exit(0)

if __name__ == "__main__":
    main()
