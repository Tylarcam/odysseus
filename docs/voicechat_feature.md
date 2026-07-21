[complete] Phase 0: Audit and instrumentation
Objective: Make the current pipeline measurable and falsifiable.

Scope: Existing PTT stack only; no architecture change.

Tasks:

Add VoiceTelemetry module with structured events (see checklist).
Log correlation ID per turn: turnId from mic start through TTS idle.
Fix obvious state bugs: call voiceChatModule.onAssistantTurnComplete(false) on stream error; emit odysseus:tts-idle from stop().
Add STT timing: browser onend wait before reading transcript.
Dashboard: dev panel showing last 20 voice events + latencies.
Dependencies: None.

Test criteria:

Every mic session produces a complete event trace or explicit *.failed reason.
Reproduce “sent but no response” with a logged break point.
Exit criteria: You can answer in one glance: “STT empty” vs “chat blocked” vs “loop stuck.”

Risks: Instrumentation added to code you plan to retire — keep it behind ?voice_debug=1.

Phase 1: Restore bidirectional audio (interim PTT OR realtime bootstrap)
Objective: Guaranteed user→agent→user turn completion.

Scope A (interim, 1 week): Fix PTT loop end-to-end.
Scope B (parallel, 2 weeks): Voice gateway + WebRTC session MVP.

Tasks (interim PTT):

Block submit while isStreaming(); queue user turn or cancel agent.
Wait for recognition.onend before browser STT read.
Watchdog: if _awaitingReply > 30s, reset and surface error.
Auto-start mic when voice chat enabled (optional desktop).
Confirm Docker has faster-whisper or default desktop to browser STT.
Tasks (realtime MVP):

POST /api/voice/session → ephemeral token + session config.
Client: RTCPeerConnection, mic track, remote audio playback.
Server: session proxy or direct OpenAI Realtime WebRTC handshake.
Map input_audio_buffer.speech_started/stopped/committed to UI + telemetry.
Dependencies: Phase 0 telemetry; HTTPS for mic; provider API access.

Test criteria:

10 consecutive turns: user text reaches chat history; agent reply audible every time.
Realtime: speech_started within 200ms of speaking; committed within 1s of silence.
Exit criteria: Median turn success rate > 95% on desktop Chrome.

Risks: iOS WebRTC + autoplay policies; provider region latency.

[complete] Phase 2: Restore conversational turn-taking
Objective: Hands-free turns without manual stop; natural pacing.

Tasks:

Enable server VAD / semantic turn detection in realtime session config.
Remove push-to-stop requirement in voice mode.
Sync chat timeline from conversation.item.input_audio_transcription.completed + response.audio_transcript.delta.
Bridge tool-heavy requests: pause realtime → run agent_loop text → resume with summarized speech.
Region-aware routing: voice gateway colocated with model region.
Dependencies: Phase 1 realtime MVP.

Test criteria:

Hands-free 5-turn dialog without button presses.
End-of-turn detection: < 800ms after user stops speaking (p95).
Chat UI matches spoken content within 500ms.
Exit criteria: Feels like “talk, pause, answer” without tap discipline.

Risks: VAD false positives in noisy environments; tool latency blowing turn budget.

Phase 3: Interruption / barge-in [complete]
Objective: User can cut off agent mid-sentence.

Implemented:
- `performBargeIn()`: stop remote playback, `response.cancel`, `output_audio_buffer.clear`
- 400ms debounce after agent audio starts (`barge_in.debounced` telemetry) to ignore echo
- Half-duplex fallback: `setHalfDuplex(true)` / `localStorage odysseus_voice_half_duplex=1` pauses mic during agent speech
- Visualizer: listening overrides speaking; sync marks interrupted assistant bubbles


Tasks:

On input_audio_buffer.speech_started while agent speaking: stop playback immediately, response.cancel, clear audio buffer.
Debounce false triggers during agent start.
Ducking / half-duplex fallback for weak AEC devices.
UI: “listening” overrides “speaking” in visualizer.
Dependencies: Phase 2 continuous listen.

Test criteria:

Interrupt within 300ms of user speech during agent playback.
No overlapping agent audio after interrupt.
Conversation remains coherent (cancelled partial not committed as final).
Exit criteria: Pass scripted barge-in test suite (10 scenarios).

Risks: Over-aggressive VAD cancelling agent; echo-triggered false barge-in.

Phase 4: Reliability, latency, production hardening [complete — sub-phases below]

**4A — Client reconnect & session hardening** [complete]
- Exponential backoff reconnect, session TTL (55m), keepalive stale detection, ICE restart
- Tab background: pause mic; reconnect on focus (`voiceRealtime.js`, `voiceChat.js`)

**4B — Server security & connection limits** [complete]
- Rate limits on `/connect`, `/client-secret`, `/telemetry` (`voice_routes.py`)
- Per-user session registry + TTL (`VoiceSessionRegistry` in `realtime_gateway.py`)

**4C — Telemetry ingest + SLO metrics** [complete]
- `POST /api/voice/telemetry` — batched turn events → `VoiceMetricsStore`
- `GET /api/voice/slo` — p50/p95 mic→first-audio, healthy flag
- Client auto-flush on turn end when voice chat active (`voiceTelemetry.js`)
- Debug panel SLO strip (`voiceDebugPanel.js`); tests in `test_voice_metrics.py`

