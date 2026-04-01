"""Amazon S3 (and S3-compatible) storage backend."""

from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)


class S3Storage:
    """Lưu file lên Amazon S3 (hoặc MinIO / custom endpoint)."""

    def __init__(
        self,
        bucket: str,
        prefix: str = "uploads",
        region: str = "ap-southeast-1",
        access_key_id: str = "",
        secret_access_key: str = "",
        session_token: str = "",
        endpoint_url: str = "",
        presigned_url_expiry: int = 3600,
    ) -> None:
        import boto3  # lazy import — chỉ load khi dùng S3

        self._bucket = bucket
        self._prefix = prefix.rstrip("/")
        self._expiry = presigned_url_expiry

        session_kwargs: dict = {"region_name": region}
        if access_key_id and secret_access_key:
            session_kwargs["aws_access_key_id"] = access_key_id
            session_kwargs["aws_secret_access_key"] = secret_access_key
            # ASIA... keys (STS/SSO temporary credentials) bắt buộc phải có session_token
            if session_token:
                session_kwargs["aws_session_token"] = session_token

        client_kwargs: dict = {}
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url

        self._client = boto3.client("s3", **session_kwargs, **client_kwargs)

    def _build_key(self, user_id: str, document_id: str, filename: str) -> str:
        """Key format: ``{prefix}/{user_id}/{document_id}/{filename}``."""
        safe_name = Path(filename).name
        return f"{self._prefix}/{user_id}/{document_id}/{safe_name}"

    def save(self, file_bytes: bytes, user_id: str, document_id: str, filename: str) -> str:
        key = self._build_key(user_id, document_id, filename)
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=file_bytes,
            ContentType="application/pdf",
        )
        logger.info("storage_s3_saved", bucket=self._bucket, key=key, bytes=len(file_bytes))
        return key

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
        logger.info("storage_s3_deleted", bucket=self._bucket, key=key)

    def get_url(self, key: str) -> str:
        """Tạo presigned URL có thời hạn `presigned_url_expiry` giây."""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._expiry,
        )
