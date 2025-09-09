"""FastAPI dependencies."""
import os
from functools import lru_cache

from ..storage.base import StorageBackend
from ..storage.local import LocalStorage
from ..storage.s3 import S3Storage


@lru_cache()
def get_storage() -> StorageBackend:
    """Get storage backend based on environment configuration."""
    storage_type = os.getenv("STORAGE_TYPE", "local").lower()
    
    if storage_type == "s3":
        bucket = os.getenv("S3_BUCKET")
        if not bucket:
            raise ValueError("S3_BUCKET environment variable is required for S3 storage")
        
        prefix = os.getenv("S3_PREFIX", "")
        region = os.getenv("S3_REGION", "us-east-1")
        
        return S3Storage(bucket=bucket, prefix=prefix, region=region)
    
    elif storage_type == "local":
        root_path = os.getenv("LOCAL_ROOT", "./data")
        return LocalStorage(root_path=root_path)
    
    else:
        raise ValueError(f"Unsupported storage type: {storage_type}")


# For testing/development, allow override
_storage_override = None

def override_storage(storage: StorageBackend) -> None:
    """Override storage for testing."""
    global _storage_override
    _storage_override = storage

def clear_storage_override() -> None:
    """Clear storage override."""
    global _storage_override
    _storage_override = None

def get_storage_dependency() -> StorageBackend:
    """Dependency function for FastAPI."""
    if _storage_override is not None:
        return _storage_override
    return get_storage()
