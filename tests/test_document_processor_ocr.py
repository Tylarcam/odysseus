from src import document_processor as dp


def _settings(overrides):
    def get_setting(key, default=None):
        return overrides.get(key, default)
    return get_setting


def test_ocr_then_vl_uses_ocr_when_usable(monkeypatch):
    monkeypatch.setattr(dp, "get_setting", _settings({"ocr_enabled": True, "ocr_lang": "en"}))
    monkeypatch.setattr(
        "src.ocr_processor.analyze_image_with_ocr",
        lambda path, lang="en": {"text": "Buy milk", "confidence": 0.9},
    )
    monkeypatch.setattr("src.ocr_processor.is_ocr_text_usable", lambda result: True)

    def _fail_vl(*_args, **_kwargs):
        raise AssertionError("VL must not be called when OCR succeeds")

    monkeypatch.setattr(dp, "analyze_image_with_vl", _fail_vl)

    assert dp._analyze_image_ocr_then_vl("page.png") == "Buy milk"


def test_ocr_then_vl_falls_back_when_ocr_unusable(monkeypatch):
    monkeypatch.setattr(dp, "get_setting", _settings({"ocr_enabled": True, "ocr_lang": "en"}))
    monkeypatch.setattr(
        "src.ocr_processor.analyze_image_with_ocr",
        lambda path, lang="en": {"text": "", "confidence": 0.0},
    )
    monkeypatch.setattr("src.ocr_processor.is_ocr_text_usable", lambda result: False)
    monkeypatch.setattr(dp, "analyze_image_with_vl", lambda path, owner=None: "a scanned page")

    assert dp._analyze_image_ocr_then_vl("page.png") == "a scanned page"


def test_ocr_then_vl_skips_ocr_when_disabled(monkeypatch):
    monkeypatch.setattr(dp, "get_setting", _settings({"ocr_enabled": False}))

    def _fail_ocr(*_args, **_kwargs):
        raise AssertionError("OCR must not run when ocr_enabled is False")

    monkeypatch.setattr("src.ocr_processor.analyze_image_with_ocr", _fail_ocr)
    monkeypatch.setattr(dp, "analyze_image_with_vl", lambda path, owner=None: "a scanned page")

    assert dp._analyze_image_ocr_then_vl("page.png") == "a scanned page"
