"""Real in-memory files, synthetic provider text; no private materials."""
import io
import zipfile

import pytest

from PIL import Image

from app.readers import read_upload
from tests.test_llm_assistant import FakeLLM


def png():
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(buf, format="PNG")
    return buf.getvalue()


def pdf_bytes(pages):
    """Minimal real PDF with selectable ASCII text or empty pages."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        page_id = len(objects) + 1
        kids.append(f"{page_id} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>".encode())
        stream = f"BT /F1 12 Tf 30 200 Td ({text}) Tj ET".encode()
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Count {len(pages)} /Kids [{' '.join(kids)}] >>".encode()
    out, offsets = bytearray(b"%PDF-1.4\n"), [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    start = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF".encode())
    return bytes(out)


def test_text_is_preserved(tmp_path):
    text = " 原文第一行\r\n金额：20000元\n"
    assert read_upload("a.txt", text.encode(), FakeLLM([], tmp_path)).text == text


def test_invalid_image_makes_no_provider_call(tmp_path):
    llm = FakeLLM(["假的成功"], tmp_path)
    result = read_upload("a.jpg", b"\xff\xd8\xff", llm)
    assert result.method == "failed" and not llm.calls


def test_image_calls_vision_role(tmp_path):
    llm = FakeLLM(["金额123元"], tmp_path)
    result = read_upload("a.png", png(), llm)
    assert result.method == "vision" and result.text == "金额123元"
    assert "原图" in result.note


def test_pdf_mixed_scan_and_text_is_explicitly_partial(tmp_path):
    result = read_upload("a.pdf", pdf_bytes(["PAYEE A", ""]), FakeLLM([], tmp_path))
    assert "PAYEE A" in result.text
    assert result.note and "2" in result.note and "手动" in result.note


def test_pdf_scanned_and_corrupt_request_manual_paste(tmp_path):
    for data in (pdf_bytes([""]), b"broken pdf"):
        result = read_upload("a.pdf", data, FakeLLM([], tmp_path))
        assert result.method == "failed" and "手动录入" in result.note


def test_empty_text_and_empty_vision_are_not_success(tmp_path):
    assert read_upload("a.txt", b"", FakeLLM([], tmp_path)).method == "failed"
    assert read_upload("a.png", png(), FakeLLM(["   "], tmp_path)).method == "failed"


def test_material_limits_and_mime_mismatch(tmp_path):
    from app.readers import read_material
    llm = FakeLLM(["do not send"], tmp_path)
    result = read_material(png(), filename="a.png", content_type="application/pdf", gateway=llm)
    assert result.status == "failed" and not llm.calls
    result = read_material(b"hello", filename="a.txt", content_type="text/plain", max_bytes=4)
    assert result.status == "failed" and not result.text
    result = read_material(pdf_bytes(["one", "two"]), filename="a.pdf", content_type="application/pdf", max_pdf_pages=1)
    assert result.status == "failed" and not result.text


def test_read_material_preserves_page_numbers():
    from app.readers import read_material
    result = read_material(pdf_bytes(["one", "", "three"]), filename="a.pdf", content_type="application/pdf")
    assert result.status == "partial"
    assert [(p.page_number, p.text) for p in result.pages] == [(1, "one"), (2, ""), (3, "three")]


def test_docx_decodes_xml_entities(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>A &amp; B</w:t></w:r></w:p></w:body></w:document>')
    result = read_upload("a.docx", buf.getvalue(), FakeLLM([], tmp_path))
    assert result.text == "A & B"


def test_encrypted_pdf_error_is_manual_not_server_error(tmp_path, monkeypatch):
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    def encrypted(*args, **kwargs):
        raise PDFPasswordIncorrect("synthetic password failure")
    monkeypatch.setattr(pdfplumber, "open", encrypted)
    result = read_upload("a.pdf", pdf_bytes(["secret"]), FakeLLM([], tmp_path))
    assert result.method == "failed" and "手动录入" in result.note


def test_pdf_page_error_keeps_successful_page(monkeypatch):
    from pdfplumber.page import Page
    from app.readers import read_material
    original = Page.extract_text
    def broken_second(self, **kwargs):
        if self.page_number == 2:
            raise ValueError("synthetic page decoding failure")
        return original(self, **kwargs)
    monkeypatch.setattr(Page, "extract_text", broken_second)
    result = read_material(pdf_bytes(["first", "second"]), filename="a.pdf", content_type="application/pdf")
    assert result.text.startswith("first") and result.status == "partial"
    assert result.pages[1].status == "failed" and result.warnings


def test_image_pixel_limit_prevents_external_transfer(tmp_path):
    from app.readers import read_material
    llm = FakeLLM(["not called"], tmp_path)
    result = read_material(png(), filename="a.png", content_type="image/png", gateway=llm, max_image_pixels=100)
    assert result.status == "failed" and not llm.calls
