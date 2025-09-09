from __future__ import annotations
import os
import boto3
from botocore.client import Config
from .base import Storage

class S3Storage(Storage):
    def __init__(self, bucket: str, prefix: str = "", region: str | None = None, endpoint: str | None = None):
        self.bucket = bucket
        self.prefix = prefix.strip('/')
        session = boto3.session.Session(region_name=region)
        self.s3 = session.client('s3', endpoint_url=endpoint, config=Config(s3={'addressing_style':'virtual'}))

    def _key(self, path: str) -> str:
        path = path.lstrip('/')
        return f"{self.prefix}/{path}".strip('/') if self.prefix else path

    def list_dir(self, path: str):
        key = self._key(path)
        if key and not key.endswith('/'):
            key += '/'
        paginator = self.s3.get_paginator('list_objects_v2')
        files, dirs = [], []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=key, Delimiter='/'):
            for c in page.get('CommonPrefixes', []):
                name = c['Prefix'][len(key):].strip('/')
                if name:
                    dirs.append(name)
            for obj in page.get('Contents', []):
                name = obj['Key'][len(key):]
                if name and '/' not in name:
                    files.append(name)
        return files, dirs

    def read_bytes(self, path: str) -> bytes:
        key = self._key(path)
        r = self.s3.get_object(Bucket=self.bucket, Key=key)
        return r['Body'].read()

    def write_bytes(self, path: str, data: bytes) -> None:
        key = self._key(path)
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data)

    def exists(self, path: str) -> bool:
        key = self._key(path)
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except self.s3.exceptions.NoSuchKey:
            return False
        except Exception:
            return False

    def size(self, path: str) -> int:
        key = self._key(path)
        r = self.s3.head_object(Bucket=self.bucket, Key=key)
        return r['ContentLength']

    def join(self, *parts: str) -> str:
        return "/".join([p.strip("/") for p in parts if p])

    def etag(self, path: str) -> str | None:
        key = self._key(path)
        try:
            r = self.s3.head_object(Bucket=self.bucket, Key=key)
            return r.get('ETag', '').strip('"')
        except Exception:
            return None
