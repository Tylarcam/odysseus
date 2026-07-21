# Voice Architecture for Odysseus CMD Center

**Question:** What architecture patterns do production voice AI chat apps (Perplexity-class, Jarvis-style ambient, Whisper pipelines) use to keep speech→text→reason→speech low-friction — and which optimizations should Odysseus apply *without* replacing Realtime + Jarvis bridge + local STT?
**Engines:** A1 last30days · A2 Firecrawl · A3 Perplexity
**Date:** 2026-07-15
**Session:** `rp-voice-arch-20260715`
**Category:** howto

---

## Executive summary (read first)

CMD Center audio is not missing a model — it is **over-branched at transcription**. Production stacks (LiveKit, Pipecat, OpenAI Realtime, AssemblyAI/Deepgram) converge on one pattern: **one happy path, soft empty-speech loop, streaming partials, turn detection separate from STT, degrade only on health**.

Odysseus already has the right bones: Realtime WebRTC + whisper-1 input transcription + Jarvis cancel-and-bridge to the text agent + mic lease + Phase 1 cancel semantics. The friction you feel at “Transcription” is the **cascade of competing STT modes** (Realtime / stream / batch / browser), **provider mismatch 503s**, **batch re-decode**, and **empty transcript dead-ends** — not a need for a new vendor.

**Do next (ROI order):** (1) eager commit on `speech_stopped`, (2) empty-speech soft re-arm, (3) VAD silence tuning, (4) Phase 1.5 STT provider sync, (5) finish Phase 2 streaming PTT as Tier-1 fallback only, (6) kill always-on triple-path, (7) mic-lease UX on contention. Keep cancel-and-bridge for vault tools; do not chase native S2S for tool-heavy turns.

---

## Answers

### 1. Canonical happy-path pipeline

```
mic → VAD / turn detect → streaming STT (partials UI, final commit)
    → agent loop (tools) → streaming TTS → barge-in cancel
```

**Single-path by default.** Frameworks (LiveKit, Pipecat) own overlap and interrupt; vendors supply plugins. Multi-path only as **degraded tiers**, not parallel races.

**Odysseus Tier 0 (keep):** Realtime WebRTC → server VAD → whisper-1 transcript → Jarvis bridge → text agent → bridge TTS.

### 2. Turn-taking, partials, empty speech

- **Turn detection is splitting from STT** (LiveKit Turn Detector v1.0, Jul 2026; Silero + SmartTurn in OSS). Waiting on final STT for endpoint = walkie-talkie UX.
- **Partials = UI + speculative prep; finals = agent submit.**
- **Empty / filler transcripts = soft re-arm**, not `turn.failed`. Consumer assistants stay listening with neutral copy (“didn’t catch that”).

### 3. Realtime S2S vs cascaded STT→LLM→TTS

| Mode | Use when |
|------|----------|
| Speech-to-speech Realtime | Natural chat, lowest TTFA, light tools / MCP-in-session |
| Cascaded (STT → text agent → TTS) | Tool-heavy vault work, auditability, existing agent loop |

Jarvis cancel-and-bridge is the **correct** pattern for Odysseus vault tools. Latency win = overlap (eager commit + sentence TTS), not removing the bridge. Native S2S alone is a poor fit for full FormFlow/agent tooling (enterprise notes: S2S without function calling is a dead end for agents).

### 4. Whisper / faster-whisper wiring

- Open-source Whisper is **batch / 30s windows** — not live-native.
- Production local path: **external VAD → utterance buffer → faster-whisper stream wrapper** (`{partial, final}`), Silero VAD optional.
- Batch `/api/stt/transcribe` = attachments / dictation only.
- Odysseus gap: stream path still re-decodes full PCM buffer (~1.5s) — fix that before treating stream as Tier 1.

### 5. Mic ownership / lease

Singleton MediaStream + cross-process lease (already in `mic_lease.py`): check before `getUserMedia`, surface holder (Clicky), pause Realtime on `track.onmute`, keep silent AudioWorklet alive during hot-mic so browser does not sleep the capture graph.

