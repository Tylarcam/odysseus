# services/stt/stt_service.py
"""Multi-provider Speech-to-Text service — dispatches to local Whisper, OpenAI-compatible API, or browser."""

import io
import logging
import os
import re
import shutil
import httpx
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Persistent Whisper weights use the HuggingFace hub cache bind-mount
# (docker-compose: ./data/huggingface → /app/.cache/huggingface).
# Do not set a separate download_root — that would re-download beside the
# existing hub/models--Systran--faster-whisper-* trees.
_LANG_RE = re.compile(r"^[a-zA-Z]{2,3}(?:-[a-zA-Z]{2,8})?$")

_AUDIO_SUFFIX_BY_TYPE = {
    "audio/webm": ".webm",
    "audio/mp4": ".mp4",
    "audio/m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/ogg": ".ogg",
    "audio/aac": ".aac",
}


def _audio_suffix(content_type: str = "", filename: str = "") -> str:
    ct = (content_type or "").lower().split(";", 1)[0].strip()
    if ct in _AUDIO_SUFFIX_BY_TYPE:
        return _AUDIO_SUFFIX_BY_TYPE[ct]
    if filename:
        ext = Path(filename).suffix.lower()
        if ext in {".webm", ".mp4", ".m4a", ".mp3", ".wav", ".ogg", ".aac"}:
            return ext
    return ".webm"


def _mime_from_suffix(suffix: str) -> str:
    for mime, ext in _AUDIO_SUFFIX_BY_TYPE.items():
        if ext == suffix:
            return mime
    return "audio/webm"


def _normalize_stt_language(language: str) -> str:
    """Whisper only accepts ISO language codes — drop UI garbage (e.g. #ffffff)."""
    lang = (language or "").strip()
    if not lang or lang.startswith("#"):
        return ""
    if not _LANG_RE.fullmatch(lang):
        return ""
    return lang.split("-", 1)[0].lower()


def _whisper_cache_path() -> str:
    """Where faster-whisper / HF hub stores Systran faster-whisper-* weights."""
    hf_home = (os.environ.get("HF_HOME") or "").strip()
    if hf_home:
        return str(Path(hf_home) / "hub")
    for candidate in (
        Path("/app/.cache/huggingface/hub"),
        Path.home() / ".cache" / "huggingface" / "hub",
    ):
        if candidate.exists():
            return str(candidate)
    return str(Path.home() / ".cache" / "huggingface" / "hub")


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


