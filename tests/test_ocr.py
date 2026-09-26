import shlex
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pharma_ocr_date_rag import ocr


@pytest.fixture
def backend(monkeypatch):
    class MissingExecutable(OSError):
        pass

    adapter = SimpleNamespace(
        __version__="test-adapter",
        TesseractNotFoundError=MissingExecutable,
        get_tesseract_version=MagicMock(return_value="test-engine"),
        get_languages=MagicMock(return_value=["vie", "eng", "fra"]),
        image_to_string=MagicMock(return_value="Expiry: 14 Apr 2028"),
    )
    image = SimpleNamespace(open=MagicMock())
    monkeypatch.setattr(ocr, "_tesseract_dependencies", lambda: (adapter, image))
    return adapter, image


def test_explicit_packs_settings_and_image_cleanup(backend, tmp_path):
    adapter, image = backend
    directory = tmp_path / "packs with spaces"
    directory.mkdir()
    result = ocr.read_tesseract("page.png", language="eng+fra", psm=6, timeout=7, tessdata_dir=directory)
    assert result.engine == "tesseract" and result.confidence is None
    assert result.text == "Expiry: 14 Apr 2028"
    kwargs = adapter.image_to_string.call_args.kwargs
    assert kwargs["lang"] == "eng+fra" and kwargs["timeout"] == 7
    assert shlex.split(kwargs["config"]) == ["--tessdata-dir", str(directory), "--oem", "1", "--psm", "6"]
    image.open.return_value.__exit__.assert_called_once()


def test_missing_python_dependency(monkeypatch):
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    with pytest.raises(ocr.OCRUnavailable, match="Python adapter"):
        ocr.read_tesseract("page.png")


def test_missing_executable_is_unavailable(backend):
    adapter, image = backend
    adapter.get_tesseract_version.side_effect = adapter.TesseractNotFoundError()
    with pytest.raises(ocr.OCRUnavailable, match="executable is missing"):
        ocr.read_tesseract("page.png")
    image.open.assert_not_called()


def test_missing_pack_does_not_silently_use_english(backend):
    adapter, image = backend
    adapter.get_languages.return_value = ["eng"]
    with pytest.raises(ocr.OCRUnavailable, match="Missing Tesseract language packs: fra"):
        ocr.read_tesseract("page.png", language="eng+fra")
    image.open.assert_not_called()
    adapter.image_to_string.assert_not_called()


def test_missing_pack_directory(backend, tmp_path):
    with pytest.raises(ocr.OCRUnavailable, match="directory does not exist"):
        ocr.read_tesseract("page.png", tessdata_dir=tmp_path / "missing")


def test_environment_failure_is_not_dependency_absence(backend):
    backend[0].get_languages.side_effect = RuntimeError("list-langs failed")
    with pytest.raises(ocr.OCRExecutionError, match="environment check failed"):
        ocr.read_tesseract("page.png")


@pytest.mark.parametrize(
    "error", [RuntimeError("Tesseract process timeout"), RuntimeError("recognizer failed")]
)
def test_execution_failure_closes_image(backend, error):
    adapter, image = backend
    adapter.image_to_string.side_effect = error
    with pytest.raises(ocr.OCRExecutionError, match=str(error)):
        ocr.read_tesseract("page.png")
    image.open.return_value.__exit__.assert_called_once()


def test_bad_image_is_execution_failure(backend):
    backend[1].open.side_effect = OSError("cannot identify image")
    with pytest.raises(ocr.OCRExecutionError, match="cannot identify image"):
        ocr.read_tesseract("broken.png")


@pytest.mark.parametrize(
    "settings",
    [
        {"psm": 0},
        {"psm": 14},
        {"psm": True},
        {"psm": 6.5},
        {"timeout": 0},
        {"timeout": -1},
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"timeout": True},
        {"language": ""},
        {"language": "eng --psm 6"},
        {"language": "eng+"},
    ],
)
def test_invalid_settings_fail_before_optional_import(monkeypatch, settings):
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    with pytest.raises(ValueError):
        ocr.read_tesseract("page.png", **settings)


def test_plain_text_needs_no_optional_dependencies(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pytesseract", None)
    path = tmp_path / "sample.txt"
    path.write_text("Expiry: 14 Apr 2028", encoding="utf-8")
    assert ocr.read_document(path).engine == "plain-text"


def test_auto_falls_back_only_for_unavailability(monkeypatch):
    tesseract = MagicMock(side_effect=ocr.OCRUnavailable("not installed"))
    paddle = MagicMock(return_value=ocr.OCRResult("test", "paddleocr"))
    monkeypatch.setattr(ocr, "read_tesseract", tesseract)
    monkeypatch.setattr(ocr, "_try_paddle", paddle)
    assert ocr.read_document("page.png").engine == "paddleocr"
    paddle.reset_mock()
    tesseract.side_effect = ocr.OCRExecutionError("timeout")
    with pytest.raises(ocr.OCRExecutionError, match="timeout"):
        ocr.read_document("page.png")
    paddle.assert_not_called()


def test_explicit_engine_never_falls_back(monkeypatch):
    monkeypatch.setattr(ocr, "read_tesseract", MagicMock(side_effect=ocr.OCRUnavailable("missing pack")))
    paddle = MagicMock()
    monkeypatch.setattr(ocr, "_try_paddle", paddle)
    with pytest.raises(ocr.OCRUnavailable, match="missing pack"):
        ocr.read_document("page.png", engine="tesseract")
    paddle.assert_not_called()


def test_unknown_engine_rejected():
    with pytest.raises(ValueError, match="Unknown OCR engine"):
        ocr.read_document("page.png", engine="typo")