### 6. Optimization checklist (mapped to Odysseus)

| # | Optimization | Maps to | Effort |
|---|--------------|---------|--------|
| 1 | Eager turn commit on Realtime `speech_stopped` + non-empty transcript | `voiceRealtime.js` bridge | S |
| 2 | Empty-speech soft re-arm (no failed turn) | `voiceChat.js` `stt.empty` path | S |
| 3 | Tune `server_vad` silence 400–500 ms, prefix ~300 ms | Realtime session config | S |
| 4 | Phase 1.5: refresh `/api/stt/stats` on `mic.start`; actionable 503 | `voiceRecorder.js`, `stt_routes.py` | S |
| 5 | Phase 2: true incremental stream STT (no full-buffer re-decode) | `stt_stream_routes.py`, `sttStream.js` | M |
| 6 | Tiered degradation: Realtime → stream → browser (health only) | `voiceChat.js` transport pick | M |
| 7 | Mic lease + `onmute` UX | `micLease.js`, CMD Audio HUD | S |
| 8 | Barge-in during bridge TTS via existing `cancelTurn()` | Phase 1 already shipped; wire hot-mic | S–M |
| 9 | Optional: STT context priming with vault brief keywords | Realtime transcription prompt | M |
| 10 | Phase 3 Silero + barge-in for OSS path | `voice-rebuild-orchestration.md` | L |

North-star (unchanged): **mic-stop → assistant first audio p50 ≤ 1.2s** (`docs/voice-rebuild-orchestration.md`).

---

## Landscape (compressed)

- **OpenAI:** Realtime S2S vs transcription sessions vs batch STT/TTS are separate products; `server_vad` / `semantic_vad`; tools native or MCP-in-session.
- **LiveKit / Pipecat:** Session state machine + cancel propagation; streaming at every stage; turn detector as first-class component.
- **Whisper ecosystem:** faster-whisper + Silero + WhisperLive-style WS for self-host.
- **Perplexity:** Public docs thin on duplex engineering; product pattern is “voice as thin I/O over the same answer/agent engine” — aligns with Odysseus vault brief + agent loop.

---

## Risks, gaps, open questions

- Always-on STT racing vs sequential tiers (prefer sequential).
- Semantic VAD maturity — start with tuned `server_vad` + client heuristics.
- Stream STT local-only today — Tier 1 unavailable in Docker without `INSTALL_STT` / faster-whisper.
- Bridge still adds a hop; mitigate with sentence-chunk TTS overlap, do not invent a second agent brain in Realtime for vault scope.

---

## Odysseus target state (one diagram)

```
CMD Audio
  └─ Tier 0: Realtime WebRTC + vault brief
        VAD → whisper-1 deltas (UI) → speech_stopped + final
        → cancel Realtime speak → Jarvis agent SSE → bridge TTS
        → empty? soft re-arm · barge-in? cancelTurn()
  └─ Tier 1 (no OPENAI_API_KEY / Realtime down):
        PTT/hot-mic → /api/stt/stream (incremental) → agent → TTS
  └─ Tier 2: browser Web Speech (last resort)
  └─ Mic lease gates all tiers; Clicky contention is explicit UX
```

---

## Appendix — research legs

### A1 Recency

See `a1_last30days.md` (LiveKit Turn Detector v1.0, GPT-Realtime-2.1 interruption/silence, AssemblyAI STT context, ElevenLabs endpointing as latency tax, Caller Digital VAD-first budgets, hugging-voice Silero + Pipecat SmartTurn).

### A2 Authority

See `a2_firecrawl.md` (OpenAI Realtime/STT/TTS fork, Whisper batch vs faster-whisper + Silero, LiveKit/Pipecat frame pipelines, Deepgram bundled vs DIY, Perplexity homepage non-authoritative for voice arch).

### A3 Perplexity

See `a3_perplexity.md` (engine: `perplexity_agent_direct`; Tier 0/1/2 degradation; top-7 ROI checklist; keep cancel-and-bridge for vault tools).
