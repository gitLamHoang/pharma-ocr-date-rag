"""Synthetic pharma-like scanned pages with gold labels written by the generator.

    uv run --project backend python eval/synth.py generate --n 300 --seed 7 --out eval/synth

Each page is a made-up English document (certificate of analysis, certificate of a pharmaceutical
product with notarization / apostille / legalization stamps, SOP signature block, batch label)
drawn as a 200 DPI raster scan. Every page gets one degradation level, in turn: clean, 150 DPI,
blur 0.6, rotation up to 2 degrees, JPEG quality 40, salt-and-pepper noise, a stamp over a date,
or a mix of three of these. All names, products and numbers are invented.

Output, one folder per page: `page.png`, the same image as a one-page `page.pdf`, and `gold.json`
with the dates the generator printed (never anything read back by the extractor). Gold items use
the public set's format (`eval/gold/`): page, raw_text, date_type, and `normalized` or, for a
numeric date that reads as two valid dates, `candidates`. They also carry the printed `format`.
The same seed always gives the same pages.
"""

from __future__ import annotations

import argparse
import calendar
import io
import json
import random
import shutil
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

DPI = 200
WIDTH = 1654  # A4 width at 200 DPI
MARGIN = 120
INK = (20, 20, 20)
STAMP_INKS = [(30, 60, 170), (170, 30, 40), (40, 110, 60)]
KINDS = ("coa", "cpp", "sop", "label")
DEGRADATIONS = ("clean", "dpi150", "blur", "rotate", "jpeg", "salt", "stamp", "mixed")
MIXABLE = ("dpi150", "blur", "rotate", "jpeg", "salt", "stamp")
MONTHS = [calendar.month_name[m] for m in range(1, 13)]
ROMAN = "I II III IV V VI VII VIII IX X XI XII".split()

# Printed form of each format. Numeric day/month formats can read two ways; see `_gold_value`.
FORMATS = {
    "iso": lambda d: f"{d:%Y-%m-%d}",
    "dmy_slash": lambda d: f"{d.day:02d}/{d.month:02d}/{d.year}",
    "mdy_slash": lambda d: f"{d.month}/{d.day}/{d.year}",
    "dmy_dot": lambda d: f"{d.day:02d}.{d.month:02d}.{d.year}",
    "dmy_dash": lambda d: f"{d.day:02d}-{d.month:02d}-{d.year}",
    "spaced_dot": lambda d: f"{d.day:02d} . {d.month:02d} . {d.year}",
    "spaced_dot_right": lambda d: f"{d.day:02d}. {d.month:02d}. {d.year}",
    "spaced_slash": lambda d: f"{d.day:02d} / {d.month:02d} / {d.year}",
    "d_mon_y": lambda d: f"{d.day} {MONTHS[d.month - 1][:3]} {d.year}",
    "d_month_y": lambda d: f"{d.day} {MONTHS[d.month - 1]} {d.year}",
    "month_d_y": lambda d: f"{MONTHS[d.month - 1]} {d.day}, {d.year}",
    "d_mon_dot_y": lambda d: f"{d.day} {MONTHS[d.month - 1][:3]}. {d.year}",
    "d_mon_y_dash": lambda d: f"{d.day:02d}-{MONTHS[d.month - 1][:3].upper()}-{d.year}",
    "d_mon_y_dot": lambda d: f"{d.day:02d}.{MONTHS[d.month - 1][:3]}.{d.year}",
    "compact": lambda d: f"{d.day:02d}{MONTHS[d.month - 1][:3].upper()}{d.year}",
    "roman_dot": lambda d: f"{d.day}.{ROMAN[d.month - 1]}.{d.year}",
    "roman_dash": lambda d: f"{d.day:02d}-{ROMAN[d.month - 1]}-{d.year}",
    "roman_space": lambda d: f"{d.day} {ROMAN[d.month - 1]} {d.year}",
    "month_year_slash": lambda d: f"{d.month:02d}/{d.year}",
    "mon_year": lambda d: f"{MONTHS[d.month - 1][:3].upper()} {d.year}",
    "month_year": lambda d: f"{MONTHS[d.month - 1]} {d.year}",
}
MONTH_ONLY = {"month_year_slash", "mon_year", "month_year"}
DAY_FIRST = {"dmy_slash", "dmy_dot", "dmy_dash", "spaced_dot", "spaced_dot_right", "spaced_slash"}
MONTH_FIRST = {"mdy_slash"}
FULL_DATE_FORMATS = [f for f in FORMATS if f not in MONTH_ONLY]
# Formats a batch label prints right after EXP / MFG / MFD with no space ("EXP03/2027").
ADJACENT_FORMATS = ["month_year_slash", "compact", "iso", "dmy_dot", "mon_year"]

