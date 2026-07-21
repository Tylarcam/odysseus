from services.stt.stt_service import _audio_suffix, _mime_from_suffix


def test_audio_suffix_from_content_type():
    assert _audio_suffix("audio/mp4", "") == ".mp4"
    assert _audio_suffix("audio/webm;codecs=opus", "") == ".webm"


def test_audio_suffix_from_filename():
    assert _audio_suffix("", "recording.m4a") == ".m4a"
    assert _audio_suffix("application/octet-stream", "clip.mp4") == ".mp4"


def test_mime_from_suffix():
    assert _mime_from_suffix(".mp4") == "audio/mp4"
    assert _mime_from_suffix(".webm") == "audio/webm"
