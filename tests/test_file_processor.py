"""Tests for actions/file_processor.py — Universal File Processor.

Tests cover TOOL_SCHEMA validity, all helper functions, and every
process function (_process_image, _process_pdf, _process_text_doc,
_process_data, _process_json, _process_code, _process_audio,
_process_video, _process_archive, _process_pptx) plus the main
file_processor() dispatch.

All external calls (AI, PIL, pdfplumber, pandas, pydub, ffmpeg,
python-docx, python-pptx, subprocess) are mocked.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from actions.file_processor import (
    TOOL_SCHEMA,
    _detect_type,
    _file_size_str,
    _process_archive,
    _process_audio,
    _process_code,
    _process_data,
    _process_image,
    _process_json,
    _process_pdf,
    _process_pptx,
    _process_text_doc,
    _process_video,
    file_processor,
)

# =========================================================================
# 1. TOOL_SCHEMA
# =========================================================================


class TestToolSchema:
    """TOOL_SCHEMA must match the expected contract."""

    def test_name(self):
        assert TOOL_SCHEMA["name"] == "file_processor"

    def test_description_is_string(self):
        assert isinstance(TOOL_SCHEMA["description"], str)
        assert len(TOOL_SCHEMA["description"]) > 10

    def test_parameters_type(self):
        assert TOOL_SCHEMA["parameters"]["type"] == "OBJECT"

    def test_parameters_properties(self):
        props = TOOL_SCHEMA["parameters"]["properties"]
        assert "action" in props
        assert "file_path" in props
        assert "query" in props
        assert "output_path" in props

    def test_required_fields(self):
        required = TOOL_SCHEMA["parameters"]["required"]
        assert "action" in required
        assert "file_path" in required
        assert len(required) == 2


# =========================================================================
# 2. _detect_type
# =========================================================================


class TestDetectType:
    """_detect_type maps file extensions to internal type strings."""

    @pytest.mark.parametrize(
        ("filename", "expected"),
        [
            ("photo.jpg", "image"),
            ("photo.jpeg", "image"),
            ("photo.png", "image"),
            ("photo.gif", "image"),
            ("photo.webp", "image"),
            ("photo.bmp", "image"),
            ("photo.tiff", "image"),
            ("photo.svg", "image"),
            ("photo.ico", "image"),
            ("video.mp4", "video"),
            ("video.avi", "video"),
            ("video.mov", "video"),
            ("video.mkv", "video"),
            ("video.wmv", "video"),
            ("video.flv", "video"),
            ("video.webm", "video"),
            ("video.m4v", "video"),
            ("video.3gp", "video"),
            ("audio.mp3", "audio"),
            ("audio.wav", "audio"),
            ("audio.ogg", "audio"),
            ("audio.m4a", "audio"),
            ("audio.aac", "audio"),
            ("audio.flac", "audio"),
            ("audio.wma", "audio"),
            ("audio.opus", "audio"),
            ("script.py", "code"),
            ("script.js", "code"),
            ("script.ts", "code"),
            ("script.jsx", "code"),
            ("script.tsx", "code"),
            ("page.html", "code"),
            ("style.css", "code"),
            ("main.java", "code"),
            ("main.c", "code"),
            ("main.cpp", "code"),
            ("main.cs", "code"),
            ("main.go", "code"),
            ("main.rs", "code"),
            ("main.rb", "code"),
            ("main.php", "code"),
            ("main.swift", "code"),
            ("main.kt", "code"),
            ("script.sh", "code"),
            ("script.bash", "code"),
            ("script.ps1", "code"),
            ("script.lua", "code"),
            ("script.r", "code"),
            ("script.m", "code"),
            ("query.sql", "code"),
            ("config.yaml", "code"),
            ("config.toml", "code"),
            ("archive.zip", "archive"),
            ("archive.rar", "archive"),
            ("archive.tar", "archive"),
            ("archive.gz", "archive"),
            ("archive.7z", "archive"),
            ("archive.bz2", "archive"),
            ("archive.xz", "archive"),
            ("doc.pdf", "pdf"),
            ("doc.docx", "docx"),
            ("doc.doc", "docx"),
            ("readme.txt", "text"),
            ("readme.md", "text"),
            ("readme.rst", "text"),
            ("readme.log", "text"),
            ("data.csv", "csv"),
            ("data.tsv", "csv"),
            ("data.xlsx", "excel"),
            ("data.xls", "excel"),
            ("data.ods", "excel"),
            ("data.json", "json"),
            ("config.xml", "xml"),
            ("slides.pptx", "pptx"),
            ("slides.ppt", "pptx"),
            ("unknown.xyz", "unknown"),
            ("no_extension", "unknown"),
            ("", "unknown"),
        ],
    )
    def test_detect(self, filename, expected):
        assert _detect_type(Path(filename)) == expected


# =========================================================================
# 3. _file_size_str
# =========================================================================


class TestFileSizeStr:
    """_file_size_str returns human-readable size strings."""

    def test_bytes(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("hello")
        result = _file_size_str(f)
        assert "B" in result
        # "hello" is 5 bytes
        assert result == "5 B" or "5 B" in result

    def test_kilobytes(self, tmp_path):
        f = tmp_path / "kb_file.txt"
        f.write_bytes(b"x" * 2048)  # 2 KB
        result = _file_size_str(f)
        assert "KB" in result

    def test_megabytes(self, tmp_path):
        f = tmp_path / "mb_file.bin"
        f.write_bytes(b"x" * (1024 * 1024 * 2))  # 2 MB
        result = _file_size_str(f)
        assert "MB" in result

    def test_zero_bytes(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = _file_size_str(f)
        assert "0 B" in result or "B" in result


# =========================================================================
# 4. Main file_processor() dispatch
# =========================================================================


class TestFileProcessorMain:
    """Main file_processor() entry point error handling."""

    def test_no_file_path(self):
        result = file_processor({"action": "describe"})
        assert "No file path provided" in result

    def test_empty_file_path(self):
        result = file_processor({"action": "describe", "file_path": ""})
        assert "No file path provided" in result

    def test_file_not_found(self):
        result = file_processor(
            {"action": "describe", "file_path": "/nonexistent/file.txt"}
        )
        assert "File not found" in result

    def test_path_is_directory(self, tmp_path):
        result = file_processor(
            {"action": "describe", "file_path": str(tmp_path)}
        )
        assert "Path is not a file" in result

    def test_unknown_type_ai_fallback(self, tmp_path):
        """Unknown file types route to _ai_text fallback."""
        f = tmp_path / "data.xyz"
        f.write_text("some content")
        with patch(
            "actions.file_processor.generate_text", return_value="AI handled it"
        ):
            result = file_processor({"action": "describe", "file_path": str(f)})
        assert "AI handled it" in result

    def test_unknown_type_read_failure(self, tmp_path):
        """Unknown file type read failure returns error."""
        f = tmp_path / "data.xyz"
        f.write_bytes(b"\xff\xfe\x00\x01")  # binary junk
        with patch(
            "actions.file_processor.generate_text",
            side_effect=Exception("read error"),
        ):
            result = file_processor({"action": "describe", "file_path": str(f)})
        assert "Could not process" in result or "read error" in str(result)


# =========================================================================
# 5. _process_image
# =========================================================================


class TestProcessImage:
    """_process_image handles describe, resize, convert, compress, info."""

    def _mock_pil(self):
        """Return a (mock_module, mock_image) tuple for PIL patching."""
        mock_pil = MagicMock()
        mock_img = MagicMock()
        mock_img.size = (800, 600)
        mock_img.format = "JPEG"
        mock_img.mode = "RGB"
        mock_pil.Image.open.return_value = mock_img
        mock_pil.Image.LANCZOS = 1
        return mock_pil, mock_img

    def _patch_pil(self):
        mock_pil, mock_img = self._mock_pil()
        return (
            patch.dict("sys.modules", {"PIL": mock_pil, "PIL.Image": mock_pil.Image}),
            mock_img,
        )

    # -- describe / AI actions --

    def test_describe(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor.generate_multimodal",
            return_value="A cat sitting on a chair.",
        ):
            result = _process_image(img, "describe", {})
        assert "A cat sitting on a chair." in result

    def test_describe_saves_result(self, tmp_path):
        """Long results (>500 chars) are saved to file when save=True."""
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        long_result = "word " * 150  # > 500 chars
        with pil_patch, patch(
            "actions.file_processor.generate_multimodal",
            return_value=long_result,
        ):
            result = _process_image(img, "describe", {"save": True})
        assert "saved to" in result.lower()
        # Check the saved file exists
        saved_files = list(tmp_path.glob("*result*"))
        assert len(saved_files) > 0

    def test_describe_no_save(self, tmp_path):
        """Short results are not saved even with save=True."""
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor.generate_multimodal",
            return_value="A cat.",
        ):
            result = _process_image(img, "describe", {"save": True})
        # Short result returned directly, no save file
        assert result == "A cat."

    def test_ocr_action(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor.generate_multimodal",
            return_value="Extracted text from image.",
        ):
            result = _process_image(img, "ocr", {})
        assert "Extracted text" in result

    def test_custom_instruction(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor.generate_multimodal",
            return_value="Custom analysis result.",
        ) as mock_ai:
            result = _process_image(img, "describe", {"instruction": "Find all faces"})
        assert "Custom analysis result." in result
        # Verify the custom instruction was passed
        call_args = mock_ai.call_args
        assert "Find all faces" in str(call_args)

    def test_ai_image_failure(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor.generate_multimodal",
            side_effect=Exception("API error"),
        ):
            result = _process_image(img, "describe", {})
        assert "AI image analysis failed" in result

    # -- resize --

    def test_resize_width_height(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        with pil_patch:
            result = _process_image(img, "resize", {"width": "400", "height": "300"})
        assert "Resized" in result
        assert "400x300" in result
        mock_img.resize.assert_called_once()

    def test_resize_scale(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        mock_img.size = (100, 50)
        with pil_patch:
            result = _process_image(img, "resize", {"scale": "0.5"})
        assert "Resized" in result
        # 100*0.5=50, 50*0.5=25
        assert "50x25" in result or "50" in result
        mock_img.resize.assert_called_once()

    def test_resize_only_width(self, tmp_path):
        """Width-only resize maintains aspect ratio."""
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        mock_img.size = (800, 600)
        with pil_patch:
            result = _process_image(img, "resize", {"width": "400"})
        assert "Resized" in result
        # 800→400, 600*400/800=300
        assert "400x300" in result
        mock_img.resize.assert_called_once()

    def test_resize_no_dimensions(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        with pil_patch:
            result = _process_image(img, "resize", {})
        assert "specify" in result.lower() or "width" in result.lower()

    def test_resize_failure(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        mock_img.resize.side_effect = Exception("bad resize")
        with pil_patch:
            result = _process_image(img, "resize", {"width": "100", "height": "100"})
        assert "Resize failed" in result

    # -- convert --

    def test_convert_to_jpeg(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        with pil_patch:
            result = _process_image(img, "convert", {"format": "jpg"})
        assert "Converted to JPG" in result or "Converted to JPEG" in result
        assert "converted" in result.lower()

    def test_convert_to_webp(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        with pil_patch:
            result = _process_image(img, "convert", {"format": "webp"})
        assert "WEBP" in result

    def test_convert_failure(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        mock_img.convert.side_effect = Exception("convert error")
        # The code does Image.open(path).convert("RGB") - we need img.convert to fail
        # Actually, img is the mock image, img.convert might not be called;
        # save might fail. Let's make save fail.
        pil_patch_context, _ = self._patch_pil()
        mock_img_alt = MagicMock()
        mock_img_alt.size = (800, 600)
        mock_img_alt.format = "PNG"
        mock_img_alt.mode = "RGB"
        mock_img_alt.convert.return_value = mock_img_alt
        mock_img_alt.save.side_effect = Exception("save error")
        mock_pil = MagicMock()
        mock_pil.Image.open.return_value = mock_img_alt
        mock_pil.Image.LANCZOS = 1
        with patch.dict(
            "sys.modules", {"PIL": mock_pil, "PIL.Image": mock_pil.Image}
        ):
            result = _process_image(img, "convert", {"format": "jpg"})
        assert "Convert failed" in result

    # -- compress --

    def test_compress(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor._file_size_str", return_value="10 KB"
        ):
            result = _process_image(img, "compress", {})
        assert "Compressed" in result

    def test_compress_custom_quality(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor._file_size_str", return_value="10 KB"
        ):
            result = _process_image(img, "compress", {"quality": "85"})
        assert "Compressed" in result

    # -- info --

    def test_info(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, mock_img = self._patch_pil()
        with pil_patch:
            result = _process_image(img, "info", {})
        assert "Image info" in result
        assert "JPEG" in result or "PNG" in result
        assert "800x600" in result or "RGB" in result

    def test_info_failure(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        mock_pil = MagicMock()
        mock_pil.Image.open.side_effect = Exception("corrupt image")
        with patch.dict(
            "sys.modules", {"PIL": mock_pil, "PIL.Image": mock_pil.Image}
        ):
            result = _process_image(img, "info", {})
        assert "Info failed" in result

    # -- no PIL --

    def test_no_pillow(self, tmp_path):
        """Without PIL, all image actions return an error message."""
        pil_available = "PIL" in sys.modules or importlib.util.find_spec("PIL") is not None
        if pil_available:
            pytest.skip("PIL is installed in this test environment")
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        result = _process_image(img, "describe", {})
        assert "Pillow is not installed" in result

    # -- fallback for unknown actions --

    def test_unknown_action_fallback(self, tmp_path):
        """Unknown action falls through to describe."""
        img = tmp_path / "test.png"
        img.write_bytes(b"fake")
        pil_patch, _ = self._patch_pil()
        with pil_patch, patch(
            "actions.file_processor.generate_multimodal",
            return_value="fallback result",
        ):
            result = _process_image(img, "unknown_action", {})
        assert "fallback result" in result


# =========================================================================
# 6. _process_pdf
# =========================================================================


class TestProcessPdf:
    """_process_pdf handles summarize, extract_text, info, to_word."""

    def _make_pdf(self, tmp_path, name="test.pdf"):
        p = tmp_path / name
        p.write_bytes(b"%PDF-1.4 fake pdf content")
        return p

    def test_summarize(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        # Mock pdfplumber
        mock_pdfplumber = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is page content."
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdfplumber.open.return_value.__enter__.return_value = mock_pdf
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}), patch(
            "actions.file_processor.generate_text",
            return_value="Summary of PDF.",
        ):
            result = _process_pdf(pdf, "summarize", {})
        assert "Summary of PDF." in result

    def test_summarize_saves_long_result(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        mock_pdfplumber = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "content."
        mock_pdfplumber.open.return_value.__enter__.return_value = MagicMock(
            pages=[mock_page]
        )
        long_result = "word " * 350  # > 600 chars
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}), patch(
            "actions.file_processor.generate_text",
            return_value=long_result,
        ):
            result = _process_pdf(pdf, "summarize", {"save": True})
        assert "saved" in result.lower()

    def test_extract_text(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        mock_pdfplumber = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Extracted page text."
        mock_pdfplumber.open.return_value.__enter__.return_value = MagicMock(
            pages=[mock_page]
        )
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}):
            result = _process_pdf(pdf, "extract_text", {})
        assert "Text extracted" in result
        assert "saved" in result.lower()

    def test_info(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        mock_pdfplumber = MagicMock()
        mock_pdfplumber.open.return_value.__enter__.return_value = MagicMock(
            pages=[MagicMock(), MagicMock()]
        )  # 2 pages
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}):
            result = _process_pdf(pdf, "info", {})
        assert "2 pages" in result or "1 page" in result
        assert "size" in result.lower()

    def test_info_without_pdfplumber(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        result = _process_pdf(pdf, "info", {})
        assert "size" in result.lower()

    def test_no_text_extracted(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        mock_pdfplumber = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_pdfplumber.open.return_value.__enter__.return_value = MagicMock(
            pages=[mock_page]
        )
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}):
            result = _process_pdf(pdf, "summarize", {})
        assert "Could not extract text" in result

    def test_to_word(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        mock_pdfplumber = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Some text content."
        mock_pdfplumber.open.return_value.__enter__.return_value = MagicMock(
            pages=[mock_page]
        )
        mock_doc_instance = MagicMock()
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber}), patch(
            "docx.Document", return_value=mock_doc_instance
        ):
            result = _process_pdf(pdf, "to_word", {})
        assert "Converted to Word" in result
        mock_doc_instance.save.assert_called_once()

    def test_to_word_no_docx(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        mock_pdfplumber = MagicMock()
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Some text."
        mock_pdfplumber.open.return_value.__enter__.return_value = MagicMock(
            pages=[mock_page]
        )
        # Inject a fake docx module without Document to trigger ImportError
        fake_docx = MagicMock(spec=[])  # empty spec — no Document attribute
        with patch.dict("sys.modules", {"pdfplumber": mock_pdfplumber, "docx": fake_docx}):
            result = _process_pdf(pdf, "to_word", {})
            assert "python-docx" in result or "not installed" in result

    def test_unknown_action(self, tmp_path):
        pdf = self._make_pdf(tmp_path)
        result = _process_pdf(pdf, "unknown_action", {})
        assert "Unknown PDF action" in result


# =========================================================================
# 7. _process_text_doc
# =========================================================================


class TestProcessTextDoc:
    """_process_text_doc handles word_count, summarize, extract_text."""

    def test_word_count(self, tmp_path):
        f = tmp_path / "notes.txt"
        f.write_text("hello world\nfoo bar baz\nend")
        result = _process_text_doc(f, "text", "word_count", {})
        assert "6 words" in result or "Word count" in result
        assert "characters" in result
        assert "lines" in result

    def test_summarize(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("Some markdown content for testing.")
        with patch(
            "actions.file_processor.generate_text",
            return_value="Summary of the document.",
        ):
            result = _process_text_doc(f, "text", "summarize", {})
        assert "Summary of the document." in result

    def test_summarize_saves_long(self, tmp_path):
        f = tmp_path / "article.md"
        f.write_text("content")
        long_result = "word " * 350  # > 600 chars
        with patch(
            "actions.file_processor.generate_text",
            return_value=long_result,
        ):
            result = _process_text_doc(f, "text", "summarize", {"save": True})
        assert "saved" in result.lower()

    def test_extract_text_non_txt(self, tmp_path):
        """extract_text on non-txt saves to file."""
        f = tmp_path / "article.md"
        f.write_text("markdown content")
        result = _process_text_doc(f, "text", "extract_text", {})
        assert "Text extracted" in result
        assert "saved" in result.lower()

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        result = _process_text_doc(f, "text", "word_count", {})
        assert "appears to be empty" in result.lower()

    def test_analyze_action(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Some content.")
        with patch(
            "actions.file_processor.generate_text",
            return_value="Analysis result.",
        ):
            result = _process_text_doc(f, "text", "analyze", {})
        assert "Analysis result." in result

    def test_custom_action(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Content.")
        with patch(
            "actions.file_processor.generate_text",
            return_value="Custom result.",
        ):
            result = _process_text_doc(f, "text", "translate_hint", {})
        assert "Custom result." in result

    def test_ai_failure(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Content.")
        with patch(
            "actions.file_processor.generate_text",
            side_effect=Exception("AI error"),
        ):
            result = _process_text_doc(f, "text", "summarize", {})
        assert "AI processing failed" in result

    def test_docx_type(self, tmp_path):
        """DOCX files use python-docx to read content."""
        f = tmp_path / "doc.docx"
        f.write_bytes(b"fake docx")
        mock_doc_instance = MagicMock()
        mock_p1 = MagicMock()
        mock_p1.text = "Paragraph 1"
        mock_p2 = MagicMock()
        mock_p2.text = "Paragraph 2"
        mock_doc_instance.paragraphs = [mock_p1, mock_p2]
        with patch("docx.Document", return_value=mock_doc_instance), patch(
            "actions.file_processor.generate_text",
            return_value="Summary of docx.",
        ):
            result = _process_text_doc(f, "docx", "summarize", {})
        assert "Summary of docx." in result


# =========================================================================
# 8. _process_data
# =========================================================================


class TestProcessData:
    """_process_data handles CSV/Excel info, stats, analyze, convert, filter, sort."""

    @staticmethod
    def _make_data_df_mock(rows=100, columns=None):
        """Create a DataFrame mock with proper columns mock."""
        if columns is None:
            columns = ["name", "age", "city"]
        df_mock = MagicMock()
        df_mock.__len__.return_value = rows

        # columns must support .tolist() and 'in' operator
        cols_mock = MagicMock()
        cols_mock.tolist.return_value = columns
        cols_mock.__contains__.side_effect = lambda x: x in columns
        cols_mock.__iter__.return_value = iter(columns)
        cols_mock.__len__.return_value = len(columns)
        df_mock.columns = cols_mock

        return df_mock

    def test_info(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=100, columns=["name", "age", "city"])
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}):
            result = _process_data(f, "csv", "info", {})
        assert "Rows: 100" in result
        assert "Columns:" in result
        assert "name" in result

    def test_stats(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=100, columns=["name", "age"])
        df_mock.describe.return_value.to_string.return_value = "count 100\nmean 35.0"
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}):
            result = _process_data(f, "csv", "stats", {})
        assert "Statistics" in result
        assert "count" in result or "mean" in result

    def test_analyze(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=100, columns=["name", "age"])
        df_mock.head.return_value.to_string.return_value = "name,age\nAlice,30"
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}), patch(
            "actions.file_processor.generate_text",
            return_value="AI analysis of dataset.",
        ):
            result = _process_data(f, "csv", "analyze", {})
        assert "AI analysis of dataset." in result

    def test_convert_to_json(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=2, columns=["name", "age"])
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}):
            result = _process_data(f, "csv", "convert", {"format": "json"})
        assert "Converted to JSON" in result

    def test_filter_by_column(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=100, columns=["name", "age"])
        # Make df[col] == value return a filtered df
        filtered_mock = MagicMock()
        filtered_mock.__len__.return_value = 10
        mock_series = MagicMock()
        mock_series.__eq__.return_value = filtered_mock
        df_mock.__getitem__.return_value = mock_series
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}):
            result = _process_data(
                f, "csv", "filter", {"column": "name", "value": "Alice"}
            )
        assert "Filtered" in result

    def test_filter_column_not_found(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=2, columns=["name", "age"])
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}):
            result = _process_data(
                f, "csv", "filter", {"column": "invalid_col", "value": "x"}
            )
        assert "Column" in result and "not found" in result

    def test_sort(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=2, columns=["name", "age"])
        df_mock.sort_values.return_value = df_mock
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}):
            result = _process_data(f, "csv", "sort", {"column": "name"})
        assert "Sorted" in result

    def test_no_pandas(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        result = _process_data(f, "csv", "info", {})
        assert "pandas not installed" in result

    def test_unknown_action_fallback(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30")
        pandas_mock = MagicMock()
        df_mock = self._make_data_df_mock(rows=2, columns=["name", "age"])
        df_mock.head.return_value.to_string.return_value = "name,age\nAlice,30"
        pandas_mock.read_csv.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}), patch(
            "actions.file_processor.generate_text",
            return_value="Fallback AI result.",
        ):
            result = _process_data(f, "csv", "custom_action", {})
        assert "Fallback AI result." in result


# =========================================================================
# 9. _process_json
# =========================================================================


class TestProcessJson:
    """_process_json handles validate, format, analyze, to_csv."""

    def test_validate(self, tmp_path):
        f = tmp_path / "data.json"
        json.dump({"key": "value"}, f.open("w"))
        result = _process_json(f, "validate", {})
        assert "Valid JSON" in result
        assert "dict" in result

    def test_format(self, tmp_path):
        f = tmp_path / "messy.json"
        f.write_text('{"a":1,"b":2}')
        result = _process_json(f, "format", {})
        assert "Formatted JSON saved" in result
        saved = json.loads((tmp_path / "messy_formatted.json").read_text())
        assert saved == {"a": 1, "b": 2}

    def test_analyze(self, tmp_path):
        f = tmp_path / "data.json"
        json.dump({"items": [1, 2, 3]}, f.open("w"))
        with patch(
            "actions.file_processor.generate_text",
            return_value="JSON analysis result.",
        ):
            result = _process_json(f, "analyze", {})
        assert "JSON analysis result." in result

    def test_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("{invalid json}")
        result = _process_json(f, "validate", {})
        assert "Invalid JSON" in result

    def test_to_csv(self, tmp_path):
        f = tmp_path / "data.json"
        json.dump([{"a": 1, "b": 2}], f.open("w"))
        pandas_mock = MagicMock()
        df_mock = MagicMock()
        pandas_mock.DataFrame.return_value = df_mock
        with patch.dict("sys.modules", {"pandas": pandas_mock}):
            result = _process_json(f, "to_csv", {})
        assert "Converted to CSV" in result

    def test_to_csv_not_array(self, tmp_path):
        f = tmp_path / "data.json"
        json.dump({"key": "value"}, f.open("w"))
        with patch.dict("sys.modules", {"pandas": MagicMock()}):
            result = _process_json(f, "to_csv", {})
        assert "must be an array" in result

    def test_to_csv_no_pandas(self, tmp_path):
        f = tmp_path / "data.json"
        json.dump([{"a": 1}], f.open("w"))
        result = _process_json(f, "to_csv", {})
        assert "not installed" in result.lower()

    def test_extract_action(self, tmp_path):
        f = tmp_path / "data.json"
        json.dump({"key": "value"}, f.open("w"))
        with patch(
            "actions.file_processor.generate_text",
            return_value="Extract result.",
        ):
            result = _process_json(f, "extract", {})
        assert "Extract result." in result


# =========================================================================
# 10. _process_code
# =========================================================================


class TestProcessCode:
    """_process_code handles info, explain, run, fix."""

    def test_info(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("def hello():\n    pass\n")
        result = _process_code(f, "info", {})
        assert "lines" in result
        assert "words" in result
        assert "size" in result.lower() or "B" in result

    def test_explain(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("x = 1\n")
        with patch(
            "actions.file_processor.generate_text",
            return_value="This code assigns 1 to x.",
        ):
            result = _process_code(f, "explain", {})
        assert "This code assigns 1 to x." in result

    def test_run_python(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("print('hello')")
        completed = subprocess.CompletedProcess(
            args=["python", str(f)], returncode=0, stdout="hello\n", stderr=""
        )
        with patch(
            "actions.file_processor.subprocess.run", return_value=completed
        ):
            result = _process_code(f, "run", {})
        assert "hello" in result

    def test_run_timeout(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("import time; time.sleep(999)")
        with patch(
            "actions.file_processor.subprocess.run",
            side_effect=subprocess.TimeoutExpired("python", 30),
        ):
            result = _process_code(f, "run", {})
        assert "timed out" in result

    def test_run_non_py(self, tmp_path):
        f = tmp_path / "script.js"
        f.write_text("console.log('hello')")
        result = _process_code(f, "run", {})
        assert "not supported" in result

    def test_fix_saves_result(self, tmp_path):
        f = tmp_path / "buggy.py"
        f.write_text("x = 1")
        fixed_code = "```py\nx = 2\n```"
        with patch(
            "actions.file_processor.generate_text",
            return_value=fixed_code,
        ):
            result = _process_code(f, "fix", {"save": True})
        assert "Saved:" in result or "Saved" in result

    def test_fix_no_save(self, tmp_path):
        f = tmp_path / "buggy.py"
        f.write_text("x = 1")
        with patch(
            "actions.file_processor.generate_text",
            return_value="Fixed: x = 2",
        ):
            result = _process_code(f, "fix", {"save": False})
        assert "Fixed:" in result

    def test_ai_failure(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("x = 1")
        with patch(
            "actions.file_processor.generate_text",
            side_effect=Exception("AI error"),
        ):
            result = _process_code(f, "explain", {})
        assert "AI processing failed" in result


# =========================================================================
# 11. _process_audio
# =========================================================================


class TestProcessAudio:
    """_process_audio handles info, transcribe, convert."""

    def _make_audio(self, tmp_path, name="test.mp3"):
        f = tmp_path / name
        f.write_bytes(b"fake audio bytes")
        return f

    def test_info_with_pydub(self, tmp_path):
        audio = self._make_audio(tmp_path)
        mock_segment = MagicMock()
        mock_segment.__len__.return_value = 10000  # 10 seconds
        mock_segment.channels = 2
        mock_segment.frame_rate = 44100
        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_segment
        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = _process_audio(audio, "info", {})
        assert "Audio:" in result
        assert "ch" in result
        assert "Hz" in result

    def test_info_without_pydub(self, tmp_path):
        audio = self._make_audio(tmp_path)
        result = _process_audio(audio, "info", {})
        assert "Audio file:" in result or "size" in result.lower()

    def test_transcribe(self, tmp_path):
        audio = self._make_audio(tmp_path)
        with patch(
            "actions.file_processor.generate_with_bytes",
            return_value="Transcription result.",
        ):
            result = _process_audio(audio, "transcribe", {})
        assert "Transcription" in result
        assert "Transcription result." in result or "saved" in result.lower()

    def test_transcribe_no_save(self, tmp_path):
        audio = self._make_audio(tmp_path)
        with patch(
            "actions.file_processor.generate_with_bytes",
            return_value="Transcription result.",
        ):
            result = _process_audio(audio, "transcribe", {"save": False})
        assert "Transcription result." in result

    def test_transcribe_failure(self, tmp_path):
        audio = self._make_audio(tmp_path)
        with patch(
            "actions.file_processor.generate_with_bytes",
            side_effect=Exception("transcribe error"),
        ):
            result = _process_audio(audio, "transcribe", {})
        assert "Transcription failed" in result

    def test_convert(self, tmp_path):
        audio = self._make_audio(tmp_path)
        mock_segment = MagicMock()
        mock_pydub = MagicMock()
        mock_pydub.AudioSegment.from_file.return_value = mock_segment
        with patch.dict("sys.modules", {"pydub": mock_pydub}):
            result = _process_audio(audio, "convert", {"format": "wav"})
        assert "Converted to WAV" in result

    def test_unknown_action(self, tmp_path):
        audio = self._make_audio(tmp_path)
        result = _process_audio(audio, "unknown_action", {})
        assert "Unknown audio action" in result


# =========================================================================
# 12. _process_video
# =========================================================================


class TestProcessVideo:
    """_process_video handles info, extract_audio, extract_frame, compress."""

    def _make_video(self, tmp_path, name="test.mp4"):
        f = tmp_path / name
        f.write_bytes(b"fake video bytes")
        return f

    def _mock_ffmpeg_available(self, monkeypatch):
        """Make _ffmpeg_available return True by mocking subprocess.run."""
        # We need to mock subprocess.run for ffmpeg -version to succeed
        # but the actual process functions also use subprocess.run with different args.
        # The inner _ffmpeg_available() is a nested function, so we need to patch
        # subprocess.run globally for the test to allow ffmpeg -version to pass.
        pass

    def test_info(self, tmp_path):
        video = self._make_video(tmp_path)
        fake_ffprobe_output = json.dumps({
            "format": {"duration": "120.5"},
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                }
            ],
        })
        mock_completed = subprocess.CompletedProcess(
            args=["ffprobe"], returncode=0, stdout=fake_ffprobe_output, stderr=""
        )
        with patch(
            "actions.file_processor.subprocess.run", return_value=mock_completed
        ):
            result = _process_video(video, "info", {})
        assert "Video:" in result
        assert "1920x1080" in result
        assert "30" in result or "fps" in result

    def test_info_fallback(self, tmp_path):
        """When ffprobe fails, return basic file size info."""
        video = self._make_video(tmp_path)
        with patch(
            "actions.file_processor.subprocess.run",
            side_effect=Exception("ffprobe not found"),
        ):
            result = _process_video(video, "info", {})
        assert "Video file:" in result or "B" in result

    def test_extract_audio_without_ffmpeg(self, tmp_path):
        """When ffmpeg is unavailable (subprocess raises), return error."""
        video = self._make_video(tmp_path)
        with patch(
            "actions.file_processor.subprocess.run",
            side_effect=FileNotFoundError("ffmpeg not found"),
        ):
            result = _process_video(video, "extract_audio", {})
        assert "ffmpeg not found" in result

    def test_extract_audio_with_ffmpeg(self, tmp_path):
        video = self._make_video(tmp_path)
        self._run_with_mocked_subprocess(
            tmp_path, video, "extract_audio", {},
            expected_in="Audio extracted",
        )

    def _run_with_mocked_subprocess(self, tmp_path, video, action, params,
                                     expected_in, also_mock_size=True):
        """Helper: mock subprocess.run and optionally _file_size_str
        so that ffmpeg commands appear to succeed without actually running."""
        mock_version_ok = subprocess.CompletedProcess(
            args=["ffmpeg", "-version"], returncode=0, stdout="ffmpeg 6.0", stderr=""
        )

        def side_effect(cmd, *args, **kwargs):
            # ffmpeg -version check → success
            if isinstance(cmd, list) and cmd[:2] == ["ffmpeg", "-version"]:
                return mock_version_ok
            # any other ffmpeg/subprocess call → pretend success
            return subprocess.CompletedProcess(cmd or [], returncode=0, stdout="", stderr="")

        patchers = [patch("actions.file_processor.subprocess.run", side_effect=side_effect)]
        if also_mock_size:
            patchers.append(
                patch("actions.file_processor._file_size_str", return_value="1 MB")
            )

        with contextlib.ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            result = _process_video(video, action, params)
        assert expected_in in result

    def test_extract_frame(self, tmp_path):
        video = self._make_video(tmp_path)
        self._run_with_mocked_subprocess(
            tmp_path, video, "extract_frame", {"timestamp": "00:00:05"},
            expected_in="Frame extracted",
        )

    def test_compress(self, tmp_path):
        video = self._make_video(tmp_path)
        self._run_with_mocked_subprocess(
            tmp_path, video, "compress", {"quality": "23"},
            expected_in="Compressed",
        )

    def test_compress_without_ffmpeg(self, tmp_path):
        video = self._make_video(tmp_path)
        with patch(
            "actions.file_processor.subprocess.run",
            side_effect=FileNotFoundError("ffmpeg not found"),
        ):
            result = _process_video(video, "compress", {})
        assert "ffmpeg not found" in result

    def test_unknown_action(self, tmp_path):
        video = self._make_video(tmp_path)
        result = _process_video(video, "unknown_action", {})
        assert "Unknown video action" in result


# =========================================================================
# 13. _process_archive
# =========================================================================


class TestProcessArchive:
    """_process_archive handles list and extract."""

    def test_list_zip(self, tmp_path):
        # Create a real zip file to test with
        arch = tmp_path / "test.zip"
        inner = tmp_path / "inner.txt"
        inner.write_text("hello")
        with zipfile.ZipFile(arch, "w") as z:
            z.write(inner, "inner.txt")

        result = _process_archive(arch, "list", {})
        assert "Archive contains" in result
        assert "inner.txt" in result

    def test_extract(self, tmp_path):
        arch = tmp_path / "test.zip"
        inner = tmp_path / "inner.txt"
        inner.write_text("hello")
        with zipfile.ZipFile(arch, "w") as z:
            z.write(inner, "inner.txt")

        dest = tmp_path / "extracted"
        result = _process_archive(arch, "extract", {"destination": str(dest)})
        assert "Extracted to" in result
        assert dest.exists()

    def test_list_unsupported_format(self, tmp_path):
        arch = tmp_path / "test.xyz"
        arch.write_bytes(b"fake")
        result = _process_archive(arch, "list", {})
        assert "Unsupported archive format" in result

    def test_list_extraction_failure(self, tmp_path):
        arch = tmp_path / "corrupt.zip"
        arch.write_bytes(b"corrupt data")
        result = _process_archive(arch, "list", {})
        assert "List failed" in result

    def test_unknown_action(self, tmp_path):
        arch = tmp_path / "test.zip"
        arch.write_bytes(b"PK\x03\x04")
        result = _process_archive(arch, "unknown_action", {})
        assert "Unknown archive action" in result


# =========================================================================
# 14. _process_pptx
# =========================================================================


class TestProcessPptx:
    """_process_pptx handles summarize, extract_text, analyze."""

    def _mock_presentation(self, slides_text=None):
        """Create a mock Presentation with slides containing text."""
        if slides_text is None:
            slides_text = [["Slide 1 content"], ["Slide 2 content"]]

        mock_prs = MagicMock()
        mock_slides = []
        for i, slide_texts in enumerate(slides_text, 1):
            mock_slide = MagicMock()
            mock_shapes = []
            for text in slide_texts:
                shape = MagicMock()
                shape.text = text
                shape.has_text = True
                mock_shapes.append(shape)
            mock_slide.shapes = mock_shapes
            mock_slides.append(mock_slide)
        mock_prs.slides = mock_slides
        return mock_prs

    def test_summarize(self, tmp_path):
        pptx = tmp_path / "slides.pptx"
        pptx.write_bytes(b"fake pptx")
        mock_prs = self._mock_presentation()
        with patch(
            "pptx.Presentation", return_value=mock_prs
        ), patch(
            "actions.file_processor.generate_text",
            return_value="Summary of presentation.",
        ):
            result = _process_pptx(pptx, "summarize", {})
        assert "Summary of presentation." in result

    def test_extract_text(self, tmp_path):
        pptx = tmp_path / "slides.pptx"
        pptx.write_bytes(b"fake pptx")
        mock_prs = self._mock_presentation()
        with patch(
            "pptx.Presentation", return_value=mock_prs
        ):
            result = _process_pptx(pptx, "extract_text", {})
        assert "Text extracted" in result
        assert "saved" in result.lower()

    def test_analyze(self, tmp_path):
        pptx = tmp_path / "slides.pptx"
        pptx.write_bytes(b"fake pptx")
        mock_prs = self._mock_presentation()
        with patch(
            "pptx.Presentation", return_value=mock_prs
        ), patch(
            "actions.file_processor.generate_text",
            return_value="Analysis of presentation.",
        ):
            result = _process_pptx(pptx, "analyze", {})
        assert "Analysis of presentation." in result

    def test_unknown_action(self, tmp_path):
        pptx = tmp_path / "slides.pptx"
        pptx.write_bytes(b"fake pptx")
        result = _process_pptx(pptx, "unknown_action", {})
        assert "Unknown PPTX action" in result


# =========================================================================
# 15. Error handling — top-level exception in dispatch
# =========================================================================


class TestFileProcessorErrorHandling:
    """Error handling in dispatch: exceptions from handlers are caught."""

    def test_handler_raises_exception(self, tmp_path):
        """If a handler raises an unhandled exception, file_processor catches it."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        with patch(
            "actions.file_processor._process_text_doc",
            side_effect=Exception("unexpected crash"),
        ):
            result = file_processor({
                "action": "summarize",
                "file_path": str(f),
            })
        assert "Processing failed" in result
        assert "unexpected crash" in result

    def test_unknown_file_type_dispatch(self, tmp_path):
        """If dispatch has no handler for a known type, return error."""
        f = tmp_path / "test.txt"
        f.write_text("content")
        # text type routes to _process_text_doc, which exists. The only way to
        # trigger "Unsupported file type" is if _detect_type returns something
        # unexpected. Since _detect_type only returns known strings, this path
        # is hard to reach in practice, but we test it by patching.
        with patch(
            "actions.file_processor._detect_type", return_value="something_unexpected"
        ):
            result = file_processor({
                "action": "summarize",
                "file_path": str(f),
            })
        assert "Unsupported file type" in result