PRODUCTS = [
    "Examplomycin 250 mg film-coated tablets",
    "Placebol 10 mg/mL oral solution",
    "Synthazine 5 mg hard capsules",
    "Demoprofen 400 mg tablets",
    "Testovir 100 mg powder for infusion",
]
COMPANIES = ["Example Pharma Ltd", "Demo Biologics Inc.", "Sample Laboratories GmbH"]
PEOPLE = ["A. Novak", "M. Okafor", "L. Brennan", "S. Ito", "R. Duarte", "K. Lindqvist", "P. Mensah"]
# Text that looks a little like a date but is not one; never in the gold labels.
DISTRACTORS = [
    "LOT 12031",
    "Quality system certified to ISO 9001:2015",
    "Tel: +1 (212) 555-0147",
    "Fax: 020 7946 0958",
    "pH 6.8   Assay 99.2 %",
    "Batch size: 120 000 tablets",
    "Store below 25 C. Protect from light.",
]


@dataclass
class Seg:
    text: str
    item: dict | None = None  # the gold item when this segment is a printed date
    x: int | None = None  # absolute column; otherwise right after the previous segment


@dataclass
class Page:
    rows: list[list[Seg]] = field(default_factory=list)
    stamps: list[tuple[list[list[Seg]], tuple[int, int, int]]] = field(default_factory=list)
    items: list[dict] = field(default_factory=list)


# --- Content -----------------------------------------------------------------------------------


def _gold_value(fmt: str, d: date) -> dict:
    if fmt in MONTH_ONLY:
        return {"normalized": f"{d.year:04d}-{d.month:02d}"}
    if fmt in DAY_FIRST or fmt in MONTH_FIRST:
        swapped = _safe(d.year, d.day, d.month)  # the other reading of the same two numbers
        if swapped is not None and swapped != d:
            return {"candidates": sorted([d.isoformat(), swapped.isoformat()])}
    return {"normalized": d.isoformat()}


