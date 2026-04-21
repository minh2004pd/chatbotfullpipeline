"""Unit tests cho app.utils.file_utils — File processing utilities."""

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.utils.file_utils import (
    chunk_text,
    ensure_upload_dir,
    extract_pdf_text,
    image_to_base64,
    save_upload_file,
    validate_pdf,
)

# ── validate_pdf ──────────────────────────────────────────────────────────────


class TestValidatePdf:
    def test_valid_pdf(self):
        assert validate_pdf(b"%PDF-1.4 content") is True

    def test_valid_pdf_exact_header(self):
        assert validate_pdf(b"%PDF") is True

    def test_invalid_pdf_empty(self):
        assert validate_pdf(b"") is False

    def test_invalid_pdf_text_file(self):
        assert validate_pdf(b"This is a text file") is False

    def test_invalid_pdf_png(self):
        assert validate_pdf(b"\x89PNG\r\n\x1a\n") is False

    def test_invalid_pdf_html(self):
        assert validate_pdf(b"<!DOCTYPE html>") is False

    def test_invalid_pdf_short(self):
        assert validate_pdf(b"%P") is False

    def test_valid_pdf_case_sensitive(self):
        """PDF header phải chính xác case-sensitive."""
        assert validate_pdf(b"%pdf") is False
        assert validate_pdf(b"Pdf-") is False


# ── chunk_text ────────────────────────────────────────────────────────────────


class TestChunkText:
    def test_chunk_text_short(self):
        text = "Short text"
        chunks = chunk_text(text, chunk_size=100)
        assert len(chunks) == 1
        assert chunks[0] == "Short text"

    def test_chunk_text_longer_than_chunk_size(self):
        text = "A" * 500
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=0)
        assert len(chunks) >= 5

    def test_chunk_text_with_paragraphs(self):
        text = "Para 1\n\nPara 2\n\nPara 3"
        chunks = chunk_text(text, chunk_size=20, chunk_overlap=0)
        assert len(chunks) >= 1

    def test_chunk_text_respects_overlap(self):
        text = "A" * 200
        chunks = chunk_text(text, chunk_size=100, chunk_overlap=50)
        # With overlap, chunks should share content
        assert len(chunks) >= 2

    def test_chunk_text_empty(self):
        chunks = chunk_text("", chunk_size=100)
        # Empty text may return empty list or list with empty string
        assert isinstance(chunks, list)

    def test_chunk_text_returns_strings(self):
        text = "Hello World" * 10
        chunks = chunk_text(text, chunk_size=50)
        for chunk in chunks:
            assert isinstance(chunk, str)


# ── ensure_upload_dir ─────────────────────────────────────────────────────────


class TestEnsureUploadDir:
    def test_ensure_upload_dir_creates_directory(self, tmp_path):
        new_dir = str(tmp_path / "new" / "nested" / "dir")
        result = ensure_upload_dir(new_dir)
        assert result.exists()
        assert result.is_dir()
        assert str(result) == new_dir

    def test_ensure_upload_dir_existing(self, tmp_path):
        existing_dir = str(tmp_path / "existing")
        existing_dir_path = Path(existing_dir)
        existing_dir_path.mkdir()
        result = ensure_upload_dir(existing_dir)
        assert result.exists()

    def test_ensure_upload_dir_returns_path(self, tmp_path):
        result = ensure_upload_dir(str(tmp_path / "test"))
        assert isinstance(result, Path)


# ── save_upload_file ──────────────────────────────────────────────────────────


class TestSaveUploadFile:
    def test_save_upload_file_returns_tuple(self, tmp_path):
        content = b"file content"
        doc_id, file_path = save_upload_file(content, "test.pdf", str(tmp_path))
        assert isinstance(doc_id, str)
        assert isinstance(file_path, Path)

    def test_save_upload_file_creates_file(self, tmp_path):
        content = b"file content"
        doc_id, file_path = save_upload_file(content, "test.pdf", str(tmp_path))
        assert file_path.exists()
        assert file_path.read_bytes() == content

    def test_save_upload_file_unique_id(self, tmp_path):
        """Mỗi lần save tạo document_id khác nhau."""
        id1, _ = save_upload_file(b"content", "test.pdf", str(tmp_path))
        id2, _ = save_upload_file(b"content", "test.pdf", str(tmp_path))
        assert id1 != id2

    def test_save_upload_file_valid_uuid(self, tmp_path):
        import uuid

        doc_id, _ = save_upload_file(b"content", "test.pdf", str(tmp_path))
        # Should be a valid UUID
        uuid.UUID(doc_id)  # Should not raise

    def test_save_upload_file_preserves_extension(self, tmp_path):
        _, file_path = save_upload_file(b"content", "document.pdf", str(tmp_path))
        assert file_path.name.endswith("_document.pdf")

    def test_save_upload_file_path_traversal_prevention(self, tmp_path):
        """Filename với path traversal phải được sanitize."""
        content = b"content"
        doc_id, file_path = save_upload_file(content, "../../../etc/passwd", str(tmp_path))
        # Should only contain the filename, not the traversal path
        assert "/etc/" not in str(file_path)
        assert file_path.name.endswith("passwd")

    def test_save_upload_file_nested_filename(self, tmp_path):
        """Filename với slash phải được lấy tên file cuối."""
        _, file_path = save_upload_file(b"content", "folder/subfolder/file.pdf", str(tmp_path))
        assert file_path.name.endswith("file.pdf")

    def test_save_upload_file_empty_content(self, tmp_path):
        doc_id, file_path = save_upload_file(b"", "empty.pdf", str(tmp_path))
        assert file_path.exists()
        assert file_path.read_bytes() == b""