**4D — Load / soak testing** [complete]
- `scripts/load_test_voice_gateway.py` — concurrent `/telemetry`, optional `/connect`, public `/stats`+`/slo` probes, `--soak-minutes` loop
- Golden trace fixtures in `tests/fixtures/voice/` + `tests/test_voice_golden_trace.py` (event order + SLO derivation)
- `services/voice/trace_validate.py` — shared ordered-step / forbidden-after validation

**Run 4D locally:**

```bash
# Public probes + telemetry burst (needs --bearer or session cookie)
python scripts/load_test_voice_gateway.py --bearer ody_... --telemetry-batches 50

# 30-min soak (telemetry + SLO each minute)
python scripts/load_test_voice_gateway.py --bearer ody_... --soak-minutes 30 --interval-sec 60

# Optional live SDP load (OPENAI_API_KEY on server)
python scripts/load_test_voice_gateway.py --bearer ody_... --connect-requests 5 --connect-concurrency 2
```

Golden traces: `pytest tests/test_voice_golden_trace.py -q`

Objective: Production-grade SLOs.

Tasks:

Reconnect strategy: session expiry, network blip, tab background.
Retry with backoff; resume conversation context.
Metrics: mic_start→first_audio_out, speech_stop→response.created, interrupt latency.
Load test gateway; connection limits per user.
Security review: token TTL, scope, rate limits.
Dependencies: Phases 1–3.

Test criteria:

p50 first audio < 1.2s, p95 < 2.5s (same region).
30-min session without stuck state.
Network drop recovery within 5s.
Exit criteria: SLO dashboard green for 7 days in staging.

Risks: Cost at scale; model rate limits.

Phase 5: UX polish and rollout
Objective: Perplexity-parity feel in product.

Tasks:

Voice mode entry/exit animations; clear states (listening / thinking / speaking).
Device picker integration (reuse audioOutput.js).
Mobile Safari hardening; headset/bluetooth matrix.
Feature flag rollout; fallback to PTT text mode.
User-facing docs: “Voice uses realtime AI session.”
Dependencies: Phase 4.

Test criteria: Dogfood 50 sessions across devices; NPS-style “felt natural” > 4/5.

Exit criteria: Feature flag on for primary users.

Risks: Mobile parity lag behind desktop.

**Phase 5 implementation (shipped):**

- `voiceStatus.js` — status pill: listening / thinking / speaking / connecting / reconnecting; body classes for entry animation.
- `voiceVisualizer.js` — amber thinking waveform state.
- `voiceRealtime.js` — iOS/Safari mono AEC, audio sink on output change, reconnect with visible state.
- `voice_chat_enabled` in settings + `/api/voice/stats`; PTT fallback when realtime unavailable.
- User copy: "Voice uses a realtime AI session when available…"

Device matrix (manual QA): Chrome desktop/Android, Safari macOS/iOS, Bluetooth headset — realtime + PTT fallback; desktop Output picker routes realtime audio via `setSinkId`.

5. Technical checklist
Client media capture

 getUserMedia permission flow + secure context (HTTPS)

 WebRTC mic track attached to peer connection (not batch MediaRecorder for voice mode)

 Device selection / echo cancellation strategy documented per browser

 iOS Safari test matrix (WebRTC + playback)
Realtime session setup

 RTCPeerConnection lifecycle (create, connect, close)

 Remote audio element bound + setSinkId for output routing

 Session config: modalities, voice, turn_detection

 Handle session.created, session.updated
Auth / ephemeral tokens

 POST /api/voice/session returns short-lived token only

 No provider API keys in frontend bundles

 Token bound to Odysseus user session
VAD / semantic turn detection

 Server-side VAD enabled in session

 Tune silence_duration_ms / semantic EOT if available

 Log speech_started / speech_stopped timestamps
Interruption policy

 Cancel playback on user speech_started during response.audio

 response.cancel wired

 Clear queued output buffers

 Half-duplex fallback when AEC poor
Transcript / event synchronization

 User transcript → chat bubble on conversation.item.created

 Agent transcript deltas → streaming bubble

 Single turnId across client + server logs
Playback queue management

 Realtime: play incoming audio chunks directly (no sentence TTS queue)

 Legacy read-aloud: keep tts-ai.js queue separate from voice mode

 tts-idle equivalent: response.done + audio buffer drained
Reconnect / retry behavior

 ICE restart / full session recreate policy

 Conversation history rehydration on reconnect

 User-visible “Reconnecting…” state
Metrics and logs

 voice.mic.start, voice.speech.start, voice.speech.stop

 voice.turn.committed, voice.response.created, voice.first_audio_out

 voice.response.done, voice.barge_in, voice.loop.stuck

 Latency histograms per segment
Test fixtures

 Scripted audio samples (quiet, noisy, overlap)

 Mock realtime server for CI event-order tests

 Golden trace: expected event sequence per turn

 Regression test for current PTT bugs (empty STT, stream error stuck)
Browser / device / network matrix

 Chrome desktop / Android

 Safari iOS / macOS

 Bluetooth headset + speaker

 WiFi / 4G / 150ms+ RTT

 Docker LAN vs public HTTPS
