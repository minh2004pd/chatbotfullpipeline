from functools import lru_cache

import boto3
import structlog
from botocore.exceptions import ClientError
from mem0 import Memory
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import Distance, VectorParams

from app.core.config import get_settings
from app.core.llm_config import get_llm_config

logger = structlog.get_logger(__name__)


def _embedding_dim() -> int:
    """Đọc dimension từ llm_config — single source of truth."""
    return get_llm_config().embedding.dimension


def get_mem0_config() -> dict:
    settings = get_settings()
    return {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "url": settings.qdrant_url,
                "collection_name": settings.qdrant_collection_mem0,
                "embedding_model_dims": _embedding_dim(),
            },
        },
        "llm": {
            "provider": "gemini",
            "config": {
                "model": settings.gemini_model,
                "api_key": settings.gemini_api_key,
            },
        },
        "embedder": {
            "provider": "gemini",
            "config": {
                "model": settings.gemini_embedding_model,
                "api_key": settings.gemini_api_key,
                "embedding_dims": _embedding_dim(),
            },
        },
    }


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )
    logger.info("qdrant_client_created", url=settings.qdrant_url)
    return client


@lru_cache
def get_async_qdrant_client() -> AsyncQdrantClient:
    settings = get_settings()
    return AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key or None,
    )


@lru_cache
def get_mem0_client() -> Memory:
    config = get_mem0_config()
    memory = Memory.from_config(config)
    logger.info("mem0_client_created")
    return memory


async def ensure_collections() -> None:
    """Create Qdrant collections if they don't exist, or recreate if dimension mismatch."""
    settings = get_settings()
    client = get_qdrant_client()
    target_dim = _embedding_dim()

    existing_collections = {c.name: c for c in client.get_collections().collections}

    for collection_name in [
        settings.qdrant_collection_rag,
        settings.qdrant_collection_mem0,
    ]:
        recreate = False
        if collection_name in existing_collections:
            # Check dimension
            info = client.get_collection(collection_name)
            # Assuming single vector config (standard for this app)
            current_dim = info.config.params.vectors.size
            if current_dim != target_dim:
                logger.warning(
                    "collection_dimension_mismatch",
                    name=collection_name,
                    expected=target_dim,
                    got=current_dim,
                )
                client.delete_collection(collection_name)
                recreate = True
        else:
            recreate = True

        if recreate:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=target_dim, distance=Distance.COSINE),
            )
            logger.info("collection_ready", name=collection_name, dimension=target_dim)


@lru_cache
def get_dynamodb_resource():
    """Trả về boto3 DynamoDB resource (singleton per process)."""
    settings = get_settings()
    kwargs: dict = {"region_name": settings.dynamodb_region}
    if settings.dynamodb_endpoint_url:
        kwargs["endpoint_url"] = settings.dynamodb_endpoint_url
    if settings.aws_access_key_id:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    elif settings.dynamodb_endpoint_url:
        # DynamoDB Local không cần credentials thật, nhưng boto3 vẫn cần *gì đó*
        kwargs["aws_access_key_id"] = "local"
        kwargs["aws_secret_access_key"] = "local"
    resource = boto3.resource("dynamodb", **kwargs)
    logger.info("dynamodb_resource_created", region=settings.dynamodb_region)
    return resource


async def ensure_dynamo_table() -> None:
    """Tạo DynamoDB table nếu chưa tồn tại (dùng cho local dev; prod dùng IaC)."""
    settings = get_settings()
    resource = get_dynamodb_resource()
    table_name = settings.dynamodb_table_name

    try:
        table = resource.Table(table_name)
        table.load()  # raises ResourceNotFoundException nếu chưa có
        logger.info("dynamo_table_ready", table=table_name)
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
        # Tạo table mới
        resource.create_table(
            TableName=table_name,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "session_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "session_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # Chờ table sẵn sàng (chỉ cần thiết với DynamoDB Local sync)
        resource.Table(table_name).wait_until_exists()
        logger.info("dynamo_table_created", table=table_name)
