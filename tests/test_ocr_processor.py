import builtins

import pytest

from src.ocr_processor import (
    OCR_MISSING,
    OCR_MIN_CHARS,
    OCR_MIN_CONFIDENCE,
    analyze_image_with_ocr,
    is_ocr_text_usable,
    load_paddleocr,
)


def _block_paddleocr_import(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "paddleocr":
            raise ImportError("No module named paddleocr")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_missing_dependency_error_is_user_actionable(monkeypatch):
    _block_paddleocr_import(monkeypatch)

    with pytest.raises(RuntimeError) as exc:
        load_paddleocr()

    message = str(exc.value)
    assert message == OCR_MISSING
    assert "requirements-optional.txt" in message


def test_analyze_returns_empty_when_dependency_missing(monkeypatch):
    _block_paddleocr_import(monkeypatch)
    result = analyze_image_with_ocr("whatever.png")
    assert result == {"text": "", "confidence": 0.0}


def test_analyze_returns_empty_on_ocr_exception(monkeypatch):
    class BoomOcr:
        def predict(self, path):
            raise ValueError("bad file")

    monkeypatch.setattr("src.ocr_processor._get_ocr_instance", lambda lang: BoomOcr())
    result = analyze_image_with_ocr("whatever.png")
    assert result == {"text": "", "confidence": 0.0}


def test_analyze_parses_lines_and_averages_confidence(monkeypatch):
    # Shape matches paddleocr>=3.x's OCRResult: predict() returns a list of
    # dict-like pages with aligned rec_texts/rec_scores lists (not the old
    # 2.x [bbox, (text, score)]-per-line shape from the deprecated .ocr()).
    class FakeOcr:
        def predict(self, path):
            return [{"rec_texts": ["Buy milk", "Call dentist"], "rec_scores": [0.95, 0.85]}]

    monkeypatch.setattr("src.ocr_processor._get_ocr_instance", lambda lang: FakeOcr())
    result = analyze_image_with_ocr("notes.png")
    assert result["text"] == "Buy milk\nCall dentist"
    assert result["confidence"] == pytest.approx(0.90)


def test_analyze_handles_no_detected_text(monkeypatch):
    class EmptyOcr:
        def predict(self, path):
            return [{"rec_texts": [], "rec_scores": []}]

    monkeypatch.setattr("src.ocr_processor._get_ocr_instance", lambda lang: EmptyOcr())
    result = analyze_image_with_ocr("blank.png")
    assert result == {"text": "", "confidence": 0.0}


def test_is_ocr_text_usable_requires_min_length_and_confidence():
    assert is_ocr_text_usable({"text": "Buy milk", "confidence": 0.9})
    assert not is_ocr_text_usable({"text": "", "confidence": 0.9})
    assert not is_ocr_text_usable({"text": "ab", "confidence": 0.9})  # below OCR_MIN_CHARS
    assert not is_ocr_text_usable({"text": "Buy milk", "confidence": 0.1})  # below OCR_MIN_CONFIDENCE
    assert is_ocr_text_usable({"text": "Buy milk"})  # confidence absent -> treated as usable


def test_thresholds_are_sane():
    assert 0 < OCR_MIN_CONFIDENCE <= 1
    assert OCR_MIN_CHARS >= 1


def test_ocr_end_to_end_with_real_image(tmp_path):
    """Optional integration check: skipped unless paddleocr is actually installed."""
    pytest.importorskip("paddleocr")
    PIL_Image = pytest.importorskip("PIL.Image")

    img = PIL_Image.new("RGB", (200, 60), color="white")
    path = tmp_path / "sample.png"
    img.save(str(path))

    # A blank image should yield no usable text, not an exception.
    result = analyze_image_with_ocr(str(path))
    assert result["text"] == ""
