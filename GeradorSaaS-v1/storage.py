from __future__ import annotations

import io
import os
import shutil
from pathlib import Path

from flask import current_app


def poster_key_for_result(result_key: str | None) -> str | None:
    """Deriva a chave da miniatura JPEG do MP4 final sem exigir nova coluna no banco."""
    if not result_key:
        return None
    base, _sep, _ext = result_key.rpartition(".")
    return f"{base or result_key}.jpg"


class Storage:
    """Storage local em desenvolvimento e S3/R2 em produção.

    Se S3_BUCKET estiver definido, usa API S3. Caso contrário grava em STORAGE_DIR.
    """

    def __init__(self):
        self.bucket = os.getenv("S3_BUCKET", "").strip()
        self.endpoint = os.getenv("S3_ENDPOINT", "").strip() or None
        self.region = os.getenv("S3_REGION", "auto").strip() or "auto"
        self.access_key = os.getenv("S3_ACCESS_KEY", "").strip()
        self.secret_key = os.getenv("S3_SECRET_KEY", "").strip()
        self._client = None

    @property
    def remote(self):
        return bool(self.bucket)

    def _s3(self):
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                region_name=self.region,
                aws_access_key_id=self.access_key or None,
                aws_secret_access_key=self.secret_key or None,
            )
        return self._client

    def _local_path(self, key: str) -> Path:
        root = Path(current_app.config["STORAGE_DIR"]).resolve()
        path = (root / key).resolve()
        if root not in path.parents and path != root:
            raise ValueError("Chave de storage inválida.")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def put_file(self, key: str, path: str, content_type: str | None = None):
        if self.remote:
            extra = {"ContentType": content_type} if content_type else {}
            self._s3().upload_file(path, self.bucket, key, ExtraArgs=extra or None)
        else:
            shutil.copy2(path, self._local_path(key))

    def put_bytes(self, key: str, data: bytes, content_type: str | None = None):
        if self.remote:
            kwargs = {"Bucket": self.bucket, "Key": key, "Body": data}
            if content_type:
                kwargs["ContentType"] = content_type
            self._s3().put_object(**kwargs)
        else:
            self._local_path(key).write_bytes(data)

    def put_stream(self, key: str, fileobj, content_type: str | None = None):
        if self.remote:
            extra = {"ContentType": content_type} if content_type else None
            self._s3().upload_fileobj(fileobj, self.bucket, key, ExtraArgs=extra)
        else:
            out = self._local_path(key)
            with out.open("wb") as f:
                shutil.copyfileobj(fileobj, f)

    def download_to(self, key: str, path: str):
        if self.remote:
            self._s3().download_file(self.bucket, key, path)
        else:
            shutil.copy2(self._local_path(key), path)

    def read_bytes(self, key: str) -> bytes:
        if self.remote:
            obj = self._s3().get_object(Bucket=self.bucket, Key=key)
            return obj["Body"].read()
        return self._local_path(key).read_bytes()

    def exists(self, key: str) -> bool:
        if not key:
            return False
        if self.remote:
            try:
                self._s3().head_object(Bucket=self.bucket, Key=key)
                return True
            except Exception:
                return False
        return self._local_path(key).exists()

    def presigned_get(self, key: str, download_name: str | None = None, expires: int = 600) -> str | None:
        if not self.remote:
            return None
        params = {
            "Bucket": self.bucket,
            "Key": key,
            "ResponseCacheControl": "no-store, no-cache, must-revalidate, max-age=0",
        }
        if download_name:
            safe = download_name.replace('"', "").replace("\r", "").replace("\n", "")
            params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
        return self._s3().generate_presigned_url(
            "get_object", Params=params, ExpiresIn=max(60, min(int(expires), 3600))
        )

    def delete(self, key: str | None):
        if not key:
            return
        if self.remote:
            try:
                self._s3().delete_object(Bucket=self.bucket, Key=key)
            except Exception:
                pass
        else:
            try:
                self._local_path(key).unlink()
            except OSError:
                pass


storage = Storage()
