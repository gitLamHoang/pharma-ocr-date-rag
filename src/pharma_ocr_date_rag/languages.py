"""Small, inspectable vocabularies for the date fields in our synthetic corpus."""
from __future__ import annotations

from functools import lru_cache
import re
import unicodedata


LANGUAGES = {"auto": "All languages", "en": "English", "fr": "French", "de": "German", "es": "Spanish", "vi": "Vietnamese"}

MONTH_NAMES = {
    "en": "January February March April May June July August September October November December".split(),
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(),
    "de": "Januar Februar März April Mai Juni Juli August September Oktober November Dezember".split(),
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
}

FIELD_WORDS = {
    "en": {
        "expiry": ["expiry", "expiration", "expires", "exp", "use before", "valid until", "shelf life"],
        "manufacture": ["manufacture", "manufactured", "mfg", "production", "packed"],
        "qa_check": ["qa", "qc", "quality", "check", "inspection", "reviewed", "verified", "released"],
        "audit": ["audit", "supplier visit", "vendor review"],
        "received": ["received", "arrival", "delivered"],
        "document": ["document", "issued", "printed", "report date"],
    },
    "fr": {
        "expiry": ["péremption", "expiration", "expire", "utiliser avant"],
        "manufacture": ["fabrication", "fabriqué", "production"],
        "qa_check": ["contrôle", "qualité", "vérifié", "inspection"],
        "audit": ["audit", "visite fournisseur"],
        "received": ["réception", "reçu", "livraison"],
        "document": ["émission", "rapport", "document"],
    },
    "de": {
        "expiry": ["Verfallsdatum", "Verfall", "haltbar bis", "Ablaufdatum"],
        "manufacture": ["Herstellungsdatum", "Herstellung", "hergestellt"],
        "qa_check": ["Qualitätsprüfung", "geprüft", "Kontrolle", "Prüfdatum"],
        "audit": ["Audit", "Lieferantenbesuch"],
        "received": ["Wareneingang", "Eingangsdatum", "erhalten"],
        "document": ["Berichtsdatum", "ausgestellt", "Dokument"],
    },
    "es": {
        "expiry": ["caducidad", "vencimiento", "vence", "utilizar antes"],
        "manufacture": ["fabricación", "fabricado", "producción"],
        "qa_check": ["calidad", "verificado", "inspección", "revisión"],
        "audit": ["auditoría", "visita proveedor"],
        "received": ["recepción", "recibido", "entregado"],
        "document": ["emisión", "informe", "documento"],
    },
    "vi": {
        "expiry": ["hạn sử dụng", "hết hạn", "hsd"],
        "manufacture": ["ngày sản xuất", "sản xuất", "nsx"],
        "qa_check": ["kiểm tra", "chất lượng", "kiểm nghiệm"],
        "audit": ["đánh giá", "kiểm toán"],
        "received": ["ngày nhận", "nhập kho", "tiếp nhận"],
        "document": ["phát hành", "báo cáo", "tài liệu"],
    },
}


def fold(text: str) -> str:
    # One base character per source character keeps offsets stable for NFC text.
    return "".join(
        unicodedata.normalize("NFD", char.lower().replace("đ", "d"))[0]
        for char in text
    )


def validate_language(language: str) -> None:
    if language not in LANGUAGES:
        raise ValueError(f"Unsupported language: {language}. Choose one of {', '.join(LANGUAGES)}.")


@lru_cache(maxsize=None)
def field_patterns(language: str = "auto") -> tuple[tuple[str, re.Pattern[str]], ...]:
    validate_language(language)
    selected = FIELD_WORDS.values() if language == "auto" else [FIELD_WORDS[language]]
    words: dict[str, set[str]] = {}
    for vocabulary in selected:
        for label, synonyms in vocabulary.items():
            words.setdefault(label, set()).update(fold(word) for word in synonyms)
    return tuple(
        (label, re.compile(r"(?<!\w)(?:" + "|".join(
            re.escape(word) for word in sorted(synonyms, key=lambda s: (-len(s), s))
        ) + r")(?!\w)"))
        for label, synonyms in words.items()
    )


def labels_in(text: str, language: str = "auto") -> set[str]:
    text = fold(text)
    return {label for label, pattern in field_patterns(language) if pattern.search(text)}


@lru_cache(maxsize=None)
def month_lookup(language: str) -> dict[str, int]:
    validate_language(language)
    selected = MONTH_NAMES.values() if language == "auto" else [MONTH_NAMES.get(language, [])]
    months = {}
    for names in selected:
        for number, name in enumerate(names, start=1):
            months[fold(name)] = number
            months[fold(name[:3])] = number
    if language in {"en", "fr", "es", "auto"}:
        months["sept"] = 9
    return months