# ── extract_pdf_text ──────────────────────────────────────────────────────────


class TestExtractPdfText:
    @patch("app.utils.file_utils.PdfReader")
    def test_extract_pdf_text_single_page(self, mock_reader_class):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Hello World"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader

        result = extract_pdf_text(b"%PDF-1.4 fake pdf")
        assert result == "Hello World"

    @patch("app.utils.file_utils.PdfReader")
    def test_extract_pdf_text_multiple_pages(self, mock_reader_class):
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Page 1"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = "Page 2"
        mock_page3 = MagicMock()
        mock_page3.extract_text.return_value = "Page 3"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page1, mock_page2, mock_page3]
        mock_reader_class.return_value = mock_reader

        result = extract_pdf_text(b"%PDF-1.4 fake pdf")
        assert "Page 1" in result
        assert "Page 2" in result
        assert "Page 3" in result
        assert "\n\n" in result

    @patch("app.utils.file_utils.PdfReader")
    def test_extract_pdf_text_skips_empty_pages(self, mock_reader_class):
        mock_page1 = MagicMock()
        mock_page1.extract_text.return_value = "Content"
        mock_page2 = MagicMock()
        mock_page2.extract_text.return_value = ""  # Empty page
        mock_page3 = MagicMock()
        mock_page3.extract_text.return_value = "More content"

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page1, mock_page2, mock_page3]
        mock_reader_class.return_value = mock_reader

        result = extract_pdf_text(b"%PDF-1.4")
        assert "Content" in result
        assert "More content" in result
        # Empty page should not create double newline
        assert "\n\n\n" not in result

    @patch("app.utils.file_utils.PdfReader")
    def test_extract_pdf_text_whitespace_only_page(self, mock_reader_class):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "   \n  \t  "

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader

        result = extract_pdf_text(b"%PDF-1.4")
        assert result == ""

    @patch("app.utils.file_utils.PdfReader")
    def test_extract_pdf_text_empty_pdf(self, mock_reader_class):
        mock_reader = MagicMock()
        mock_reader.pages = []
        mock_reader_class.return_value = mock_reader

        result = extract_pdf_text(b"%PDF-1.4")
        assert result == ""

    @patch("app.utils.file_utils.PdfReader")
    def test_extract_pdf_text_strips_whitespace(self, mock_reader_class):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "  Hello  \n  World  "

        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]
        mock_reader_class.return_value = mock_reader

        result = extract_pdf_text(b"%PDF-1.4")
        # text.strip() được gọi
        assert result.startswith("Hello")
        assert result.endswith("World")


# ── image_to_base64 ───────────────────────────────────────────────────────────


class TestImageToBase64:
    def test_image_to_base64_encodes(self):
        image_bytes = b"\x89PNG\r\n\x1a\nfake image data"
        result = image_to_base64(image_bytes)
        assert isinstance(result, str)
        # Should be valid base64
        decoded = base64.b64decode(result)
        assert decoded == image_bytes

    def test_image_to_base64_empty(self):
        result = image_to_base64(b"")
        assert result == ""

    def test_image_to_base64_returns_string(self):
        result = image_to_base64(b"test")
        assert isinstance(result, str)

    def test_image_to_base64_no_newlines(self):
        """Base64 result nên là single line (không có newline)."""
        large_image = b"x" * 10000
        result = image_to_base64(large_image)
        assert "\n" not in result
        assert "\r" not in result

    def test_image_to_base64_decodable(self):
        original = bytes(range(256))  # All byte values
        encoded = image_to_base64(original)
        decoded = base64.b64decode(encoded)
        assert decoded == original
