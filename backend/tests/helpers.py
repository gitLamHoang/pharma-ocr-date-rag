"""Plain helpers shared by test modules (importable via `pythonpath = ["tests"]`)."""

from pharma_dates.models import BBox, PageLayout, Word

CHAR_W, LINE_H = 10, 20


def make_layout(lines: list[str], n: int = 1, transcription: str | None = None) -> PageLayout:
    """A layout whose word boxes follow the character grid: x = column * 10, y = line * 20."""
    words, pos = [], 0
    for row, line in enumerate(lines):
        col = 0
        for text in line.split(" "):
            if text:
                box = BBox(
                    x0=col * CHAR_W, y0=row * LINE_H, x1=(col + len(text)) * CHAR_W, y1=row * LINE_H + 15
                )
                words.append(Word(text=text, bbox=box, char_start=pos + col, char_end=pos + col + len(text)))
            col += len(text) + 1
        pos += len(line) + 1
    return PageLayout(
        n=n,
        width=1000,
        height=1000,
        text="\n".join(lines),
        text_source="pdf",
        words=words,
        transcription=transcription,
    )
