# A2 Authority Digest

**Scrape method:** Firecrawl MCP (user-firecrawl-mcp) — available and used for all primary sources. OpenAI docs redirect to `developers.openai.com`. Pipecat `getting-started/overview` 404'd; substituted `overview/introduction` and `pipecat/get-started/introduction`. Perplexity homepage is marketing shell only (no voice architecture detail).

---

## OpenAI Realtime / STT / TTS

### Architecture fork (authoritative)

OpenAI explicitly splits voice into **live sessions** vs **request-based APIs**:

| Goal | Path | Endpoint / model |
|------|------|------------------|
| Low-latency voice agent (listen, reason, speak, tools) | Speech-to-speech Realtime | `gpt-realtime-2.1` on `/v1/realtime` |
| Live transcript only (no spoken reply) | Transcription session | `gpt-realtime-whisper` |
| File / bounded audio | Batch STT | `/v1/audio/transcriptions` |
| Generate speech from text | TTS | `/v1/audio/speech` (`gpt-4o-mini-tts`) |

**Speech-to-speech path:** Browser/server opens persistent Realtime session (WebRTC for browser, WebSocket for server pipelines). VAD enabled by default. Model handles audio turns, tool calls, interruptions inside one session. Agents SDK: `RealtimeAgent` + `RealtimeSession` with ephemeral `client_secrets`.

**Cascaded path (Python Agents SDK):** Explicit `VoicePipeline` = STT → text agent (LLM + tools) → TTS. Best when you need durable transcripts, policy gates between stages, or reuse of existing text agents.

### Canonical pipeline (Realtime)

```
mic → [WebRTC/WS audio in]
    → VAD (server_vad | semantic_vad)
    → speech_started / speech_stopped events
    → (optional) input transcription deltas
    → model turn + response.output_audio.delta
    → playback
    ← barge-in: interrupt_response + cancel in-flight TTS
```

**VAD modes** (`session.audio.input.turn_detection`):
- `server_vad`: silence-based chunking; tunable `threshold`, `prefix_padding_ms`, `silence_duration_ms`.
- `semantic_vad`: utterance completion from meaning; `eagerness` low/medium/high/auto.
- Conversation-only flags: `create_response`, `interrupt_response` (enable barge-in).

**Turn / partials (STT guide):**
- **Completed recording + own turn detection:** `transcriptions.create(..., stream=True)` → `transcript.text.delta` then `transcript.text.done`.
- **Live mic:** use Realtime transcription session, not file streaming API.
- **Partials vs finals:** streaming STT emits partials for UI; only **final** transcripts should trigger LLM (Deepgram/LiveKit pattern echoed in Salesforce tutorial via `is_final` / `speech_final`).
- **Empty / low-confidence:** guard before `response.create`; Whisper prompt limited to 224 tokens; diarization requires `chunking_strategy` for audio >30s.

**TTS streaming:** `speech.create` with chunk transfer encoding; prefer `wav` or `pcm` for lowest latency. Realtime API has separate voice set from standalone TTS.

**Tools without double latency:**
- **Native Realtime:** Register `function` tools on session; on `function_call`, app executes and returns `function_call_output` + `response.create`. MCP tools run **inside** Realtime API (client listens, does not round-trip tool execution). Session-level vs response-level tool scoping.
- **Chained pipeline:** Tools live in text LLM; voice adds one STT+TTS wrap — tool latency is additive unless you use async tools / preambles ("let me check that") while tool runs.
- **Bridge pattern:** Keep tool orchestration in text layer; Realtime session only for low-latency audio UX, or use MCP so model doesn't wait on your client for remote tools.

---

## Whisper / faster-whisper

### OpenAI Whisper (reference impl)

- **Batch-only** in open-source: `transcribe()` reads full file, **30-second sliding windows**, autoregressive decode per window.
- Multitask seq2seq replaces traditional pipeline (ASR + VAD + language ID in one model).
- **Not streaming-native**; production live agents use API Realtime transcription or external streaming wrappers (WhisperLive, whisper_streaming).
- `turbo` model: fast English ASR, **not** for translation.

### faster-whisper (production self-host)

- CTranslate2 reimplementation; **4× faster**, lower memory; optional int8.
- **Batch:** `model.transcribe()` returns segment **generator** (lazy until iterated).
- **BatchedInferencePipeline:** `batch_size=16` for offline throughput (not live turn-taking).
- **Built-in Silero VAD:** `vad_filter=True`; strips silence >2s default; tunable `vad_parameters` (telephony-sensitive).
- Community streaming: Whisper-Streaming (self-adaptive latency), WhisperLive, speaches (OpenAI-compatible server).
- **Production wiring:** mic → external VAD/endpointing → buffer utterance → faster-whisper segment OR streaming wrapper → text LLM. Do not feed partial 30s windows to LLM without endpointing.

---

## LiveKit / Pipecat / agent frameworks

### LiveKit Agents

