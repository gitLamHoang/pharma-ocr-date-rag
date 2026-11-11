"""Test fixtures generated at test time (no binary documents are committed)."""

from pathlib import Path

import pytest
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from pharma_dates.config import Settings

SAMPLE_TEXT = "Expiry date: 31/03/2027"


def make_text_pdf(path: Path, lines_per_page: list[str]) -> Path:
    pdf = FPDF()
    pdf.set_font("Helvetica", size=14)
    for line in lines_per_page:
        pdf.add_page()
        pdf.cell(text=line)
    pdf.output(str(path))
    return path


@pytest.fixture
def make_pdf():
    return make_text_pdf


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", ai_enabled=False)


@pytest.fixture
def native_pdf(tmp_path: Path) -> Path:
    return make_text_pdf(tmp_path / "native.pdf", [SAMPLE_TEXT])


@pytest.fixture
def scanned_png(tmp_path: Path) -> Path:
    img = Image.new("RGB", (1400, 300), "white")
    ImageDraw.Draw(img).text((60, 110), SAMPLE_TEXT, fill="black", font=ImageFont.load_default(size=56))
    path = tmp_path / "scan.png"
    img.save(path)
    return path


@pytest.fixture
def blank_png(tmp_path: Path) -> Path:
    path = tmp_path / "blank.png"
    Image.new("RGB", (1000, 800), "white").save(path)
    return path


@pytest.fixture
def encrypted_pdf(tmp_path: Path) -> Path:
    pdf = FPDF()
    pdf.set_encryption(owner_password="owner-test", user_password="user-test")  # pragma: allowlist secret
    pdf.add_page()
    pdf.set_font("Helvetica", size=14)
    pdf.cell(text=SAMPLE_TEXT)
    path = tmp_path / "encrypted.pdf"
    pdf.output(str(path))
    return path


@pytest.fixture
def corrupt_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "corrupt.pdf"
    path.write_bytes(b"%PDF-1.7\n1 0 obj << /Type /Catalog >>\nthis is not a real pdf\n")
    return path
