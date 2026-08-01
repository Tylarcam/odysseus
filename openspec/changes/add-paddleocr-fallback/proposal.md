## Why

When the active chat model can't natively see images (`model_supports_vision` returns `False`), `src/chat_handler.py` currently falls back to asking a separately-configured Vision-Language model to "describe this image in detail" (`analyze_image_with_vl_result` in `src/document_processor.py`). That works for general photos, but it's the wrong tool for the user's actual case — a photo of handwritten to-do-list notes. Description prompts paraphrase and drop details rather than transcribing verbatim, and the fallback goes dark entirely ("[No vision model configured]" / "[VL model unavailable]") for anyone who hasn't set up a paid or local VL model. A dedicated, offline OCR pass gets exact text out of the image without depending on any LLM being available, so every chat model — vision-capable or not — can work from an accurate transcription of what was written.

## What Changes

- Add a PaddleOCR-backed text-extraction step (`src/ocr_processor.py`) that runs locally, offline, with no cloud dependency.
- In `src/chat_handler.py`'s existing text-only-model branch (around `chat_handler.py:215-239`), try OCR transcription before falling back to the VL-description call; if OCR yields confident text, use it as the inline caption instead of (or alongside) the VL description.
- Reuse the same OCR step in `src/document_processor.py::_process_pdf` for image-heavy PDF pages, as a faster/free alternative to invoking a VL model per page.
- Add a `Settings → Vision` toggle (`ocr_enabled`, default on) and an optional `ocr_lang` field, following the existing `vision_enabled` / `vision_model` settings pattern in `src/settings.py`.
- Cache OCR output the same way VL captions are cached today, at `UPLOAD_DIR/.vision/{attachment_id}.txt`, so a user's manual correction via the chat attachment dropdown still overrides it.
- Add `paddlepaddle` + `paddleocr` as optional dependencies, loaded lazily (import-on-first-use, like the existing `markitdown` / `python-magic` optional-dependency pattern) so the app still runs if the packages or their model weights aren't installed.

Explicitly **not** doing (out of scope vs. the pasted vendor draft): no separate FastAPI ingestion microservice, no Docker container, no table/invoice/ID extraction pipeline, no per-document-type REST endpoints. This app is a single Python monolith with an existing attachment/vision pipeline — the draft's clean-slate microservice architecture doesn't fit and isn't needed for the stated use case.

## Capabilities

### New Capabilities
- `ocr-text-extraction`: Local/offline OCR (PaddleOCR) that turns an uploaded image or scanned PDF page into transcribed text, used as a fallback/enhancement wherever the app currently asks a VL model to describe an image instead of transcribing it.

### Modified Capabilities
(none — no existing archived specs cover the vision-fallback behavior yet; it lives only in application code)

## Impact

- **Affected code**: `src/chat_handler.py` (text-only-model attachment branch), `src/document_processor.py` (`_process_pdf`, new `analyze_image_with_ocr` alongside `analyze_image_with_vl_result`), `src/settings.py` (new settings keys), `static/js/` attachment dropdown (surface "OCR" alongside existing caption text, no behavior change needed if it already just edits the cached `.txt`).
- **New dependency**: `paddlepaddle` (CPU wheel) + `paddleocr`, plus their downloaded model weights (~10-100MB depending on model) cached under a local model-store directory on first use. Import must be lazy/optional per repo convention — do not add to hard startup requirements.
- **Platform note**: dev machine is Windows (win32); use the `paddlepaddle` CPU wheel for `win_amd64`, not the vendor draft's macOS ARM64 guidance.
- **No API surface change**: this is an internal fallback path, not a new user-facing endpoint.
