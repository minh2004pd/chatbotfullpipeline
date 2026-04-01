"""Utilities cho xử lý file (PDF, images, v.v.)."""
import io
import uuid
import base64
from pathlib import Path

import structlog
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter

logger = structlog.get_logger(__name__)


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Trích xuất text từ PDF bytes."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text.strip())
    full_text = "\n\n".join(pages)
    logger.info("pdf_text_extracted", pages=len(reader.pages), chars=len(full_text))
    return full_text


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[str]:
    """Chia text thành các chunks nhỏ."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = splitter.split_text(text)
    logger.info("text_chunked", chunks=len(chunks), chunk_size=chunk_size)
    return chunks


def ensure_upload_dir(upload_dir: str) -> Path:
    path = Path(upload_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload_file(file_bytes: bytes, filename: str, upload_dir: str) -> tuple[str, Path]:
    """Lưu file upload và trả về (document_id, file_path)."""
    document_id = str(uuid.uuid4())
    dir_path = ensure_upload_dir(upload_dir)
    safe_name = Path(filename).name  # prevent path traversal
    file_path = dir_path / f"{document_id}_{safe_name}"
    file_path.write_bytes(file_bytes)
    logger.info("file_saved", document_id=document_id, path=str(file_path))
    return document_id, file_path


def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("utf-8")


def validate_pdf(file_bytes: bytes) -> bool:
    """Kiểm tra file có phải PDF hợp lệ không."""
    return file_bytes[:4] == b"%PDF"
