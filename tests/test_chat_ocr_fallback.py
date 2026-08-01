from types import SimpleNamespace

import pytest

from src.chat_handler import ChatHandler


class _FakeUploadHandler:
    def __init__(self, file_info):
        self._file_info = file_info

    def resolve_upload(self, att_id, owner=None):
        return dict(self._file_info)

    def is_image_file(self, name, mime):
        return True

    def _inside_upload_dir(self, path):
        return True


def _settings(overrides):
    def get_setting(key, default=None):
        return overrides.get(key, default)
    return get_setting


def _make_handler(upload_handler):
    return ChatHandler(
        session_manager=None,
        memory_manager=None,
        chat_processor=None,
        research_handler=None,
        preset_manager=None,
        upload_handler=upload_handler,
    )


@pytest.fixture
def image_file(tmp_path):
    path = tmp_path / "notes.png"
    path.write_bytes(b"not-a-real-png-but-good-enough-for-this-test")
    return {"id": "att1", "path": str(path), "mime": "image/png", "name": "notes.png"}


@pytest.mark.asyncio
async def test_ocr_success_short_circuits_before_vl_call(monkeypatch, image_file, tmp_path):
    monkeypatch.setattr("src.chat_handler.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("src.chat_handler.model_supports_vision", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        "src.settings.get_setting",
        _settings({"vision_enabled": True, "vision_model": "", "ocr_enabled": True, "ocr_lang": "en"}),
    )
    monkeypatch.setattr(
        "src.ocr_processor.analyze_image_with_ocr",
        lambda path, lang="en": {"text": "Buy milk\nCall dentist", "confidence": 0.9},
    )
    monkeypatch.setattr("src.ocr_processor.is_ocr_text_usable", lambda result: True)

    def _fail_vl(*_args, **_kwargs):
        raise AssertionError("VL description must not be called when OCR succeeds")

    monkeypatch.setattr("src.chat_handler.analyze_image_with_vl_result", _fail_vl)

    handler = _make_handler(_FakeUploadHandler(image_file))
    sess = SimpleNamespace(model="text-only", endpoint_url="", owner="user", id="session")

    enhanced, _user_content, _text_ctx, _youtube, attachment_meta = await handler.preprocess_message(
        "Here are my to-do notes",
        ["att1"],
        sess,
        auto_opened_docs=[],
        allow_tool_preprocessing=True,
    )

    assert "[OCR text for image: notes.png]" in enhanced
    assert "Buy milk\nCall dentist" in enhanced
    assert attachment_meta[0]["vision_model"] == "paddleocr"


@pytest.mark.asyncio
async def test_low_confidence_ocr_falls_through_to_vl(monkeypatch, image_file, tmp_path):
    monkeypatch.setattr("src.chat_handler.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("src.chat_handler.model_supports_vision", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        "src.settings.get_setting",
        _settings({"vision_enabled": True, "vision_model": "", "ocr_enabled": True, "ocr_lang": "en"}),
    )
    monkeypatch.setattr(
        "src.ocr_processor.analyze_image_with_ocr",
        lambda path, lang="en": {"text": "", "confidence": 0.0},
    )
    monkeypatch.setattr("src.ocr_processor.is_ocr_text_usable", lambda result: False)
    monkeypatch.setattr(
        "src.chat_handler.analyze_image_with_vl_result",
        lambda path, owner=None: {"text": "a photo of a notebook page", "model": "gpt-4o"},
    )

    handler = _make_handler(_FakeUploadHandler(image_file))
    sess = SimpleNamespace(model="text-only", endpoint_url="", owner="user", id="session")

    enhanced, _user_content, _text_ctx, _youtube, attachment_meta = await handler.preprocess_message(
        "Here are my to-do notes",
        ["att1"],
        sess,
        auto_opened_docs=[],
        allow_tool_preprocessing=True,
    )

    assert "[Image: notes.png]" in enhanced
    assert "a photo of a notebook page" in enhanced
    assert attachment_meta[0]["vision_model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_ocr_disabled_skips_straight_to_vl(monkeypatch, image_file, tmp_path):
    monkeypatch.setattr("src.chat_handler.UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr("src.chat_handler.model_supports_vision", lambda *_a, **_kw: False)
    monkeypatch.setattr(
        "src.settings.get_setting",
        _settings({"vision_enabled": True, "vision_model": "", "ocr_enabled": False, "ocr_lang": "en"}),
    )

    def _fail_ocr(*_args, **_kwargs):
        raise AssertionError("OCR must not run when ocr_enabled is False")

    monkeypatch.setattr("src.ocr_processor.analyze_image_with_ocr", _fail_ocr)
    monkeypatch.setattr(
        "src.chat_handler.analyze_image_with_vl_result",
        lambda path, owner=None: {"text": "a photo of a notebook page", "model": "gpt-4o"},
    )

    handler = _make_handler(_FakeUploadHandler(image_file))
    sess = SimpleNamespace(model="text-only", endpoint_url="", owner="user", id="session")

    enhanced, _user_content, _text_ctx, _youtube, _attachment_meta = await handler.preprocess_message(
        "Here are my to-do notes",
        ["att1"],
        sess,
        auto_opened_docs=[],
        allow_tool_preprocessing=True,
    )

    assert "[Image: notes.png]" in enhanced
    assert "a photo of a notebook page" in enhanced
