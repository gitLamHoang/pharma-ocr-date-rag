"""Scan clean-up before the second OCR pass, and how layout_page chooses between the passes."""

import pytest
from PIL import Image, ImageDraw, ImageFont

from pharma_dates import layout
from pharma_dates.ingest import ingest
from pharma_dates.layout import layout_page
from pharma_dates.models import BBox
from pharma_dates.preprocess import estimate_x_height, prepare, to_original

LINES = [
    "CERTIFICATE OF ANALYSIS",
    "Product: Examplomycin 250 mg tablets",
    "Date of manufacture: 12 March 2026",
    "Expiry date: 11 March 2028",
    "Released by QA on 2026-03-30",
]


def text_page(size: int, width: int = 1400) -> Image.Image:
    font = ImageFont.load_default(size=size)
    img = Image.new("RGB", (width, int(size * 1.8) * len(LINES) + 200), "white")
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(LINES):
        draw.text((80, 100 + i * int(size * 1.8)), line, font=font, fill="black")
    return img


def test_deskew_recovers_2deg():
    skewed = text_page(36).rotate(2, resample=Image.Resampling.BICUBIC, fillcolor="white")
    assert prepare(skewed).info["deskew_angle"] == pytest.approx(-2, abs=0.25)


def test_straight_page_is_not_rotated():
    assert prepare(text_page(36)).info["deskew_angle"] == 0.0


def test_upscale_small_text():
    small = text_page(16)
    prepared = prepare(small)
    assert estimate_x_height(small.convert("L")) < 20
    assert prepared.info["scale"] > 1.5
    assert prepared.size == (
        round(small.width * prepared.info["scale"]),
        round(small.height * prepared.info["scale"]),
    )


def test_large_text_is_not_upscaled():
    big = text_page(60)
    prepared = prepare(big)
    assert prepared.info["scale"] == 1.0
    assert prepared.size == big.size


def test_prepared_page_is_black_on_white():
    page = text_page(36)
    noisy = page.copy()
    draw = ImageDraw.Draw(noisy)
    draw.rectangle((0, 0, noisy.width, noisy.height), fill=(200, 200, 200))  # grey paper
    for i, line in enumerate(LINES):
        draw.text(
            (80, 100 + i * int(36 * 1.8)), line, font=ImageFont.load_default(size=36), fill=(70, 70, 70)
        )
    prepared = prepare(noisy)
    assert prepared.mode == "L"
    assert set(prepared.get_flattened_data()) <= {0, 255}
    # Paper becomes white, text stays dark: about as much ink as on the clean page.
    ink = sum(1 for v in prepared.get_flattened_data() if v == 0)
    clean_ink = sum(1 for v in prepare(page).get_flattened_data() if v == 0)
    assert 0.6 * clean_ink < ink < 1.6 * clean_ink


def test_blank_page_is_left_alone():
    prepared = prepare(Image.new("RGB", (800, 600), "white"))
    assert prepared.info["deskew_angle"] == 0.0
    assert prepared.info["scale"] == 1.0
    assert set(prepared.get_flattened_data()) == {255}


def test_boxes_map_back_to_the_original_page():
    original = Image.new("L", (900, 700), 255)
    ImageDraw.Draw(original).rectangle((600, 150, 619, 169), fill=0)
    # The same rotation and scale `prepare` applies, done by hand so the expected place is known.
    moved = original.rotate(2, resample=Image.Resampling.BICUBIC, fillcolor=255).resize((1800, 1400))
    moved.info.update(deskew_angle=2.0, scale=2.0, original_size=original.size)
    x0, y0, x1, y1 = moved.point(lambda v: 255 if v < 128 else 0).getbbox()
    box = to_original(BBox(x0=x0, y0=y0, x1=x1, y1=y1), moved)
    assert box.x0 == pytest.approx(600, abs=3) and box.x1 == pytest.approx(620, abs=3)
    assert box.y0 == pytest.approx(150, abs=3) and box.y1 == pytest.approx(170, abs=3)


def _tesseract_data(words: list[tuple[str, float, int]]) -> dict:
    """image_to_data output for one line of words (text, confidence 0-100, left)."""
    return {
        "text": [w[0] for w in words],
        "conf": [w[1] for w in words],
        "left": [w[2] for w in words],
        "top": [100] * len(words),
        "width": [10 * len(w[0]) for w in words],
        "height": [30] * len(words),
        "block_num": [1] * len(words),
        "par_num": [1] * len(words),
        "line_num": [1] * len(words),
    }


@pytest.mark.parametrize(
    ("original_conf", "prepared_conf", "expected"),
    [(40, 90, "Expiry 31/03/2027"), (90, 40, "Expiry 31/O3/2O27"), (70, 70, "Expiry 31/O3/2O27")],
)
def test_confidence_selects_better_pass(
    monkeypatch, tmp_path, settings, original_conf, prepared_conf, expected
):
    path = tmp_path / "scan.png"
    text_page(36).save(path)

    def fake_image_to_data(img, **kwargs):
        if "deskew_angle" in img.info:  # the prepared image
            return _tesseract_data([("Expiry", prepared_conf, 160), ("31/03/2027", prepared_conf, 320)])
        return _tesseract_data(
            [("Expiry", original_conf, 80), ("31/O3/2O27", original_conf, 160), ("", -1, 0)]
        )

    monkeypatch.setattr(layout.pytesseract, "image_to_data", fake_image_to_data)
    page = layout_page(ingest(path, settings), 1, settings)
    assert page.text == expected
    assert {w.confidence for w in page.words} == {max(original_conf, prepared_conf) / 100}


def test_prepared_pass_boxes_are_on_the_original_page(monkeypatch, tmp_path, settings):
    path = tmp_path / "scan.png"
    text_page(16).save(path)  # small text: the prepared image is upscaled

    def fake_image_to_data(img, **kwargs):
        if "deskew_angle" in img.info:
            scale = img.info["scale"]
            return _tesseract_data([("31/03/2027", 95, round(200 * scale))])
        return _tesseract_data([("31/O3/2O27", 50, 200)])

    monkeypatch.setattr(layout.pytesseract, "image_to_data", fake_image_to_data)
    [word] = layout_page(ingest(path, settings), 1, settings).words
    assert word.text == "31/03/2027"
    assert word.bbox.x0 == pytest.approx(200, abs=1)
