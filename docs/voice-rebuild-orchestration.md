# Voice rebuild — phase orchestration (1–4)

> Goal: Perplexity-quality voice delegation on an OSS-first stack. Keep the
> backend agent loop untouched; rebuild the client voice layer around a single
> `VoiceSession` state machine, then upgrade each stage to streaming.
> Realtime (OpenAI WebRTC) stays as an optional premium transport.
>
> North-star metric: **time from "user stops talking" to "assistant starts
> speaking"** (target p50 ≤ 1.2s, p95 ≤ 2.5s — matches `/api/voice/slo` targets).

## Architecture target

```
mic ──► turn detect ──► streaming STT ──► agent loop ──► streaming TTS
        (Silero VAD      (partial          (backend       (Kokoro,
         + semantic)      transcripts)      as-is)          sentence chunks)

            all owned by VoiceSession: idle → listening → thinking → speaking
            Esc / barge-in → cancel(): stop audio, discard turn, back to listening
```

Design sources: LiveKit (session state machine, turn detector), Pipecat
(cancel propagation through every stage), Perplexity (cascade + stream
everything, voice as thin I/O over the same agent), Deepgram/ElevenLabs
(streaming provider interfaces), Kokoro/faster-whisper/Silero (local models).

Explicitly out of scope: single-model speech-to-speech (Moshi), telephony
stacks, replacing the realtime gateway.

---

## Phase 1 — cancel semantics (Esc fix) ✅ SHIPPED

Esc is a true cancel: discard, never submit, no auto re-arm.

| Item | Detail |
|---|---|
| Files | `static/js/voiceRecorder.js`, `static/js/voiceChat.js`, `static/js/voiceKeyboardPtt.js` |
| Added | `cancelRecording()` (discard flag + getUserMedia-window cancel), `cancelTurn()` (recorder + agent stream + TTS + realtime bridge), `_resumeSuppressed` gate on both auto-resume entry points |
| Esc behavior | 1st Esc: cancel in-flight turn · realtime hot mic idle: disconnect link · all idle: falls through to vault/modals |
| Telemetry | new events `mic.cancelled {during}`, `turn.cancelled {reason}` |
| Tests | `tests/test_voice_esc_cancel.py` (6 contract tests) + full voice suite green (79) |

## Phase 1.5 — STT provider mismatch bug (✅ shipped)

Was: `Transcription failed: STT service not available or set to browser
mode` — client POSTs `/api/stt/transcribe` while the server is in browser
mode (`stt_service.available` false ⇒ 503). Stale `_sttProvider` cache vs
server setting (or SpeechRecognition unavailable).

Fix: client refreshes STT provider before transcribe; server returns an
actionable 503; covered by `tests/test_voice_stt_provider_mismatch.py`.

Fix plan (~3 files):
1. `voiceRecorder.js` — re-fetch `/api/stt/stats` on `mic.start` if the cache
   is older than ~30s; if provider is `browser` but `window.SpeechRecognition`
   is missing, surface the settings hint instead of silently recording.
2. `routes/stt_routes.py` — 503 message should say *which* provider is
   configured and what to change (`Settings → Audio & Voice`).
3. Regression test: provider-mismatch contract in `tests/`.

Exit: recording works in browser mode end-to-end; mismatch produces one
actionable toast, not a failed turn.

## Phase 2 — streaming STT

Replace batch record→blob→transcribe with a streaming transcription channel
so the agent submit happens at end-of-speech, not after upload+decode.

| Item | Detail |
|---|---|
| Server (≤3 files) | new `routes/stt_stream_routes.py` — WebSocket `/api/stt/stream`; wraps faster-whisper incremental decoding (or Parakeet later) behind the existing `stt_service` provider switch; auth + per-user session cap like voice routes |
| Client (≤2 files) | `static/js/sttStream.js` — AudioWorklet PCM frames → WS, receives `{partial, final}`; `voiceChat.js` consumes finals through the existing `onTranscription` path |
| Fallback | provider `browser` keeps Web Speech API; batch `/api/stt/transcribe` stays for dictation attachments |
| Cancel | `cancelTurn()` closes the WS with a `cancelled` close code — server discards the partial buffer (Pipecat-style propagation) |
| Telemetry | `stt.partial` events; SLO gains `speech_stop_to_submit` histogram |

Exit: PTT turn submits within ~300ms of VAD stop on local Whisper;
`stt.partial` visible in the debug panel; Esc mid-stream leaves no orphan WS.

## Phase 3 — turn detection + barge-in (hot mic for OSS path)

Make the local path hands-free like realtime: mic stays open through TTS.

| Item | Detail |
|---|---|
| VAD (≤2 files) | `static/js/vadWorklet.js` — Silero VAD (onnxruntime-web) in an AudioWorklet; replaces the RMS threshold in `voiceRecorder.js:110`; config surfaced in Settings → Audio & Voice |
| Endpointing | dynamic: VAD silence + "is the partial transcript syntactically complete" heuristic (cheap regex/length rules first; LiveKit turn-detector model later) |
| Barge-in (≤2 files) | keep capture alive during TTS with echo cancellation; speech during `speaking` → `cancelTurn()` minus suppression → back to `listening` (mirror realtime's `BARGE_IN_DEBOUNCE_MS` debounce) |
| State machine | promote Phase 1's flags into an explicit `VoiceSession` object (`idle/listening/thinking/speaking` + `cancel()`/`bargeIn()` transitions); `voiceChat.js` delegates to it |
| Tests | golden trace fixture `golden_esc_cancel_turn.json` + barge-in local fixture; `forbidden_after: turn.cancelled → [turn.committed, loop.resume]` |

Exit: full conversation without touching the keyboard; speaking over the
assistant interrupts it within ~250ms; Esc still hard-cancels.

## Phase 4 — streaming TTS (Kokoro)

| Item | Detail |
|---|---|
| Server (≤2 files) | Kokoro-82M behind the existing TTS provider interface; chunked audio endpoint (stream WAV/PCM per sentence) |
| Client (≤1 file) | `tts-ai.js` already speaks sentence chunks (`tts-ai.js:429`) — point it at the streaming endpoint; keep current engine as fallback |
| Cancel | `cancelTurn()` aborts the fetch stream + flushes the audio queue |

Exit: first audio ≤ 500ms after first sentence completes; SLO
`mic_to_first_audio` p50 ≤ 1.2s on local stack; `/api/voice/slo` healthy.

---

## Cross-phase rules

- Phase gate: complete → verify → explicit approval before the next phase
  (per CLAUDE.md). Each phase ≤ 5 files.
- Verification per phase: `node --check` on edited JS, targeted pytest files,
  then full voice suite (`tests/test_voice_*.py`), then a live turn with
  `localStorage.odysseus_voice_debug = '1'` checking the event trace.
- Every new stage must implement two hooks or it doesn't merge:
  `cancel()` (Esc/barge-in) and a telemetry emit with the current turn ID.
- OSS-first: no feature lands realtime-only without a local equivalent.
- Rollback: static/ is live-mounted — reverting a phase is a git revert +
  hard refresh; no container rebuild needed.

## Status

| Phase | State |
|---|---|
| 1 — cancel semantics | ✅ shipped (this branch) |
| 1.5 — STT mismatch bug | ✅ shipped |
| 2 — streaming STT | ✅ shipped (pending live QA) |
| 3 — turn detect + barge-in | ⬜ planned |
| 4 — streaming TTS | ⬜ planned |
