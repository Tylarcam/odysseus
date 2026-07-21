## A1 Recency Digest

**Window:** ~30 days ending 2026-07-15  
**Focus:** Transcription and turn-taking friction in production voice chat

### Key signals (bullets with dates if known)

- **2026-07-13 - LiveKit Turn Detector v1.0:** LiveKit ships audio-native end-of-turn detection that fuses semantic and acoustic signals without waiting on a final STT transcript. Claims strongest results in a new open benchmark (`eot-bench`), with 9.9% false-cutoff at 300 ms latency budget vs 12.9% (Deepgram Flux) and 27.7% (ultraVAD). v1-mini is open-weight for CPU inference. Turn detection is now default in LiveKit Agents on LiveKit Cloud. Signal: production stacks are decoupling turn-taking from STT vendors to avoid walkie-talkie UX.

- **2026-07-06 - OpenAI GPT-Realtime-2.1 + mini:** API release emphasizes interruption behavior, silence/noise handling, and alphanumeric accuracy (order numbers, IDs). OpenAI reports 25%+ p95 latency reduction via improved caching. Full-duplex speech-to-speech path supports WebRTC, WebSocket, and SIP. Signal: native speech-to-speech models are optimizing barge-in and pause handling at the model layer, not only in orchestration.

- **2026-07-08 - OpenAI GPT-Live (ChatGPT Voice):** Consumer voice models that "listen and speak simultaneously" with background delegation to frontier models. Not yet fully in API, but signals full-duplex and ambient-style interaction moving from demo to product surface.

