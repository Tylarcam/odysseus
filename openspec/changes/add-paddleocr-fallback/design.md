## Context

`src/chat_handler.py` and `src/document_processor.py` already have a working vision pipeline:

- `src/chat_helpers.py::model_supports_vision` decides whether the active chat model can natively accept an image.
- When it can't, `chat_handler.py` (~lines 215-239) calls `document_processor.py::analyze_image_with_vl_result`, which resolves a configured (or auto-detected) Vision-Language model — GPT-4o, Claude, Gemini, llava, pixtral, qwen2-vl, etc. — and asks it to "Describe this image in detail." The result is cached at `UPLOAD_DIR/.vision/{attachment_id}.txt` and is overridable by the user via the chat attachment dropdown (a plain editable textarea).
- `document_processor.py::_process_pdf` reuses `analyze_image_with_vl` per-page for image-heavy, text-sparse PDF pages.
- Settings for this live in `src/settings.py` under `vision_enabled` / `vision_model` / `vision_model_fallbacks`, read via `get_setting`/`load_settings`.

This entire path assumes a VL-capable LLM is available and that "describe this image" is an acceptable substitute for the image's content. For the motivating use case — a photo of handwritten to-do-list notes — neither assumption holds well: description prose is lossy for verbatim text, and many local-first setups have no VL model configured at all, producing `"[No vision model configured]"`.

## Goals / Non-Goals

