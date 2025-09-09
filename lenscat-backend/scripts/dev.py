#!/usr/bin/env python3
"""Development server runner."""
import os
import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

if __name__ == "__main__":
    import uvicorn
    
    # Set development environment
    os.environ.setdefault("STORAGE_TYPE", "local")
    os.environ.setdefault("LOCAL_ROOT", "./data")
    os.environ.setdefault("HOST", "0.0.0.0")
    os.environ.setdefault("PORT", "8000")
    os.environ.setdefault("RELOAD", "true")
    
    # Create data directory if it doesn't exist
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)
    
    # Add some sample images if directory is empty
    if not any(data_dir.iterdir()):
        print("📁 Data directory is empty. Add some images to ./data to see them in the gallery.")
    
    print("🚀 Starting Lenscat backend in development mode...")
    print(f"📂 Storage: Local ({data_dir.resolve()})")
    print(f"🌐 Server: http://localhost:8000")
    print(f"📖 API Docs: http://localhost:8000/docs")
    
    uvicorn.run(
        "main:app",
        host=os.environ["HOST"],
        port=int(os.environ["PORT"]),
        reload=True,
        reload_dirs=["src"]
    )