- Agent = **stateful WebRTC bridge** between user and AI stack; HTTP/WS to backend models.
- Explicit **STT → LLM → TTS pipeline** with plugins for 100+ providers.
- Built-ins: **turn detection model**, interruption handling, tool use (forward to frontend possible), multi-agent handoff.
- Transport: WebRTC user ↔ agent; agent server dispatches jobs per room.
- Target: **<1s** perceived latency with streaming at all stages (LiveKit blog: transport <50ms, STT partial 100–200ms, LLM TTFT 200–400ms, TTS TTFB 100–300ms).

### Pipecat

- **Frame-based pipeline:** `transport.input() → STT → user_aggregator (VAD) → LLM → TTS → transport.output() → assistant_aggregator`.
- Claims **500–800ms** round-trip typical.
- **Silero VAD** in `LLMContextAggregatorPair` detects end-of-utterance and **cancels TTS on interrupt** (Deepgram tutorial).
- **SentenceAggregator** pattern (also Pipecat/LiveKit): buffer LLM tokens until sentence boundary before TTS — critical for streaming cascade latency.
- Multi-agent via message bus; Pipecat Flows for structured dialogs.

### Deepgram (bundled vs DIY)

- **Voice Agent API:** single WebSocket bundles STT + LLM routing + TTS (cascade inside one connection).
- **DIY:** Pipecat + Deepgram Nova-3 STT + external LLM + Aura TTS — full control, text artifacts at each stage.
- Deepgram blog: cascade favored for **auditability, component swap, function-calling reliability**; S2S for latency/prosody when compliance/debug less critical.

---

## Perplexity / consumer voice UX notes

Perplexity public homepage exposes **text "answer engine"** positioning only — no documented mic pipeline, VAD, or voice agent architecture. Not useful as a voice-system authority source. (Consumer voice UX elsewhere: push-to-talk vs always-listening; Perplexity product voice features not scraped here.)

---

## Cross-vendor synthesis: S2S vs cascade

| Dimension | Speech-to-speech (OpenAI Realtime, Gemini Live) | Cascaded STT→LLM→TTS |
|-----------|--------------------------------------------------|----------------------|
| Latency | Lower first-audio potential (<500ms cited) | Sub-1s achievable with streaming overlap (~755–947ms measured in Salesforce tutorial) |
| Tool use | Native function + MCP in session | Mature OpenAI function calling; inspectable tool loop |
| Debuggability | Audio-primary; transcript may diverge from audio | Text at every boundary |
| Partials | Model-internal | STT partials → UI only; LLM on finals |
| Barge-in | `interrupt_response`, semantic VAD | VAD + cancel TTS stream (Pipecat/LiveKit) |
| Self-host STT | N/A | Whisper batch / faster-whisper + Silero VAD |

Salesforce/arXiv finding: native Qwen2.5-Omni S2S **~13s TTFA**, no function calling — cascaded pipeline still production default for tool agents.

---

## Source excerpts (short quotes + URLs)

1. "Build speech-to-speech agents that listen, reason, speak, and call tools." — OpenAI Realtime overview  
   https://developers.openai.com/api/docs/guides/realtime

2. "Voice-agent sessions use the standard Realtime API conversation lifecycle… sends audio or text, and listens for model responses, tool calls, and session events." — same

3. "If your application needs live transcript deltas from a microphone… use Realtime transcription… instead of the file-oriented streaming path." — STT guide  
   https://developers.openai.com/api/docs/guides/speech-to-text

4. "`interrupt_response`: only in conversation mode" — VAD guide  
   https://developers.openai.com/api/docs/guides/realtime-vad

5. "Use the live audio API path when the interaction should feel conversational and immediate… barge-in, low first-audio latency, natural turn taking, and realtime tool use." — Voice agents  
   https://developers.openai.com/api/docs/guides/voice-agents

6. "MCP tools are executed by the Realtime API itself… your client configures access, listens for MCP lifecycle events." — Realtime with tools  
   https://developers.openai.com/api/docs/guides/realtime-mcp

7. "Internally, the transcribe() method reads the entire file and processes the audio with a sliding 30-second window." — Whisper README  
   https://github.com/openai/whisper

8. "segments is a generator so the transcription only starts when you iterate over it." — faster-whisper README  
   https://github.com/SYSTRAN/faster-whisper

9. "Streaming audio through an STT-LLM-TTS pipeline, reliable turn detection, handling interruptions." — LiveKit Agents  
   https://docs.livekit.io/agents/

10. "Transport receives audio → Speech Recognition → LLM → Speech Synthesis → Transport streams audio back." — Pipecat  
    https://docs.pipecat.ai/pipecat/get-started/introduction

11. "When a user speaks over the agent, Silero VAD detects the interruption and cancels the current TTS output." — Deepgram + Pipecat guide  
    https://developers.deepgram.com/docs/build-voice-agent-with-pipecat-and-deepgram

12. "Partial transcripts… Useful for UI feedback but not sent to the LLM. Final transcripts… what we send to the LLM." — Salesforce voice agent tutorial (via search)  
    https://arxiv.org/html/2603.05413v1
