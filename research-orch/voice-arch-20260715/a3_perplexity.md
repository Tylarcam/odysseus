# A3 Perplexity Digest — Voice Transcription Architecture

**Engine:** `perplexity_agent_direct` (Odysseus `/api/research/start` unreachable for poll; direct Perplexity Agent `pro-search` preset)  
**Session:** `rp-voice-arch-20260715`  
**Date:** 2026-07-15

---

## Findings

1. **The transcription hop is the dominant latency cliff in cascaded voice agents.** Production voice stacks achieve sub-second time-to-first-audio only when STT streams continuously and downstream stages start on *interim* text, not after batch decode. Waiting for a full utterance upload + Whisper pass pushes first response into multi-second territory and breaks conversational feel [Deepgram bundled vs assembled](https://deepgram.com/learn/voice-agent-api-architecture-bundled-vs-assembled), [Luong Voice AI Playbook Pt.2](https://luonghongthuan.com/en/blog/voice-ai-playbook-pipeline-architectures-part2/).

2. **For Odysseus CMD Center, the canonical happy path should stay Realtime WebRTC → whisper-1 input transcription → Jarvis bridge → text agent → bridge TTS.** Native speech-to-speech is not viable for tool-heavy vault work: enterprise benchmarks show S2S models at ~13s time-to-first-audio, no function calling, and no streaming audio output suitable for agent loops [arXiv enterprise voice agents](https://arxiv.org/html/2603.05413v1). OpenAI Realtime already bundles STT inside the session; the win is *pipelining* transcript deltas into the bridge, not replacing the bridge [OpenAI Realtime guide](https://developers.openai.com/api/docs/guides/realtime).

3. **Optimal turn pipeline for Realtime + Jarvis:** mic (16 kHz mono PCM over WebRTC) → **server-side VAD** (`server_vad`, 400–600 ms silence, ~300 ms prefix padding) → **streaming `input_audio_transcription` deltas** → **eager turn commit on `speech_stopped`** (do not wait for a second “polished” pass) → cancel Realtime spoken reply → inject final transcript into chat/agent loop → sentence-chunked bridge TTS. Perceived “realtime” comes from overlapping STT, LLM, and TTS, not a single fast model [arXiv](https://arxiv.org/html/2603.05413v1), [OpenAI realtime transcription](https://platform.openai.com/docs/guides/realtime-transcription).

4. **Perplexity-class and Jarvis-like UX both treat voice as thin I/O over the same agent** — voice is not a separate brain. Consumer assistants stream partials into planning, use semantic or hybrid end-of-turn (silence + utterance completeness), and keep the mic hot with short-window barge-in (~200 ms) during TTS. Pipecat/LiveKit formalize this as a session state machine (`idle → listening → thinking → speaking`) with cancel propagation through every stage [LiveKit Agents](https://docs.livekit.io/agents/overview/), matching Odysseus’s existing `voice-rebuild-orchestration.md` north star (p50 ≤ 1.2 s mic-stop → first audio).

5. **Unify three STT modes as one primary path + explicit degraded tiers, not three parallel competitors.** Racing multiple STTs simultaneously (Realtime + faster-whisper + Web Speech) saves ~50–100 ms in theory but adds state divergence, double-commits, and debug pain. Better pattern for an existing stack:
   - **Tier 0 (default):** Realtime session transcription (Jarvis hot mic).
   - **Tier 1 (degraded):** PTT + local faster-whisper **stream** (`/api/stt/stream`) — not batch re-decode.
   - **Tier 2 (last resort):** browser Web Speech when server/local unavailable.
   Promote tier only on health signals (WebSocket close, ping > 500 ms, 503 provider mismatch), then hold for session remainder [Deepgram STT+NLP+TTS workflows](https://deepgram.com/learn/designing-voice-ai-workflows-using-stt-nlp-tts).

6. **Empty / no-speech handling must be a soft loop, not a dead end.** Filter at the bridge: if post-trim transcript is empty, < 3 chars, or filler-only (`um`, `uh`, `…`) after ≥ 1 s of detected speech, emit telemetry (`stt.empty`) but **re-arm listening** without `turn.failed`, without blocking PTT, and with a neutral UI (“didn’t catch that — still listening”). Odysseus already emits `stt.empty` in `voiceChat.js` but leaves the user in a friction state; Perplexity/Jarvis patterns treat these as VAD false positives, not errors.

7. **Partial transcripts unlock ROI without rewriting the agent loop.** “Eager processing” — start LLM/tool prefetch when a partial matches a high-confidence vault command (e.g., “open the vau—”) — can shave 50–100 ms [Luong Playbook](https://luonghongthuan.com/en/blog/voice-ai-playbook-pipeline-architectures-part2/). For Jarvis, partials should update the chat bubble (`voiceRealtimeSync.js`) and optionally pre-warm tool routes; only **commit** the turn on `speech_stopped` + non-empty final.

8. **Whisper / faster-whisper wiring for fallback:** streaming incremental decode over WebSocket with `{partial, final}` events; never re-decode the full buffer on each chunk. Batch `/api/stt/transcribe` stays for attachments only. Tune `gpt-realtime-whisper` delay (`minimal`/`low` for CMD Center; benchmark with vault vocabulary) [OpenAI realtime transcription delay docs](https://developers.openai.com/api/docs/guides/realtime-transcription). Local sidecar (tiny/base faster-whisper) gives offline *feedback* (live captions) even when agent reasoning stays cloud.

9. **Mic lease is a first-class UX surface, not a backend detail.** Singleton `MediaStream` + cross-process lease file (Odysseus `mic_lease.py` + Clicky) should: (a) check lease before `getUserMedia`, (b) listen for `track.onmute` / OS capture theft, (c) pause Realtime and show “mic in use by {holder}”, (d) use longer TTL for realtime (600 s vs 90 s) — already modeled in code. Browser mic sleep during silence: keep an `AudioWorklet` or silent graph alive during hot-mic sessions.

10. **Barge-in during bridge TTS:** on user speech, `audio_buffer.clear` + stop bridge TTS queue + cancel in-flight agent stream (`cancelTurn()` semantics already shipped Phase 1). Short-window VAD during assistant speech prevents the “yelling over TTS” failure mode [Deepgram voice agent architecture](https://developers.deepgram.com/docs/voice-agent-architecture).

---

## Contradictions / uncertainty

- **Parallel STT racing vs single VoiceSession:** Perplexity’s “first-to-commit wins” race is latency-aggressive but conflicts with Odysseus’s planned `VoiceSession` state machine and telemetry (`stt.final` / `turn.committed`). Recommendation: *sequential degradation with health-based promotion*, not always-on triple broadcast.

- **`conversation.item.create` inject vs cancel-and-bridge:** Perplexity suggests injecting transcript into Realtime and calling tools in-session; Odysseus Jarvis deliberately **cancels** Realtime reply and routes to the full text agent for vault tools. For vault scope, cancel-and-bridge is correct (tool breadth, memory, streaming TTS). Injection is only worth it for a tiny realtime tool subset (`voice_tools.py`).

- **Semantic VAD maturity:** OpenAI `server_vad` is documented; “end-of-thought” semantic commit on partial grammar is described in practitioner blogs but not as a stable OpenAI API primitive — treat as client-side heuristic (punctuation + min length + command regex) until proven on vault audio.

- **Perplexity product surface:** Public Perplexity voice/Comet UX patterns are inferred from cascaded-agent literature, not primary vendor docs in this run.

---

## Implications

**For Odysseus without greenfield rewrite:** Keep Realtime + Jarvis bridge as Tier 0. Invest at the **transcription boundary** — VAD tuning, eager commit, empty-speech re-arm, provider-sync, streaming PTT fallback — not a new model stack.

| Area | Current friction | Target behavior |
|------|------------------|-----------------|
| Realtime path | Waits on final polish; bridge doubles perceived latency | Commit on `speech_stopped`; stream agent TTS sentences during bridge |
| PTT fallback | Batch upload + provider 503 mismatch | Stream WS + refresh `/api/stt/stats` on `mic.start` |
| Empty speech | `stt.empty` dead-end | Soft re-arm, no `turn.failed` |
| 3 STT modes | User-visible mode confusion | One active tier; auto-promote on health |
| Mic | Lease file exists; weak UI on contention | Block capture + explain holder; pause Realtime on `onmute` |

**Telemetry to watch:** `mic_to_stt`, `sttToCommit`, `stt.empty` rate, `cmd_jarvis.mic_to_first_audio` p95 (already in `services/voice/metrics.py`).

---

## Sources

- [OpenAI Realtime and audio](https://developers.openai.com/api/docs/guides/realtime)
- [OpenAI Realtime transcription](https://platform.openai.com/docs/guides/realtime-transcription)
- [Deepgram — Designing Voice AI Workflows (STT+NLP+TTS)](https://deepgram.com/learn/designing-voice-ai-workflows-using-stt-nlp-tts)
- [Deepgram — Voice Agent API: Bundled vs Assembled](https://deepgram.com/learn/voice-agent-api-architecture-bundled-vs-assembled)
- [Deepgram — Voice Agent Architecture Overview](https://developers.deepgram.com/docs/voice-agent-architecture)
- [Luong — Cascaded vs Speech-to-Speech (Voice AI Playbook Pt.2)](https://luonghongthuan.com/en/blog/voice-ai-playbook-pipeline-architectures-part2/)
- [arXiv — Building Enterprise Realtime Voice Agents from Scratch](https://arxiv.org/html/2603.05413v1)
- [LiveKit Agents overview](https://docs.livekit.io/agents/overview/)
- Odysseus internal: `docs/voice-rebuild-orchestration.md`, `static/js/voiceChat.js`, `services/voice/mic_lease.py`

---

## Top 7 optimizations (ROI order)

1. **Eager turn commit** — fire Jarvis bridge on Realtime `speech_stopped` + first non-empty transcript; never wait for a second decode pass (~300–500 ms).
2. **Empty-speech soft re-arm** — `stt.empty` returns to listening with neutral copy; never `turn.failed` or blocked PTT.
3. **Server-side VAD tuning** — enable OpenAI `server_vad`, `prefix_padding_ms` ~300, silence 400–500 ms; reduces clipped commands and false end-of-turn.
4. **STT provider sync (Phase 1.5)** — refresh `/api/stt/stats` on `mic.start`; actionable 503 toasts; eliminates silent batch-path failures.
5. **Streaming PTT fallback (Phase 2)** — WebSocket faster-whisper partials/finals replaces batch re-decode; target ~300 ms speech-stop → submit.
6. **Tiered STT degradation** — Realtime → stream → browser promotion on health only; kill always-on triple-path confusion.
7. **Mic lease + `onmute` UX** — gate `getUserMedia` on lease; pause Realtime and surface holder when OS steals mic.
