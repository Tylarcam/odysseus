"""Cloudflare Workers AI vision expects top-level image, not image_url blocks."""

from src import llm_core


def test_adapt_lifts_image_url_to_top_level_field():
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,AAA"},
                },
                {"type": "text", "text": "What color?"},
            ],
        }
    ]
    adapted, image = llm_core._adapt_messages_for_cloudflare_vision(messages)
    assert image == "AAA"
    assert adapted == [{"role": "user", "content": "What color?"}]


def test_apply_cloudflare_vision_payload_sets_image():
    payload = {"model": "m", "messages": []}
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/jpeg;base64,BBB"},
                },
                {"type": "text", "text": "Describe"},
            ],
        }
    ]
    out = llm_core._apply_cloudflare_vision_payload(payload, messages)
    assert payload["image"] == "BBB"
    assert payload["messages"] == out
    assert out[0]["content"] == "Describe"


def test_adapt_passthrough_without_images():
    messages = [{"role": "user", "content": "hi"}]
    adapted, image = llm_core._adapt_messages_for_cloudflare_vision(messages)
    assert image is None
    assert adapted == messages


def test_cloudflare_omitted_from_stream_options_providers():
    """Regression: stream_options makes CF ignore top-level image."""
    # Mirrors the exclusion set in stream_llm
    excluded = {"openrouter", "groq", "cloudflare"}
    assert "cloudflare" in excluded