# =========================================================================
# 16. Integration-style: main dispatch routes to correct handler
# =========================================================================


class TestFileProcessorDispatch:
    """Verify file_processor() routes to the correct handler per file type."""

    def test_dispatches_to_image(self, tmp_path):
        f = tmp_path / "photo.png"
        f.write_bytes(b"fake")
        with patch(
            "actions.file_processor._process_image",
            return_value="Image processed",
        ) as mock_fn:
            result = file_processor({
                "action": "describe",
                "file_path": str(f),
            })
        assert result == "Image processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_pdf(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"fake")
        with patch(
            "actions.file_processor._process_pdf",
            return_value="PDF processed",
        ) as mock_fn:
            result = file_processor({
                "action": "summarize",
                "file_path": str(f),
            })
        assert result == "PDF processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_text(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("hello")
        with patch(
            "actions.file_processor._process_text_doc",
            return_value="Text processed",
        ) as mock_fn:
            result = file_processor({
                "action": "word_count",
                "file_path": str(f),
            })
        assert result == "Text processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_csv(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2")
        with patch(
            "actions.file_processor._process_data",
            return_value="Data processed",
        ) as mock_fn:
            result = file_processor({
                "action": "info",
                "file_path": str(f),
            })
        assert result == "Data processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_code(self, tmp_path):
        f = tmp_path / "script.py"
        f.write_text("x=1")
        with patch(
            "actions.file_processor._process_code",
            return_value="Code processed",
        ) as mock_fn:
            result = file_processor({
                "action": "explain",
                "file_path": str(f),
            })
        assert result == "Code processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_video(self, tmp_path):
        f = tmp_path / "video.mp4"
        f.write_bytes(b"fake")
        with patch(
            "actions.file_processor._process_video",
            return_value="Video processed",
        ) as mock_fn:
            result = file_processor({
                "action": "info",
                "file_path": str(f),
            })
        assert result == "Video processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_audio(self, tmp_path):
        f = tmp_path / "audio.mp3"
        f.write_bytes(b"fake")
        with patch(
            "actions.file_processor._process_audio",
            return_value="Audio processed",
        ) as mock_fn:
            result = file_processor({
                "action": "transcribe",
                "file_path": str(f),
            })
        assert result == "Audio processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"a":1}')
        with patch(
            "actions.file_processor._process_json",
            return_value="JSON processed",
        ) as mock_fn:
            result = file_processor({
                "action": "validate",
                "file_path": str(f),
            })
        assert result == "JSON processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_archive(self, tmp_path):
        f = tmp_path / "data.zip"
        f.write_bytes(b"PK\x03\x04")
        with patch(
            "actions.file_processor._process_archive",
            return_value="Archive processed",
        ) as mock_fn:
            result = file_processor({
                "action": "list",
                "file_path": str(f),
            })
        assert result == "Archive processed"
        mock_fn.assert_called_once()

    def test_dispatches_to_pptx(self, tmp_path):
        f = tmp_path / "slides.pptx"
        f.write_bytes(b"fake")
        with patch(
            "actions.file_processor._process_pptx",
            return_value="PPTX processed",
        ) as mock_fn:
            result = file_processor({
                "action": "summarize",
                "file_path": str(f),
            })
        assert result == "PPTX processed"
        mock_fn.assert_called_once()

    def test_handler_returns_none(self, tmp_path):
        """If handler returns None, file_processor returns 'Done.'."""
        f = tmp_path / "photo.png"
        f.write_bytes(b"fake")
        with patch(
            "actions.file_processor._process_image",
            return_value=None,
        ):
            result = file_processor({
                "action": "describe",
                "file_path": str(f),
            })
        assert result == "Done."