class STTService:
    """Multi-provider STT service.

    Reads provider config from data/settings.json on each call.
    Providers:
      "disabled"        — no STT
      "browser"         — client-side Web Speech API (no server transcription)
      "local"           — faster-whisper on CPU/GPU
      "endpoint:<id>"   — OpenAI-compatible /audio/transcriptions via ModelEndpoint
    """

    def __init__(self):
        self._whisper_model = None  # lazy-init
        self._local_status = "not_loaded"  # not_loaded | loaded | missing_package | load_failed
        self._local_reason = ""
        self._local_detail = ""

    # ── Settings ──

    def _load_settings(self) -> dict:
        from src.settings import load_settings
        saved = load_settings()
        return {
            "stt_enabled": saved.get("stt_enabled", False),
            "stt_provider": saved.get("stt_provider", "disabled"),
            "stt_model": saved.get("stt_model", "base"),
            "stt_language": saved.get("stt_language", ""),
        }

    @property
    def available(self) -> bool:
        settings = self._load_settings()
        if settings.get("stt_enabled") is False:
            return False
        provider = settings["stt_provider"]
        if provider == "disabled":
            return False
        if provider == "browser":
            return True  # handled client-side
        if provider == "local":
            return self._get_whisper() is not None
        if provider.startswith("endpoint:"):
            return True  # assume reachable
        return False

    # ── Local Whisper ──

    def _set_local_status(self, status: str, reason: str = "", detail: str = "") -> None:
        self._local_status = status
        self._local_reason = reason
        self._local_detail = detail

    def _get_whisper(self):
        if self._whisper_model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                logger.warning("faster-whisper not installed. Install with: pip install faster-whisper")
                self._set_local_status(
                    "missing_package",
                    "missing_package",
                    "faster-whisper is not installed on the server",
                )
                return None
            try:
                settings = self._load_settings()
                model_size = settings.get("stt_model", "base")
                # faster-whisper runs on CTranslate2, not torch. torch is only
                # used (optionally) to detect a CUDA device for acceleration —
                # if it's missing or unusable we just run on CPU. Keeping this
                # probe separate (and tolerant of any failure, e.g. a broken
                # CUDA/torch install that raises OSError on import) means a
                # torch-less or torch-broken machine still does CPU
                # transcription instead of failing with a misleading
                # "faster-whisper not installed" error.
                try:
                    import torch
                    use_cuda = torch.cuda.is_available()
                except Exception:
                    use_cuda = False
                device = "cuda" if use_cuda else "cpu"
                compute_type = "float16" if device == "cuda" else "int8"
                cache_path = _whisper_cache_path()
                self._whisper_model = WhisperModel(
                    model_size,
                    device=device,
                    compute_type=compute_type,
                )
                logger.info(
                    "faster-whisper model '%s' loaded on %s (cache=%s)",
                    model_size,
                    device,
                    cache_path,
                )
                detail = f"model '{model_size}' on {device}; cache={cache_path}"
                if not _ffmpeg_available():
                    detail += "; WARNING: ffmpeg missing (webm mic takes will fail)"
                self._set_local_status("loaded", "loaded", detail)
            except Exception as e:
                logger.error(f"Failed to load whisper model: {e}")
                self._set_local_status("load_failed", "load_failed", str(e))
                return None
        return self._whisper_model

    def _transcribe_local(
        self,
        audio_bytes: bytes,
        language: str = "",
        content_type: str = "",
        filename: str = "",
    ) -> Optional[str]:
        model = self._get_whisper()
        if not model:
            return None
        tmp_path = None
        suffix = _audio_suffix(content_type, filename)
        # Browser MediaRecorder usually sends webm/ogg — needs ffmpeg.
        if suffix in {".webm", ".ogg", ".mp4", ".m4a", ".aac"} and not _ffmpeg_available():
            logger.error(
                "Local STT needs ffmpeg to decode %s (browser mic format). "
                "Install ffmpeg in the image/host, or use streaming STT (PCM/WAV).",
                suffix,
            )
            self._set_local_status(
                "loaded",
                "ffmpeg_missing",
                f"ffmpeg required to decode {suffix}; install ffmpeg or use stream STT",
            )
            return None
        try:
            # Write to temp file (faster-whisper needs a file path or file-like)
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name

            kwargs = {}
            lang = _normalize_stt_language(language)
            if lang:
                kwargs["language"] = lang

            segments, info = model.transcribe(tmp_path, **kwargs)
            text = " ".join(seg.text.strip() for seg in segments)

            logger.info(f"Local STT: {len(text)} chars, lang={info.language}, prob={info.language_probability:.2f}")
            return text
        except Exception as e:
            logger.error(f"Local STT transcription failed: {e}", exc_info=True)
            return None
        finally:
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

    # ── API endpoint ──

    def _transcribe_api(
        self,
        audio_bytes: bytes,
        endpoint_id: str,
        model: str,
        language: str = "",
        content_type: str = "",
        filename: str = "",
    ) -> Optional[str]:
        from src.database import SessionLocal, ModelEndpoint

        db = SessionLocal()
        try:
            ep = db.query(ModelEndpoint).filter(ModelEndpoint.id == endpoint_id).first()
            if not ep:
                logger.error(f"STT endpoint {endpoint_id} not found")
                return None
            base_url = ep.base_url.rstrip("/")
            api_key = ep.api_key
        finally:
            db.close()

        url = base_url + "/audio/transcriptions"
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        suffix = _audio_suffix(content_type, filename)
        upload_name = filename or f"audio{suffix}"
        upload_type = content_type or _mime_from_suffix(suffix)
        files = {"file": (upload_name, io.BytesIO(audio_bytes), upload_type)}
        data = {"model": model or "whisper-1"}
        if language:
            data["language"] = language

        try:
            r = httpx.post(url, headers=headers, files=files, data=data, timeout=60)
            r.raise_for_status()
            result = r.json()
            text = result.get("text", "")
            logger.info(f"API STT: {len(text)} chars from {base_url}")
            return text
        except Exception as e:
            logger.error(f"API STT transcription failed: {e}")
            return None

    # ── Public interface ──

    def transcribe(
        self,
        audio_bytes: bytes,
        content_type: str = "",
        filename: str = "",
    ) -> Optional[str]:
        settings = self._load_settings()
        if settings.get("stt_enabled") is False:
            return None
        provider = settings["stt_provider"]
        model = settings["stt_model"]
        language = _normalize_stt_language(settings.get("stt_language", ""))

        if provider in ("disabled", "browser"):
            return None

        if provider == "local":
            return self._transcribe_local(audio_bytes, language, content_type, filename)
        elif provider.startswith("endpoint:"):
            endpoint_id = provider.split(":", 1)[1]
            return self._transcribe_api(audio_bytes, endpoint_id, model, language, content_type, filename)
        else:
            logger.error(f"Unknown STT provider: {provider}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        settings = self._load_settings()
        provider = settings["stt_provider"]
        stt_enabled = settings.get("stt_enabled", False)
        # If toggle is off, report as disabled
        effective_provider = provider if stt_enabled else "disabled"

        stats = {
            "enabled": stt_enabled,
            "available": self.available and stt_enabled,
            "provider": effective_provider,
            "model": settings["stt_model"],
            "language": settings.get("stt_language", ""),
        }

        if provider == "local":
            whisper = self._get_whisper()
            stats["model_loaded"] = whisper is not None
            stats["local_status"] = self._local_status
            stats["ffmpeg"] = _ffmpeg_available()
            stats["whisper_cache"] = _whisper_cache_path()
            if self._local_reason:
                stats["reason"] = self._local_reason
            if self._local_detail:
                stats["local_detail"] = self._local_detail
            if not stats["ffmpeg"]:
                stats["hint"] = (
                    "ffmpeg is missing — browser mic (webm) cannot be decoded. "
                    "Rebuild the Docker image (Dockerfile installs ffmpeg) or "
                    "apt-get install ffmpeg inside the container."
                )
        elif provider == "browser":
            stats["model"] = "Browser (Web Speech API)"
        elif provider.startswith("endpoint:"):
            stats["endpoint_id"] = provider.split(":", 1)[1]

        return stats


# Module-level singleton
_stt_service = None

def get_stt_service() -> STTService:
    global _stt_service
    if _stt_service is None:
        _stt_service = STTService()
    return _stt_service
