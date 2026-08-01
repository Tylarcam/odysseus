## 1. Dependency & Runtime Scaffolding

- [x] 1.1 Add `paddlepaddle` (CPU wheel) and `paddleocr` as optional dependencies (e.g. `requirements-optional.txt` or extras group, matching how `markitdown` is handled) — not in the always-installed core requirements.
- [x] 1.2 Create `src/ocr_processor.py` with a `load_paddleocr()` lazy-import helper that raises a friendly `RuntimeError` (mirroring `src/markitdown_runtime.py::load_markitdown`) when the packages aren't installed.
- [x] 1.3 Point PaddleOCR's model-download/cache directory at a repo-local path consistent with existing model-store conventions (check `src/model_discovery.py`) instead of the default `~/.paddleocr/`.
- [x] 1.4 Confirm `paddlepaddle` CPU wheel installs cleanly on this Windows (win_amd64) dev machine; note any install caveats in a short README/comment. — **Verified live** in `venv/` (Python 3.13.14): the originally-pinned `paddlepaddle==2.6.2`/`paddleocr==2.9.1` do **not** install — 2.6.2 has no win_amd64/cp313 wheel, and 2.9.1 hard-pins `numpy<2.0`, which has no Python 3.13 wheels and conflicts with this app's existing numpy>=2 stack. Re-pinned to `paddlepaddle==3.2.2` / `paddleocr==3.7.0`, which install and resolve cleanly (confirmed via a real `pip install`, not a dry run). Discovered along the way and fixed: (a) 3.x's API dropped `use_angle_cls`/`show_log`/`*_model_dir` kwargs and deprecated `.ocr()` in favor of `use_textline_orientation`/`.predict()` with a `rec_texts`/`rec_scores` result shape — `src/ocr_processor.py` and its tests were rewritten to match; (b) the model-cache env var `PADDLE_PDX_CACHE_HOME` is read once at import time by `paddlex/utils/cache.py`, so it must be set *before* `from paddleocr import PaddleOCR`, not after — fixed the ordering in `_get_ocr_instance`. Ran a real end-to-end OCR call against a rendered test image and confirmed correct text extraction and correct model-cache redirection to `data/ocr_models/`. Full test suite run afterward (140+ tests across security/settings/vision/rag) shows no regressions from the numpy 2.4.6→2.3.5 shift.

## 2. OCR Extraction Function

- [x] 2.1 Implement `analyze_image_with_ocr(image_path, lang="en") -> dict` in `src/ocr_processor.py` returning `{"text": str, "confidence": float}` (or empty/None on failure), following the `{"text": ..., "model": ...}` return shape used by `analyze_image_with_vl_result` for consistency.
- [x] 2.2 Decide and implement the "usable text" threshold (length and/or confidence) referenced in design.md's Open Questions.
- [x] 2.3 Ensure all PaddleOCR exceptions are caught internally — this function must never raise into the chat request path.

## 3. Settings

- [x] 3.1 Add `ocr_enabled` (bool, default `True`) and `ocr_lang` (str, default `"en"`) to `src/settings.py` alongside `vision_enabled`/`vision_model`.
- [x] 3.2 Surface both in the existing Settings → Vision UI section (check the settings frontend page that renders `vision_enabled`/`vision_model` today).

## 4. Wire Into Chat Attachment Flow

- [x] 4.1 In `src/chat_handler.py`'s text-only-model branch (~lines 215-239), call `analyze_image_with_ocr` before `analyze_image_with_vl_result` when `ocr_enabled` is true.
- [x] 4.2 On usable OCR text, cache it at `UPLOAD_DIR/.vision/{attachment_id}.txt` (existing cache path) and label it distinctly (e.g. `[OCR text for this image]`) from the VL-description label in the message sent to the model.
- [x] 4.3 On empty/low-confidence/failed OCR, fall through to the existing `analyze_image_with_vl_result` call unchanged.
- [x] 4.4 Verify the existing user-correction path (chat attachment dropdown editing `.vision/{id}.txt`) still takes precedence over fresh OCR/VL output on subsequent turns — no change needed if it already just reads the cache file, but confirm. — Confirmed: the cache-read block runs before the OCR/VL calls and both are gated on `not vl_desc`, unchanged from the original code.

## 5. Wire Into PDF Processing

- [x] 5.1 In `src/document_processor.py::_process_pdf`, replace the direct `analyze_image_with_vl` call on sparse-text image pages with the same OCR-first/VL-fallback helper used in chat (extract a shared helper if the logic is identical, per design.md's reuse decision). — Added `_analyze_image_ocr_then_vl()`.

## 6. Tests

- [x] 6.1 Unit test `analyze_image_with_ocr` against a sample handwritten/printed test image (skip gracefully if `paddleocr` isn't installed in CI, matching how other optional-dependency tests are skipped in this repo). — `tests/test_ocr_processor.py` (mocked-parsing tests always run; one real-image test uses `pytest.importorskip`).
- [x] 6.2 Test `chat_handler.py`'s fallback ordering: OCR success short-circuits before any VL call is attempted (mock/patch both functions). — `tests/test_chat_ocr_fallback.py::test_ocr_success_short_circuits_before_vl_call`.
- [x] 6.3 Test graceful degradation: `paddleocr` import failure results in the existing VL-only behavior with no exception surfaced to the chat response. — `tests/test_ocr_processor.py::test_analyze_returns_empty_when_dependency_missing`; low-confidence/empty-OCR fallthrough covered by `test_chat_ocr_fallback.py::test_low_confidence_ocr_falls_through_to_vl`.
- [x] 6.4 Test `ocr_enabled=false` skips OCR entirely. — `tests/test_chat_ocr_fallback.py::test_ocr_disabled_skips_straight_to_vl` and `tests/test_document_processor_ocr.py::test_ocr_then_vl_skips_ocr_when_disabled`.

All 23 tests across `test_ocr_processor.py`, `test_chat_ocr_fallback.py`, and `test_document_processor_ocr.py` pass, plus no regressions in `test_vision_owner_scope.py`, `test_markitdown_runtime.py`, `test_chat_preprocess_tool_policy.py`, `test_security_regressions.py`, `test_review_regressions.py`, `test_settings_scrub.py`, `test_context_budget.py` (135 passed, 1 skipped).

## 7. Manual Verification

- [ ] 7.1 Attach a real photo of handwritten to-do-list notes in a chat session using a text-only model; confirm the transcribed text appears in the model's context and is reasonably accurate. — **Not done**: requires a running app instance, an installed `paddleocr`, and a real photo; not performed in this session.
- [ ] 7.2 Edit the OCR result via the attachment dropdown and confirm the correction sticks on the next turn. — **Not done**, same reason as 7.1.
- [ ] 7.3 Disable OCR in Settings and confirm the flow falls back to today's VL-description behavior unchanged. — Covered at the code/unit-test level (task 6.4); not verified through the live UI.
