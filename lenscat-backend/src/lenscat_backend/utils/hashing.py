"""File hashing utilities."""
import asyncio
import hashlib
from typing import Optional

try:
    import blake3
    BLAKE3_AVAILABLE = True
except ImportError:
    BLAKE3_AVAILABLE = False
    blake3 = None

from ..storage.base import StorageBackend


async def compute_file_hash(storage: StorageBackend, path: str) -> Optional[str]:
    """Compute BLAKE3 hash of a file, fallback to SHA256."""
    try:
        data = await storage.read_bytes(path)
        
        if BLAKE3_AVAILABLE:
            # Use BLAKE3 (faster)
            hash_obj = blake3.blake3()
            hash_obj.update(data)
            return f"blake3:{hash_obj.hexdigest()}"
        else:
            # Fallback to SHA256
            hash_obj = hashlib.sha256()
            hash_obj.update(data)
            return f"sha256:{hash_obj.hexdigest()}"
            
    except Exception as e:
        print(f"Failed to compute hash for {path}: {e}")
        return None


async def compute_hash_chunked(storage: StorageBackend, path: str, chunk_size: int = 8192) -> Optional[str]:
    """Compute hash for large files in chunks (for future streaming support)."""
    # For now, just use the simple method since our storage interface
    # doesn't support streaming reads yet
    return await compute_file_hash(storage, path)
