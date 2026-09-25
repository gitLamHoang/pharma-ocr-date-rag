"""Explicit per-document date conventions; never infer an order from language."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

from .dates import DATE_ORDERS


def _unique_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate document name in date-order map: {key}")
        result[key] = value
    return result


def _validate_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise ValueError("Date-order map must be an object mapping filenames to auto, dmy or mdy")
    result = {}
    for name, order in value.items():
        if not isinstance(name, str) or not name or name in {".", ".."} or any(c in name for c in "/\\"):
            raise ValueError("Date-order map keys must be exact filenames, not paths or patterns")
        if not isinstance(order, str) or order not in DATE_ORDERS:
            raise ValueError(f"Unsupported date order for {name}: {order!r}")
        result[name] = order
    return result


def load_date_order_map(path: str | Path) -> dict[str, str]:
    """Reject malformed maps and duplicate keys rather than silently choosing a policy."""
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_keys)
    return _validate_map(value)


def resolve_date_orders(
    paths: Sequence[Path], default: str = "auto", overrides: Mapping[str, str] | None = None
) -> dict[str, str]:
    if default not in DATE_ORDERS:
        raise ValueError(f"Unsupported date order: {default}")
    explicit = _validate_map(overrides if overrides is not None else {})
    names = {path.name for path in paths}
    unknown = set(explicit) - names
    if unknown:
        raise ValueError(
            "Date-order map refers to missing or unsupported documents: " + ", ".join(sorted(unknown))
        )
    return {name: explicit.get(name, default) for name in names}
