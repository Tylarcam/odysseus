# services/transcribe/__init__.py
"""Video transcription service — caption/STT waterfall for agent use."""

from .video_transcriber import transcribe_video_url

__all__ = ["transcribe_video_url"]