- **2026-07-09 - AssemblyAI / HackerNoon:** Cascading voice agent piece argues STT is the highest-leverage context layer. Universal-3.5 Pro Realtime adds `agent_context` (agent's prior turn fed into STT), punctuation-based end-of-turn detection, and sub-300 ms formatted transcripts. LiveKit and Pipecat plugins are one-line swaps. Signal: reduce downstream LLM errors by biasing transcription before turn finalization.

- **2026-06-23 / 2026-07-02 - ElevenLabs latency guide:** Endpointing (VAD silence thresholds) is often the largest controllable latency line item - e.g., 700 ms silence wait adds 700 ms per turn. Recommends tightening silence thresholds, push-to-talk/manual commit events, and speculative LLM execution on stable partial transcripts. Scribe v2 Realtime returns partials in ~150 ms. Signal: overlap stages; do not wait for final transcript before starting LLM work.

- **2026-06-22 - Caller Digital (production telephony architecture):** Stage-by-stage latency budget on real Indian carrier traffic. VAD end-of-speech (80-450 ms typical) and STT final flush dominate variance more than LLM on many calls. Best-case first-audible ~280 ms; typical ~480 ms. Recommends language-routed STT and aggressive VAD tuning with measured false-interruption rates. Signal: turn-taking config matters more than model marketing for perceived latency.

- **2026-07 - Hugging Face `hugging-voice` space + forum threads:** Open realtime voice stack using Silero VAD v5 (speech detected after 384 ms active audio) plus Pipecat SmartTurn V3 for turn detection, targeting sub-second cascaded latency. Signal: open-source reference architectures standardize Silero + dedicated turn analyzers outside the STT model.

- **2026-06/07 - faster-whisper / WhisperLive ecosystem:** Docker images and guides for WebSocket streaming STT (WhisperLive wrapping faster-whisper). Community voice-agent repos (e.g., AVA for Asterisk) mix Faster-Whisper CUDA + WebSocket streaming + explicit barge-in quarantine. Signal: self-hosted stacks mirror cloud pattern - streaming partials + separate turn logic.

- **2026-07 - Pipecat + Vonage / WebRTC.ventures:** Pipecat transport integrations emphasize streaming pipeline composition (transport -> VAD -> STT -> LLM -> TTS) with low-latency chunk processing. Signal: framework layer owns overlap and interruption, not individual API vendors.

- **2026-05-08 area - OpenAI GPT-Realtime-2 family:** Earlier API wave (Realtime-2, Translate, Realtime-Whisper) established separate paths for speech-to-speech vs chained transcription - Realtime-Whisper for dedicated transcription vs interactive speech-to-speech sessions.

- **Perplexity voice / Comet (ongoing, lighter signal on turn-taking):** Perplexity mobile app advertises voice Q&A ("type or say it"); Comet browser expanded to iOS (March 2026 per industry posts) as agentic browser, but recent coverage (TechCrunch, July 2026) centers on task automation in-browser rather than duplex turn-taking engineering. Less explicit STT/VAD detail than telephony/agent platforms.

### Quotes / posts worth knowing

> "End-of-turn detection is the difference between a voice agent that feels like a conversation and one that feels like a walkie-talkie." - LiveKit blog, Turn Detector v1.0 (2026-07-13)

> "Text-based models, however good, share a ceiling... reducing speech to text throws away the timing and acoustic signals that tell you when a speaker has actually finished." - LiveKit, on why v1 listens to audio directly

> "The larger latency cost is endpointing: the moment your system decides the user has actually finished their turn... If you wait for, say, 700 ms of silence before declaring the turn over, you have added 700 ms to every turn." - ElevenLabs, Voice agent latency optimization (Jun-Jul 2026)

> "Three of the four highest-value context sources belong at the speech-to-text layer - the layer teams most often pick last, by price." - AssemblyAI / HackerNoon (2026-07-09)

> "Improved alphanumeric recognition, silence and noise handling, and interruption behavior." - OpenAI API changelog summary for GPT-Realtime-2.1 (2026-07-06), via RohitAI analysis

> "The gap between best and typical is almost entirely VAD tuning, LLM choice, and region routing. Three knobs, in that order." - Caller Digital sub-500ms architecture post (2026-06-22)

> "Running VAD locally on the CPU (using open-source models like Silero) allows you to process 30+ms audio chunks in less than 1ms." - LinkedIn practitioner posts on LiveKit/Pipecat stacks (June-July 2026)

### Implications for the research question

Recent production signals converge on a few patterns for reducing friction at the transcription / turn-taking layer:

1. **Turn detection is splitting from STT.** The strongest July 2026 move is LiveKit's audio-native turn detector - bypassing transcript latency and prosody loss. STT vendors still ship endpointing (AssemblyAI punctuation + silence, Deepgram Flux), but frameworks increasingly treat turn-taking as a first-class, swappable component (Silero VAD + SmartTurn/Pipecat, LiveKit Turn Detector, manual commit for push-to-talk).

2. **Partial transcripts + speculative downstream work.** ElevenLabs, AssemblyAI, and OpenAI's chained guidance all push feeding stable STT partials into the LLM before endpoint fires, hiding 200-700 ms of "waiting for silence." Friction drops when the system stops treating transcription as a batch gate.

3. **Context at STT reduces re-asks and turn confusion.** AssemblyAI's `agent_context` and keyterm boosting show that wrong transcripts - not slow LLMs - cause the most conversational breakage (emails read as spaced words, etc.). Biasing STT with the agent's last question cuts repair turns, which feel like turn-taking failures to users.

4. **Speech-to-speech for duplex; cascaded for control.** OpenAI GPT-Realtime-2.1 and GPT-Live optimize interruption and silence inside the model. Most high-volume production (Caller Digital, Inception Labs commentary) still runs ASR -> LLM -> TTS for auditability, but routes simple turns to faster models and reserves speech-to-speech for natural conversation lanes. Latency wins are as much about routing and overlap as architecture choice.

5. **Open/self-hosted parity.** Hugging Face hugging-voice, faster-whisper WebSocket servers, and LiveKit v1-mini give teams the same decomposition as cloud agents: cheap local Silero VAD, dedicated turn analyzer, streaming STT, explicit barge-in handling. Jarvis/ambient hobbyist content (TikTok/Instagram, June-July) mostly reiterates this four-piece loop (STT in, agent, tools, voice out) without new turn-taking science.

6. **Measurement shifted to false-cutoff vs latency tradeoffs.** eot-bench and ElevenLabs/Caller Digital budgeting treat false interruptions and dead-air as paired metrics. Production quality in 2026 is tuned on P50/P95 TTFA *and* interruption rate, not WER alone.

**Bottom line:** The last 30 days show friction reduction happening *before* and *beside* raw transcription speed - audio-native endpointing, STT contextual priming, speculative LLM on partials, and model-level interruption tuning in speech-to-speech APIs.

### Sources (url list)

- https://livekit.com/blog/solving-end-of-turn-detection
- https://community.openai.com/t/new-realtime-models-on-the-api-gpt-realtime-2-1-and-gpt-realtime-2-1-mini/1385896
- https://rohitai.com/blog/openai-gpt-realtime-2-1-voice-agents
- https://hackernoon.com/where-context-lives-in-a-cascading-voice-agent-and-why-the-stt-layer-quietly-decides-your-accuracy
- https://elevenlabs.io/blog/voice-agent-latency-optimization
- https://caller.digital/blog/sub-500ms-latency-voice-ai-india-architecture-stt-llm-tts-2026
- https://huggingface.co/spaces/HuggingFaceM4/hugging-voice
- https://discuss.huggingface.co/t/voice-ai-agent-construction/177750
- https://webrtc.ventures/2026/07/vonage-video-connector-sdk-pipecat-transport/
- https://www.f22labs.com/blogs/difference-between-livekit-vs-pipecat-voice-ai-platforms/
- https://www.assemblyai.com/blog/best-api-models-for-real-time-speech-recognition-and-transcription
- https://www.gladia.io/blog/what-is-openai-whisper
- https://github.com/hkjarral/AVA-AI-Voice-Agent-for-Asterisk
- https://www.evalgent.com/blog/cascading-vs-speech-to-speech-voice-agents
- https://www.inceptionlabs.ai/blog/mercury-2-the-first-reasoning-model-fast-enough-to-pick-up-the-phone
- https://techcrunch.com/2026/07/03/as-the-browser-wars-heat-up-here-are-the-hottest-alternatives-to-chrome-and-safari-in-2026/
- https://play.google.com/store/apps/details?id=ai.perplexity.app.android
- https://www.forasoft.com/blog/article/openai-realtime-api-pricing
- https://apidog.com/blog/how-to-use-gpt-realtime-2-1-mini-api/