def _safe(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


class Builder:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.page = Page()

    def date_seg(self, d: date, date_type: str, fmts: list[str] | None = None) -> Seg:
        fmt = self.rng.choice(fmts or FULL_DATE_FORMATS)
        text = FORMATS[fmt](d)
        item = {"page": 1, "raw_text": text, "date_type": date_type, "format": fmt} | _gold_value(fmt, d)
        self.page.items.append(item)
        return Seg(text, item)

    def row(self, *segs: Seg | str) -> None:
        self.page.rows.append([Seg(s) if isinstance(s, str) else s for s in segs])

    def blank(self) -> None:
        self.page.rows.append([])

    def distractor(self) -> None:
        self.row(self.rng.choice(DISTRACTORS))


def _random_date(rng: random.Random) -> date:
    return date(2019, 1, 1) + timedelta(days=rng.randrange(9 * 365))


def _coa(b: Builder) -> None:
    rng = b.rng
    mfg = _random_date(rng)
    b.row(rng.choice(COMPANIES))
    b.row("CERTIFICATE OF ANALYSIS")
    b.blank()
    b.row(f"Product: {rng.choice(PRODUCTS)}")
    b.row(f"Batch No.: B{rng.randrange(10000, 99999)}")
    b.distractor()
    b.row("Date of manufacture: ", b.date_seg(mfg, "manufacture_date"))
    b.row("Expiry date: ", b.date_seg(mfg + timedelta(days=rng.choice([730, 1095])), "expiry_date"))
    if rng.random() < 0.5:
        b.row("Retest date: ", b.date_seg(mfg + timedelta(days=365), "retest_date"))
    b.row("Date of analysis: ", b.date_seg(mfg + timedelta(days=rng.randrange(3, 20)), "test_date"))
    b.blank()
    b.row(Seg("Test", x=0), Seg("Specification", x=420), Seg("Result", x=900))
    b.row(Seg("Assay", x=0), Seg("95.0 - 105.0 %", x=420), Seg("99.2 %", x=900))
    b.row(Seg("Dissolution", x=0), Seg("NLT 80 % (Q)", x=420), Seg("91 %", x=900))
    b.distractor()
    b.blank()
    released = mfg + timedelta(days=rng.randrange(20, 40))
    b.row(f"Released by QA: {rng.choice(PEOPLE)}   Signature: ________")
    b.row("Date: ", b.date_seg(released, "signature_date"))
    b.distractor()


def _cpp(b: Builder) -> None:
    rng = b.rng
    issued = _random_date(rng)
    b.row("CERTIFICATE OF A PHARMACEUTICAL PRODUCT")
    b.row("This certificate conforms to the format recommended by WHO.")
    b.blank()
    b.row(f"Certificate No.: CPP-{rng.randrange(1000, 9999)}")
    b.row(f"Name of product: {rng.choice(PRODUCTS)}")
    b.row(f"Product licence holder: {rng.choice(COMPANIES)}")
    b.distractor()
    b.row("Date of issue: ", b.date_seg(issued, "certificate_issue_date"))
    b.row(
        "This certificate is valid until: ",
        b.date_seg(issued + timedelta(days=730), "certificate_valid_until"),
    )
    b.blank()
    b.row(f"Authorized signatory: {rng.choice(PEOPLE)}   Signed: ", b.date_seg(issued, "signature_date"))
    b.blank()
    stamps = [
        ("NOTARY PUBLIC", f"Notary: {rng.choice(PEOPLE)}", "Notarized on: ", "notarization_date"),
        ("APOSTILLE", "Issued by the competent authority", "6. the ", "apostille_date"),
        ("LEGALIZED", "Consular section, Embassy of Exampleland", "Date: ", "legalization_date"),
    ]
    for title, line, prefix, date_type in rng.sample(stamps, rng.randrange(1, 4)):
        when = issued + timedelta(days=rng.randrange(2, 30))
        rows = [[Seg(title)], [Seg(line)], [Seg(prefix), b.date_seg(when, date_type)]]
        b.page.stamps.append((rows, rng.choice(STAMP_INKS)))
    b.distractor()


def _sop(b: Builder) -> None:
    rng = b.rng
    effective = _random_date(rng)
    b.row(rng.choice(COMPANIES))
    b.row(f"STANDARD OPERATING PROCEDURE SOP-QA-{rng.randrange(100, 999)}")
    b.row("Title: Handling of out-of-specification results")
    b.row(f"Version: {rng.randrange(1, 9)}.0")
    b.row("Effective date: ", b.date_seg(effective, "effective_date"))
    b.row("Next review date: ", b.date_seg(effective + timedelta(days=730), "next_review_date"))
    b.blank()
    b.row(Seg("Role", x=0), Seg("Name", x=380), Seg("Signature", x=760), Seg("Date", x=1080))
    for role, offset in (("Prepared by", 20), ("Reviewed by", 12), ("Approved by", 5)):
        signed = effective - timedelta(days=offset + rng.randrange(0, 4))
        b.row(
            Seg(role, x=0),
            Seg(rng.choice(PEOPLE), x=380),
            Seg("________", x=760),
            Seg("", x=1080),
            b.date_seg(signed, "signature_date"),
        )
    b.blank()
    b.row("Revision history")
    previous = effective - timedelta(days=rng.randrange(400, 900))
    b.row(Seg("1.0", x=0), Seg("", x=160), b.date_seg(previous, "version_date"), Seg("First issue", x=600))
    b.distractor()


def _label(b: Builder) -> None:
    rng = b.rng
    mfg = _random_date(rng)
    expiry = mfg + timedelta(days=rng.choice([365, 730, 1095]))
    b.row(rng.choice(PRODUCTS))
    b.row("LOT 12031" if rng.random() < 0.5 else f"Batch: B{rng.randrange(10000, 99999)}")
    for label, d, date_type in (("MFG", mfg, "manufacture_date"), ("EXP", expiry, "expiry_date")):
        if label == "MFG" and rng.random() < 0.4:
            label = "MFD"
        style = rng.random()
        if style < 0.4:  # adjacent: "EXP03/2027", "MFD:12.03.2026"
            fmts = (
                ADJACENT_FORMATS
                if date_type == "expiry_date"
                else [f for f in ADJACENT_FORMATS if f not in MONTH_ONLY]
            )
            b.row(label + rng.choice(["", ":", ""]), b.date_seg(d, date_type, fmts))  # ":" one time in 3
        elif date_type == "expiry_date" and style < 0.7:
            b.row(f"{label} ", b.date_seg(d, date_type, sorted(MONTH_ONLY)))
        else:
            b.row(f"{label} ", b.date_seg(d, date_type))
    b.distractor()
    b.row(rng.choice(COMPANIES))


BUILDERS = {"coa": _coa, "cpp": _cpp, "sop": _sop, "label": _label}


# --- Drawing -----------------------------------------------------------------------------------


def _draw_rows(draw: ImageDraw.ImageDraw, rows: list[list[Seg]], x0: int, y0: int, font, fill) -> list[tuple]:
    """Draw rows of segments; returns (item, box) for every printed date."""
    boxes = []
    line_h = int(font.size * 1.6)
    for r, row in enumerate(rows):
        y = y0 + r * line_h
        x = x0
        for seg in row:
            if seg.x is not None:
                x = x0 + seg.x
            if seg.text:
                draw.text((x, y), seg.text, font=font, fill=fill)
                if seg.item is not None:
                    boxes.append((seg.item, draw.textbbox((x, y), seg.text, font=font)))
            x += int(draw.textlength(seg.text, font=font))
    return boxes


def render(page: Page, rng: random.Random) -> tuple[Image.Image, list[tuple]]:
    font = ImageFont.load_default(size=rng.randrange(30, 40))
    line_h = int(font.size * 1.6)
    stamp_font = ImageFont.load_default(size=int(font.size * 0.9))
    stamp_h = 3 * int(stamp_font.size * 1.6) + 60
    # Stamps go below the text, side by side while they fit, each a box of coloured ink.
    places, x, y = [], MARGIN, MARGIN + len(page.rows) * line_h + 20
    for rows, ink in page.stamps:
        width = max(int(stamp_font.getlength("".join(s.text for s in row))) for row in rows) + 60
        if x > MARGIN and x + width > WIDTH - MARGIN:
            x, y = MARGIN, y + stamp_h + 40
        places.append((rows, ink, x, y, width))
        x += width + 40
    bottom = y + stamp_h + 20 if page.stamps else MARGIN + len(page.rows) * line_h
    img = Image.new("RGB", (WIDTH, bottom + MARGIN), "white")
    boxes = _draw_rows(ImageDraw.Draw(img), page.rows, MARGIN, MARGIN, font, INK)
    for rows, ink, x, y, width in places:
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        draw.rectangle((x, y, x + width, y + stamp_h), outline=ink + (230,), width=5)
        boxes += _draw_rows(draw, rows, x + 30, y + 30, stamp_font, ink + (235,))
        img = Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")
    return img, boxes


# --- Degradations ------------------------------------------------------------------------------


def _stamp_over(img: Image.Image, box: tuple, rng: random.Random) -> Image.Image:
    """A round "CERTIFIED COPY" stamp in translucent ink, centred on a printed date."""
    cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
    r = max(90, (box[2] - box[0]) // 2 + 30)
    layer = Image.new("RGBA", (2 * r + 20, 2 * r + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    ink = rng.choice(STAMP_INKS)
    draw.ellipse((10, 10, 2 * r + 10, 2 * r + 10), outline=ink + (120,), width=8)
    draw.ellipse((40, 40, 2 * r - 20, 2 * r - 20), outline=ink + (100,), width=3)
    font = ImageFont.load_default(size=max(24, r // 4))
    draw.text((r + 10, r + 10), "CERTIFIED COPY", font=font, fill=ink + (110,), anchor="mm")
    layer = layer.rotate(rng.uniform(-25, 25), resample=Image.Resampling.BICUBIC)
    out = img.convert("RGBA")
    out.alpha_composite(layer, (max(0, cx - r - 10), max(0, cy - r - 10)))
    return out.convert("RGB")


def degrade(
    img: Image.Image, steps: list[str], boxes: list[tuple], rng: random.Random
) -> tuple[Image.Image, int]:
    """Apply the degradation steps in order; returns the image and its resolution in DPI."""
    dpi = DPI
    for step in steps:
        if step == "stamp" and boxes:
            img = _stamp_over(img, rng.choice(boxes)[1], rng)
        elif step == "dpi150":
            dpi = 150
            size = (round(img.width * 150 / DPI), round(img.height * 150 / DPI))
            img = img.resize(size, Image.Resampling.LANCZOS)
        elif step == "blur":
            img = img.filter(ImageFilter.GaussianBlur(0.6))
        elif step == "rotate":
            angle = rng.choice([-1, 1]) * rng.uniform(0.5, 2.0)
            img = img.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor="white")
        elif step == "jpeg":
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=40)
            img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
        elif step == "salt":
            img = _salt_and_pepper(img, rng, density=0.01)
    return img, dpi


def _salt_and_pepper(img: Image.Image, rng: random.Random, density: float) -> Image.Image:
    noise = Image.frombytes("L", img.size, rng.randbytes(img.width * img.height))
    cut = round(255 * density / 2)
    pepper = noise.point(lambda v: 255 if v < cut else 0)
    salt = noise.point(lambda v: 255 if v > 255 - cut else 0)
    img = img.copy()
    img.paste((0, 0, 0), mask=pepper)
    img.paste((255, 255, 255), mask=salt)
    return img


# --- Generation --------------------------------------------------------------------------------


def generate_page(index: int, seed: int) -> tuple[Image.Image, int, dict]:
    rng = random.Random(f"{seed}-{index}")
    kind = KINDS[index % len(KINDS)]
    degradation = DEGRADATIONS[(index // len(KINDS)) % len(DEGRADATIONS)]
    builder = Builder(rng)
    BUILDERS[kind](builder)
    img, boxes = render(builder.page, rng)
    steps = sorted(rng.sample(MIXABLE, 3), key=MIXABLE.index) if degradation == "mixed" else [degradation]
    # The stamp goes on before any scan degradation, as on a real stamped page.
    steps = [s for s in steps if s == "stamp"] + [s for s in steps if s not in ("stamp", "clean")]
    img, dpi = degrade(img, steps, boxes, rng)
    page_id = f"{index:03d}-{kind}-{degradation}"
    gold = {"id": page_id, "kind": kind, "degradation": degradation, "steps": steps, "dpi": dpi}
    return img, dpi, gold | {"items": builder.page.items}


def generate(n: int, seed: int, out: Path) -> None:
    """Write `n` pages to `out`, replacing the pages of an earlier run (folders with a gold.json)."""
    for old in out.glob("*/gold.json"):
        shutil.rmtree(old.parent)
    for index in range(n):
        img, dpi, gold = generate_page(index, seed)
        folder = out / gold["id"]
        folder.mkdir(parents=True)
        img.save(folder / "page.png", dpi=(dpi, dpi))
        fixed = time.gmtime(1767225600)  # 2026-01-01: a fixed timestamp keeps the PDF reproducible
        img.save(folder / "page.pdf", "PDF", resolution=dpi, creationDate=fixed, modDate=fixed)
        (folder / "gold.json").write_text(json.dumps(gold, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate", help="write the synthetic set")
    gen.add_argument("--n", type=int, default=300)
    gen.add_argument("--seed", type=int, default=7)
    gen.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "synth")
    args = parser.parse_args()
    generate(args.n, args.seed, args.out)
    print(f"written: {args.n} pages to {args.out}")


if __name__ == "__main__":
    main()