**Goals:**
- Get accurate, verbatim text out of images/scanned-PDF-pages without requiring any LLM call, using PaddleOCR running locally.
- Reuse the existing cache/override plumbing (`.vision/{id}.txt`, attachment dropdown edit) rather than building a parallel system.
- Degrade gracefully to the existing VL-description fallback (and ultimately to today's "no vision model" message) when PaddleOCR isn't installed, its models aren't downloaded, or it finds no text.
- Keep the change additive to `chat_handler.py` / `document_processor.py` — no restructuring of the attachment pipeline.

**Non-Goals:**
- No standalone FastAPI microservice or Docker container for OCR — this stays an in-process Python call, matching how `markitdown`, `pypdf`, and `python-magic` are already used as optional in-process libraries.
- No table-structure extraction, invoice/ID key-value extraction, or per-document-type REST endpoints. Not asked for; the actual use case is single-page handwritten/printed text.
- No GPU inference path. CPU-only PaddleOCR is sufficient for chat-attachment-sized images and avoids a CUDA dependency most deployments (including this Windows dev box) don't have.
- Not replacing the VL-description fallback — OCR and VL description solve different problems (transcription vs. scene description) and both stay available.

## Decisions

**Embedded SDK, not Docker microservice.** The vendor draft proposed a separate containerized OCR worker reachable over HTTP. This app is a single FastAPI process with in-process optional dependencies (`markitdown`, `python-magic`, `pypdf`). Adding a second network hop and a second deployable for one CPU-bound library call is unwarranted complexity — `paddleocr` imports and runs in-process like the others.

**Lazy import, optional dependency.** `paddlepaddle`/`paddleocr` are heavy (the paddlepaddle wheel alone is 100+MB, plus downloaded detection/recognition model weights). Following the `markitdown_runtime.py` pattern (`load_markitdown()` raising a friendly `RuntimeError` when absent), add `src/ocr_processor.py` with a `load_paddleocr()` that imports lazily and raises the same way. The app must start and chat must keep working with the package absent — OCR silently falls through to the existing VL-description path.

**OCR-first, VL-description-fallback, in the existing text-only-model branch.** Rather than adding a separate code path, `chat_handler.py`'s existing `else` branch (main model is text-only) tries OCR first:
1. Run PaddleOCR on the image.
2. If it returns non-trivial text (length/confidence threshold — see Open Questions), use that as the inline caption, tagged `[OCR text for this image]` (distinct label from the existing `[User-corrected caption / OCR for this image]` marker so it's clear which path produced it).
3. If OCR returns nothing usable (blank/low-confidence/exception), fall back to `analyze_image_with_vl_result` exactly as today.

Same caching path (`UPLOAD_DIR/.vision/{id}.txt`) and user-override behavior apply unchanged — the dropdown doesn't need to know whether the cached text came from OCR or a VL model.

**PDF image-pages: reuse the same OCR-first order.** `_process_pdf`'s per-page-image loop swaps its direct `analyze_image_with_vl` call for the same OCR-then-VL-fallback helper, so scanned PDF pages get the same accuracy improvement.

**Model store location.** PaddleOCR downloads its detection/recognition/classification models on first use. Point it at a repo-local cache dir (`src/constants.py::OCR_MODELS_DIR = DATA_DIR/ocr_models`, matching the existing `RAG_DIR`/`CHROMA_DIR`/`FASTEMBED_CACHE_DIR` convention) instead of its default `~/.paddlex/official_models/`, via the `PADDLE_PDX_CACHE_HOME` env var. **Verified live**: this env var is read once into a module-level constant at `paddlex/utils/cache.py` import time, so it must be set *before* `from paddleocr import PaddleOCR` runs, not after — `_get_ocr_instance` sets it first.

**Settings surface.** Add `ocr_enabled` (bool, default `True`) and `ocr_lang` (str, default `"en"`) next to the existing `vision_enabled`/`vision_model` keys in `src/settings.py`, surfaced in the same Settings → Vision UI section — not a new settings page.

**Actual installed version: paddleocr 3.7.0, not 2.9.1 as originally planned.** A real `pip install` against this dev machine's Python 3.13 venv showed the originally-targeted `paddlepaddle==2.6.2`/`paddleocr==2.9.1` don't install at all: 2.6.2 has no win_amd64 wheel for cp313, and 2.9.1 hard-pins `numpy<2.0`, which has no Python 3.13 wheel and conflicts with numpy>=2 already required elsewhere in this app's stack (fastembed/chromadb). `paddleocr==3.7.0` resolves cleanly against numpy 2.x instead. Its API changed substantially from the 2.x line this design was originally written against:
- Constructor kwargs `use_angle_cls` / `show_log` / `det_model_dir` / `rec_model_dir` / `cls_model_dir` are gone, replaced by `use_textline_orientation` and per-model `*_model_name`/`*_model_dir` pairs (left at their defaults here — no per-model override needed).
- `.ocr()` is now a deprecated shim over `.predict()`; the result shape changed from a list of `[bbox, (text, score)]` tuples per line to a dict-like `OCRResult` per page exposing aligned `rec_texts: list[str]` / `rec_scores: list[float]`.
`src/ocr_processor.py` targets `.predict()` and the `rec_texts`/`rec_scores` shape directly.

## Risks / Trade-offs

- **[Risk]** `paddlepaddle` install friction on Windows (the dev machine here) or ARM64 Macs → **Mitigation**: document the correct CPU wheel per platform in requirements notes; keep the import fully lazy so a failed/skipped install never breaks the rest of the app, only disables this one fallback.
- **[Risk]** First real "offline" use still needs one-time network access to download model weights → **Mitigation**: call this out explicitly in proposal/docs; this matches the vendor draft's own caveat, not a regression.
- **[Risk]** OCR is poor at very messy handwriting and could return garbled text that looks confident → **Mitigation**: surface OCR output through the same editable attachment-dropdown textarea that already exists for VL captions, so a bad transcription is a one-click user correction, not a silent wrong answer baked into the conversation.
- **[Risk]** Added heavy dependency increases install size/time for everyone even if few use OCR, and is heavier than originally scoped → **Mitigation**: strictly optional/lazy-loaded, not in core `requirements.txt`'s always-installed set (mirrors how `markitdown` is handled). **Confirmed heavier than planned**: `paddleocr>=3.x` now wraps the PaddleX inference framework and pulls in `paddlex`, `modelscope`, `pandas`, `aiohttp`, and friends — roughly 150MB+ of additional packages beyond `paddlepaddle` itself, not just the lean `opencv`+`shapely`+`pyclipper` footprint the 2.x line had. Still fully optional/lazy, but worth knowing before installing on a constrained deployment.
- **[Risk]** `paddleocr==3.7.0` downgraded the already-installed `numpy` (2.4.6→2.3.5) and `PyYAML` (6.0.3→6.0.2) in this venv to satisfy its pin → **Mitigation checked**: ran the full test suite before and after: no regressions attributable to this shift (the ~79 pre-existing failures on this branch — Node/ESM-on-Windows JS-shim tests, macOS/WSL-only tests, and a couple of unrelated pre-existing app bugs — are identical with or without this change, confirmed via `git stash`/`git stash pop` diffing).
- **[Trade-off]** Running both OCR and, on OCR failure, a VL call is slower in the worst case than VL-only — acceptable since OCR is the fast path and only falls through to the existing (already-accepted) latency on failure.

## Migration Plan

1. Add `src/ocr_processor.py` behind lazy import; no behavior change until wired in.
2. Wire OCR-first into `chat_handler.py`'s existing text-only-model branch and `document_processor.py::_process_pdf`, guarded by `ocr_enabled` setting (default on, but a no-op if the package isn't installed).
3. Add settings keys with safe defaults so existing installs without the package see zero behavior change beyond "OCR attempted, fell through to VL as before."
4. No data migration needed — reuses the existing `.vision/{id}.txt` cache format.
5. Rollback: set `ocr_enabled=false` or uninstall the package; behavior reverts exactly to today's VL-description-only fallback.

## Open Questions

- Should OCR text and a short VL description ever be combined (e.g., "photo of a notebook page, OCR: ...") for non-text images the user tags as images-of-text incorrectly, or is falling through to VL-only sufficient? (Left as VL-only fallback for now — no reported need for the combined case.)

Resolved during implementation (see Decisions): confidence/length threshold is `OCR_MIN_CONFIDENCE = 0.6` / `OCR_MIN_CHARS = 3` in `src/ocr_processor.py`; model-store path is `src/constants.py::OCR_MODELS_DIR`.
