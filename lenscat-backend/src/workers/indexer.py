"""Indexing worker for building manifests."""
import asyncio
from datetime import datetime
from typing import List, Optional

import orjson

from ..models.types import FolderIndex, RollupItem, RollupManifest, Sidecar
from ..storage.base import StorageBackend
from ..utils import compute_file_hash, extract_exif


class FolderIndexer:
    """Builds and maintains folder index manifests."""

    def __init__(self, storage: StorageBackend):
        """Initialize indexer with storage backend."""
        self.storage = storage

    async def build_folder_index(self, folder_path: str) -> FolderIndex:
        """Build _index.json for a folder."""
        dirs, items = await self.storage.list_directory(folder_path)
        
        # Enrich items with hashes and EXIF if missing
        enriched_items = []
        for item in items:
            # Check if we have a sidecar with hash
            sidecar_path = f"{item.path}.json"
            hash_value = item.hash
            
            if await self.storage.exists(sidecar_path):
                try:
                    sidecar_data = await self.storage.read_text(sidecar_path)
                    sidecar = Sidecar.parse_raw(sidecar_data)
                    if sidecar.hash:
                        hash_value = sidecar.hash
                except Exception:
                    pass
            
            # Compute hash if missing
            if not hash_value:
                hash_value = await compute_file_hash(self.storage, item.path)
            
            # Update item
            enriched_items.append(item.copy(update={"hash": hash_value}))
        
        return FolderIndex(
            path=folder_path,
            generatedAt=datetime.utcnow(),
            items=enriched_items,
            dirs=dirs
        )

    async def save_folder_index(self, folder_path: str, index: FolderIndex) -> None:
        """Save folder index to _index.json."""
        index_path = f"{folder_path.rstrip('/')}/_index.json"
        
        # Serialize with orjson for performance
        data = orjson.dumps(
            index.dict(by_alias=True), 
            option=orjson.OPT_UTC_Z | orjson.OPT_INDENT_2
        )
        
        await self.storage.write_bytes(index_path, data)

    async def build_and_save_index(self, folder_path: str) -> FolderIndex:
        """Build and save folder index in one operation."""
        index = await self.build_folder_index(folder_path)
        await self.save_folder_index(folder_path, index)
        return index

    async def is_index_stale(self, folder_path: str) -> bool:
        """Check if folder index needs rebuilding."""
        index_path = f"{folder_path.rstrip('/')}/_index.json"
        
        if not await self.storage.exists(index_path):
            return True
        
        # For simplicity in MVP, consider index stale if older than 1 hour
        # In production, you'd compare with actual file mtimes
        try:
            index_data = await self.storage.read_text(index_path)
            index = FolderIndex.parse_raw(index_data)
            
            # Check if index is older than 1 hour
            age = datetime.utcnow() - index.generatedAt
            return age.total_seconds() > 3600
            
        except Exception:
            return True


class RollupBuilder:
    """Builds search rollup manifests."""

    def __init__(self, storage: StorageBackend):
        """Initialize rollup builder."""
        self.storage = storage

    async def build_rollup_manifest(self, root_path: str = "") -> RollupManifest:
        """Build _rollup.json for search across all folders."""
        items = []
        
        # Recursively collect all items with metadata
        await self._collect_items_recursive(root_path, items)
        
        return RollupManifest(
            generatedAt=datetime.utcnow(),
            items=items
        )

    async def _collect_items_recursive(self, folder_path: str, items: List[RollupItem]) -> None:
        """Recursively collect items from all folders."""
        try:
            dirs, folder_items = await self.storage.list_directory(folder_path)
            
            # Process items in current folder
            for item in folder_items:
                # Load sidecar if available
                sidecar_path = f"{item.path}.json"
                tags = []
                notes = ""
                
                if await self.storage.exists(sidecar_path):
                    try:
                        sidecar_data = await self.storage.read_text(sidecar_path)
                        sidecar = Sidecar.parse_raw(sidecar_data)
                        tags = sidecar.tags
                        notes = sidecar.notes
                    except Exception:
                        pass
                
                items.append(RollupItem(
                    path=item.path,
                    name=item.name,
                    tags=tags,
                    notes=notes
                ))
            
            # Recurse into subdirectories
            for dir_entry in dirs:
                subdir_path = f"{folder_path.rstrip('/')}/{dir_entry.name}"
                await self._collect_items_recursive(subdir_path, items)
                
        except Exception as e:
            print(f"Error collecting items from {folder_path}: {e}")

    async def save_rollup_manifest(self, root_path: str, manifest: RollupManifest) -> None:
        """Save rollup manifest to _rollup.json."""
        rollup_path = f"{root_path.rstrip('/')}/_rollup.json"
        
        data = orjson.dumps(
            manifest.dict(by_alias=True),
            option=orjson.OPT_UTC_Z | orjson.OPT_INDENT_2
        )
        
        await self.storage.write_bytes(rollup_path, data)

    async def build_and_save_rollup(self, root_path: str = "") -> RollupManifest:
        """Build and save rollup manifest."""
        manifest = await self.build_rollup_manifest(root_path)
        await self.save_rollup_manifest(root_path, manifest)
        return manifest
