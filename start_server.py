#!/usr/bin/env python3
"""
Simple server startup script for testing
Starts the FastAPI server with proper configuration
"""

import uvicorn
import sys
from pathlib import Path

# Add project root to path
project_root = str(Path(__file__).resolve().parent)
if project_root not in sys.path:
    sys.path.append(project_root)

if __name__ == "__main__":
    print("🚀 Starting FastAPI server for integration testing...")
    print("Server will be available at: http://localhost:8000")
    print("API documentation at: http://localhost:8000/docs")
    print("Press Ctrl+C to stop the server")
    
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
