# Research Brief — Voice / Audio AI Chat Architecture

**Topic / question:** What architecture patterns do production voice AI chat apps (Perplexity Voice/Comet-class, Jarvis-style ambient assistants, Whisper-based STT pipelines) use to keep speech→text→reason→speech low-friction — and which patterns should Odysseus CMD Center adopt *without replacing* its existing stack (OpenAI Realtime WebRTC, vault brief, Jarvis agent bridge, local faster-whisper STT stream/batch, mic lease, TTS)?

**Audience / use:** Architecture optimization for Odysseus V.A.U.L.T. Command Center audio flow; reduce transcription break points and mode friction.

**Date:** 2026-07-15  
**Category:** `howto`  
**Session id:** `rp-voice-arch-20260715`  
**Owner:** `tylarcam`

---

## Must-answer questions

1. What is the **canonical happy-path pipeline** for modern voice chat (mic → VAD → STT → turn commit → LLM/tools → TTS → barge-in), and where do apps deliberately stay single-path vs multi-path?
2. How do Perplexity-class voice UIs and Jarvis-like ambient assistants handle **turn-taking, partial transcripts, and empty/no-speech** without dead-ending the user?
3. What are the proven patterns for **Realtime (speech-to-speech) vs STT→LLM→TTS (cascaded)** — when to use each, and how to bridge tools without doubling latency?
4. How should **Whisper / faster-whisper** be wired in a production client (streaming vs batch, local vs endpoint) so provider mismatches and mid-take fallbacks do not break the session?
5. What **mic ownership / lease / contention** patterns (browser + desktop overlays) prevent "mic in use" failures?
6. What concrete **optimization checklist** maps onto an existing stack that already has: OpenAI Realtime + vault brief + agent bridge + PTT/STT fallback + mic lease + telemetry?

## Authority URLs (A2)

- https://platform.openai.com/docs/guides/realtime
- https://platform.openai.com/docs/guides/speech-to-text
- https://platform.openai.com/docs/guides/text-to-speech
- https://platform.openai.com/docs/api-reference/realtime
- https://github.com/openai/whisper
- https://github.com/SYSTRAN/faster-whisper
- https://docs.livekit.io/agents/
- https://docs.pipecat.ai/getting-started/overview
- https://www.perplexity.ai/ (product surface; note voice/comet mentions if present)
- https://deepgram.com/learn/voice-agent-architecture (or Deepgram voice agent docs if redirected)

## Recency keywords (A1)

- Perplexity voice, Perplexity Comet voice, voice AI assistant 2026
- OpenAI Realtime API WebRTC whisper-1 transcription
- Jarvis ambient voice agent architecture
- Whisper streaming STT, faster-whisper WebSocket
- barge-in VAD Silero voice agent
- speech-to-speech vs cascaded pipeline latency
- LiveKit Agents Pipecat voice pipeline

## Synthesis angle (A3)

Reconcile consumer UX (Perplexity/Jarvis-like ambient) with developer architecture (Realtime vs cascaded Whisper). Produce an **optimization-first** architecture for a vault command center that already has Realtime + agent bridge + local STT — focus on eliminating friction at the **transcription** hop, not greenfield rewrite.

## Odysseus stack context (do not invent replacements)

Keep / optimize in place:
- CMD Center → Jarvis mode → `voiceChat.setActive` → Realtime WebRTC preferred
- Realtime input transcription (`whisper-1`) → Jarvis bridge cancels Realtime reply → text agent loop → bridge TTS
- Fallback: PTT + browser Web Speech / local faster-whisper stream / batch
- Mic lease vs Clicky; vault brief injection
- Known frictions: 3 parallel STT modes, provider mismatch 503s, stream re-decode full buffer, bridge doubles latency, empty transcript dead-ends, PTT blocked while streaming

## Deliverable

Parallel legs A1 + A2 + A3 → `master_report.md` → Odysseus `deep_research` JSON + visual HTML report.
