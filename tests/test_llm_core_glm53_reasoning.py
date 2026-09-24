"""GLM-5.3-Flash requires explicit reasoning on OpenRouter / Z.ai."""

from src import llm_core


def test_is_glm53_model_matches_openrouter_slug():
    assert llm_core._is_glm53_model("z-ai/glm-5.3-flash")
    assert llm_core._is_glm53_model("glm-5.3-flash")
    assert not llm_core._is_glm53_model("z-ai/glm-5.2")


def test_apply_glm53_reasoning_openrouter():
    payload = {"model": "z-ai/glm-5.3-flash", "messages": []}
    llm_core._apply_glm53_reasoning_payload(
        payload,
        "https://openrouter.ai/api/v1/chat/completions",
        "z-ai/glm-5.3-flash",
    )
    assert payload["reasoning"] == {"effort": "max", "exclude": False}


def test_apply_glm53_reasoning_zai_direct():
    payload = {"model": "glm-5.3-flash", "messages": []}
    llm_core._apply_glm53_reasoning_payload(
        payload,
        "https://api.z.ai/api/paas/v4/chat/completions",
        "glm-5.3-flash",
        stream=True,
        tools=[{"type": "function", "function": {"name": "ping"}}],
    )
    assert payload["reasoning_effort"] == "max"
    assert payload["thinking"] == {"type": "enabled", "clear_thinking": False}
    assert payload["tool_stream"] is True


def test_apply_glm53_reasoning_skips_unrelated_models():
    payload = {"model": "openai/gpt-oss-120b", "messages": []}
    llm_core._apply_glm53_reasoning_payload(
        payload,
        "https://openrouter.ai/api/v1/chat/completions",
        "openai/gpt-oss-120b",
    )
    assert "reasoning" not in payload
