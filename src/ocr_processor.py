"""Helpers for the optional PaddleOCR local text-extraction dependency.

PaddleOCR (Apache-2.0) transcribes text out of an image or scanned document
page entirely offline/on-CPU. It is used as a **fallback ahead of** the
Vision-Language "describe this image" path in src/chat_handler.py and
src/document_processor.py::_process_pdf — for images that are mostly text
(e.g. a photo of handwritten notes), an accurate transcription beats a
paraphrased description, and it doesn't require any VL model to be
configured at all.

Optional: install with `pip install -r requirements-optional.txt`. When
absent, callers degrade gracefully by falling through to the existing
VL-description flow. Mirrors the optional-dependency pattern in
src/markitdown_runtime.py and src/pdf_runtime.py.
"""

import logging
import os

logger = logging.getLogger(__name__)

OCR_MISSING = (
    "Local OCR requires paddlepaddle + paddleocr. Install optional "
    "dependencies with `pip install -r requirements-optional.txt`."
)

# A recognized line below this average confidence, or a result with fewer
# than this many non-whitespace characters, is treated as "not usable" —
# callers fall through to the Vision-Language description path instead of
# trusting a garbled transcription.
OCR_MIN_CONFIDENCE = 0.6
OCR_MIN_CHARS = 3

# One PaddleOCR instance per language — construction loads model weights,
# so callers within the same process reuse it instead of reloading per call.
_ocr_instances: dict[str, "object"] = {}


def load_paddleocr():
    """Return the PaddleOCR class, or raise a user-facing setup hint."""
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(OCR_MISSING) from exc
    return PaddleOCR


def _get_ocr_instance(lang: str):
    """Return a cached PaddleOCR instance for `lang`, constructing it lazily.

    PaddleOCR 3.x (the version that actually resolves on a modern Python /
    numpy>=2 environment — 2.x hard-pins numpy<2.0, which has no Python 3.13
    wheels) is a thin wrapper around the PaddleX inference framework. Its
    constructor dropped the old `use_angle_cls`/`show_log`/`*_model_dir`
    kwargs in favor of `use_textline_orientation` and per-model name/dir
    pairs; model weights are cached via the `PADDLE_PDX_CACHE_HOME` env var
    rather than a constructor argument.
    """
    inst = _ocr_instances.get(lang)
    if inst is not None:
        return inst
    # Must be set before the paddleocr/paddlex import below: paddlex reads
    # this env var once into a module-level constant at import time
    # (paddlex/utils/cache.py), so setting it afterward has no effect.
    from src.constants import OCR_MODELS_DIR
    os.makedirs(OCR_MODELS_DIR, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", OCR_MODELS_DIR)
    PaddleOCR = load_paddleocr()
    inst = PaddleOCR(lang=lang)
    _ocr_instances[lang] = inst
    return inst


def is_ocr_text_usable(result: dict) -> bool:
    """Whether an `analyze_image_with_ocr` result is confident enough to use
    directly, versus falling through to the Vision-Language description."""
    text = (result or {}).get("text") or ""
    if len(text.strip()) < OCR_MIN_CHARS:
        return False
    confidence = (result or {}).get("confidence")
    return confidence is None or confidence >= OCR_MIN_CONFIDENCE


def analyze_image_with_ocr(image_path: str, lang: str = "en") -> dict:
    """Transcribe text out of an image via local PaddleOCR.

    Returns {"text": str, "confidence": float} — text is "" and confidence is
    0.0 when nothing is detected, unavailable, or extraction fails. Never
    raises: callers on the hot chat path must not have a request fail because
    an optional local OCR dependency is missing or errored.
    """
    try:
        ocr = _get_ocr_instance(lang)
    except RuntimeError:
        logger.info("paddleocr not installed; skipping local OCR for %s", image_path)
        return {"text": "", "confidence": 0.0}

    try:
        result = ocr.predict(image_path)
    except Exception as e:
        logger.warning("PaddleOCR failed on %s: %s", image_path, e)
        return {"text": "", "confidence": 0.0}

    page = result[0] if result else None
    if not page:
        return {"text": "", "confidence": 0.0}

    # PaddleOCR 3.x's OCRResult exposes recognized lines as two aligned
    # lists rather than the old [bbox, (text, score)] tuple-per-line shape.
    lines = list(page.get("rec_texts") or [])
    raw_scores = list(page.get("rec_scores") or [])
    scores = [float(s) for s, t in zip(raw_scores, lines) if t]
    lines = [t for t in lines if t]

    text = "\n".join(lines).strip()
    confidence = (sum(scores) / len(scores)) if scores else 0.0
    return {"text": text, "confidence": confidence}
