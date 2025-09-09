import uvicorn
from .main import app


def main() -> None:
    """Run the FastAPI application server."""
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=["src"]
    )
