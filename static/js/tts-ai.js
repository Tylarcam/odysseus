// static/js/tts-ai.js
// AI Text-to-Speech Module — supports server TTS and browser Web Speech API
import { emitVoiceSpeaking } from './voiceVisualizer.js';
import { applySinkToMediaElement } from './audioOutput.js';
import voiceTelemetry from './voiceTelemetry.js';
import markdownModule from './markdown.js';

let _firstAudioOutTurnId = null;
const VOICE_STREAM_MIN_CHARS = 80;
const VOICE_STREAM_HOLD_CHARS = 24;
const VOICE_STREAM_MAX_CHARS = 150;
const SYNTH_TIMEOUT_MS = 45000;

/**
 * Strip model reasoning so TTS only speaks the user-facing reply.
 * Handles <think>/<thinking>/<thought> (incl. time= attrs), Gemma channel
 * markers, Qwen "Thinking Process:", and mid-stream unclosed think blocks
 * (never speak truncated reasoning while the tag is still open).
 */
function stripThinkingForSpeech(text) {
    if (!text) return '';
    let out = markdownModule.normalizeThinkingMarkup(String(text));

    if (!markdownModule.hasUnclosedThinkTag(out)) {
        return markdownModule.extractThinkingBlocks(out).content || '';
    }

    // Unclosed think: drop completed blocks, then everything from the open
    // tag to EOF. extractThinkingBlocks keeps leading-unclosed body as reply
    // (for UI reload); speech must stay silent until a real answer exists.
    out = out.replace(/<\/think(?:ing)?>\s*<think(?:ing)?(?:\s+[^>]*)?>/gi, '\n\n');
    let prev;
    do {
        prev = out;
        out = out.replace(/<think(?:ing)?(?:\s+[^>]*)?>[\s\S]*?<\/think(?:ing)?>\s*/gi, '');
    } while (out !== prev);
    out = out.replace(/<(?:think(?:ing)?|thought)(?:\s+[^>]*)?>[\s\S]*$/gi, '');
    out = out.replace(/<\|channel>thought[\s\S]*$/gi, '');
    const orphan = out.match(/^([\s\S]+?)<\/(?:think(?:ing)?|thought)>/i);
    if (orphan) out = out.slice(orphan[0].length);
    out = out.replace(/<\/(?:think(?:ing)?|thought)>/gi, '');
    return out.trim();
}

function _ttsErrorMessage(err) {
    if (!err) return 'TTS failed';
    if (err.name === 'AbortError') return 'TTS cancelled or timed out';
    return err.message || String(err);
}

async function _toastTtsError(err) {
    try {
        const { showToast } = await import('./ui.js');
        showToast?.(`TTS: ${_ttsErrorMessage(err)}`, 4000);
    } catch (_) { /* ignore */ }
}

function _emitFirstAudioOut(via) {
    const turnId = voiceTelemetry.getCurrentTurnId();
    if (!turnId || _firstAudioOutTurnId === turnId) return;
    _firstAudioOutTurnId = turnId;
    voiceTelemetry.emit('first_audio_out', { via });
}

class AITTSManager {
    constructor() {
        this.currentAudio = null;
        this.isPlaying = false;
        this.available = false;
        this.useBrowserTTS = false;
        this.browserVoice = '';
        this.playbackSpeed = 1;
        this._provider = 'disabled';
        this.autoPlay = false;
        this.cache = new Map(); // Client-side audio cache

        // Queue for sequential auto-play
        this._queue = [];       // Array of { text, button, resetFn, paragraphIndex, ... }
        this._processing = false;
        this._skipToParagraph = null;
        // Bumped on stop() so in-flight synthesize/play cannot resurrect after cancel
        this._playEpoch = 0;
        this._synthAbort = null;

        // Streaming sentence-by-sentence TTS state
        this._streamSentencesSent = 0;  // chars of plain text already queued
        this._streamActive = false;
        this._streamButton = null;
        this._streamResetFn = null;
        this._streamDebounceTimer = null;

        // iOS/Safari audio-unlock state.
        // Mobile Safari only allows audio to start inside a user-gesture call
        // stack. Because we fetch synthesized audio over the network before
        // playing (an async gap), a freshly-created Audio() would be blocked by
        // iOS with NotAllowedError. The workaround is to keep ONE persistent
        // <audio> element, "bless" it during a real tap by playing a silent
        // clip, then reuse that same blessed element for later programmatic
        // playback.
        this._sharedAudio = null;
        this._audioUnlocked = false;
        this._speechUnlocked = false;
        this._setupAudioUnlock();

        // Check if TTS service is available
        this._readyPromise = this.checkAvailability();
    }

    _isLive(epoch) {
        return epoch === this._playEpoch && this._processing;
    }

    // ── iOS/Safari audio unlock ──

    /**
     * A single reusable <audio> element. Created lazily and reused for every
     * playback so the "unlocked" (user-gesture-blessed) state persists on iOS.
     */
    _getSharedAudio() {
        if (!this._sharedAudio) {
            const audio = new Audio();
            // playsinline avoids the fullscreen player takeover on iPhone.
            audio.setAttribute('playsinline', '');
            audio.setAttribute('webkit-playsinline', '');
            audio.preload = 'auto';
            this._sharedAudio = audio;
        }
        return this._sharedAudio;
    }

    /**
     * Attach one-time listeners so the first real user interaction anywhere in
     * the app unlocks audio playback. iOS requires the very first play() to
     * originate from a gesture; once blessed, the shared element (and Web
     * Speech API) can be driven programmatically afterwards.
     */
    _setupAudioUnlock() {
        if (typeof window === 'undefined') return;
        const handler = () => this.unlockAudio();
        // pointerdown fires earliest and is still within the gesture; touchend
        // and click are kept as fallbacks for older iOS and desktop.
        window.addEventListener('pointerdown', handler, { passive: true });
        window.addEventListener('touchend', handler, { passive: true });
        window.addEventListener('click', handler, { passive: true });
    }

    /**
     * Unlock audio + speech synthesis. MUST run inside a user gesture. Safe to
     * call repeatedly — it no-ops once each channel is unlocked.
     */
    unlockAudio() {
        // 1) Bless the shared HTMLAudioElement by playing a silent clip.
        if (!this._audioUnlocked) {
            try {
                const audio = this._getSharedAudio();
                audio.muted = true;
                audio.src = AITTSManager.SILENT_AUDIO;
                const p = audio.play();
                if (p && typeof p.then === 'function') {
                    p.then(() => {
                        audio.pause();
                        audio.currentTime = 0;
                        audio.muted = false;
                        this._audioUnlocked = true;
                    }).catch(() => {
                        // Not fatal — a later gesture will retry.
                        audio.muted = false;
                    });
                } else {
                    audio.muted = false;
                    this._audioUnlocked = true;
                }
            } catch (e) {
                /* retried on next gesture */
            }
        }

        // 2) Prime the Web Speech API. iOS won't speak() outside a gesture
        // until it has spoken once inside one; an empty utterance warms it up.
        if (!this._speechUnlocked && 'speechSynthesis' in window) {
            try {
                window.speechSynthesis.speak(new SpeechSynthesisUtterance(''));
                this._speechUnlocked = true;
            } catch (e) {
                /* retried on next gesture */
            }
        }
    }

    async checkAvailability() {
        try {
            // Check user setting first — if TTS is disabled in settings, don't show buttons
            try {
                const settingsRes = await fetch('/api/auth/settings', { credentials: 'same-origin' });
                const settings = await settingsRes.json();
                if (settings.tts_enabled === false) {
                    this.available = false;
                    this._provider = 'disabled';
                    refreshAllTTSButtons();
                    return false;
                }
            } catch {}

            const response = await fetch('/api/tts/stats');
            const stats = await response.json();
            this.available = stats.available && stats.ready;
            this.playbackSpeed = stats.speed || 1;
            this._provider = stats.provider || 'disabled';

            if (stats.provider === 'browser') {
                this.useBrowserTTS = true;
                this.browserVoice = stats.voice || '';
                this.available = 'speechSynthesis' in window;
                if (!this.available) {
                    console.warn('TTS: browser mode selected but speechSynthesis not supported');
                }
            } else if (this.available) {
                this.useBrowserTTS = false;
            } else {
                console.warn('TTS: not available');
            }
        } catch (error) {
            console.error('Failed to check TTS availability:', error);
            this.available = false;
        }
        refreshAllTTSButtons();
        return this.available;
    }

    extractPlainText(content) {
        // Strip thinking/reasoning first — never speak CoT, only the reply
        let cleaned = stripThinkingForSpeech(content);
        if (!cleaned) return '';

        // Strip markdown horizontal rules (same rule as markdown.js)
        cleaned = cleaned.replace(/^(?:---|\*\*\*|___)\s*$/gm, '');

        // Create a temporary div to parse HTML/markdown
        const temp = document.createElement('div');
        temp.innerHTML = cleaned;

        // Remove code blocks, rendered horizontal rules, and any thinking UI
        // that leaked in via body textContent fallbacks
        temp.querySelectorAll('pre, code, hr, .thinking-section').forEach(el => el.remove());

        // Get text content
        let text = temp.textContent || temp.innerText || '';

        // Clean up markdown syntax
        text = text
            .replace(/#{1,6}\s/g, '') // Remove headers
            .replace(/\*\*(.+?)\*\*/g, '$1') // Remove bold
            .replace(/\*(.+?)\*/g, '$1') // Remove italic
            .replace(/\[(.+?)\]\(.+?\)/g, '$1') // Remove links
            .replace(/`(.+?)`/g, '$1') // Remove inline code
            .replace(/^(?:---|\*\*\*|___)\s*$/gm, '') // Horizontal rules (safety pass)
            .replace(/\n{3,}/g, '\n\n') // Normalize line breaks
            .trim();

        return text;
    }

    _splitParagraphs(plainText) {
        if (!plainText) return [];
        const parts = plainText.split(/\n\s*\n+/).map((p) => p.trim()).filter(Boolean);
        if (parts.length) return parts;
        const single = plainText.trim();
        return single ? [single] : [];
    }

    _paragraphIndexForOffset(plainText, offset) {
        const paragraphs = this._splitParagraphs(plainText);
        if (paragraphs.length <= 1) return 0;
        let pos = 0;
        for (let i = 0; i < paragraphs.length; i++) {
            const idx = plainText.indexOf(paragraphs[i], pos);
            if (idx < 0) continue;
            const end = idx + paragraphs[i].length;
            if (offset <= end) return i;
            pos = end;
        }
        return paragraphs.length - 1;
    }

    _canSkip() {
        if (!this._processing || this._queue.length < 2) return false;
        const current = this._queue[0]?.paragraphIndex ?? 0;
        return this._queue.some((item, i) => i > 0 && (item.paragraphIndex ?? 0) > current);
    }

    _updateSkipButton() {
        const item = this._queue[0];
        const playBtn = item?.button;
        if (!playBtn) return;
        const skipBtn = playBtn.parentElement?.querySelector('.ai-tts-skip-btn');
        if (!skipBtn) return;
        const show = this._canSkip();
        skipBtn.classList.toggle('hidden', !show);
        skipBtn.disabled = !show;
    }

    _hideSkipButton() {
        document.querySelectorAll('.ai-tts-skip-btn').forEach((btn) => {
            btn.classList.add('hidden');
            btn.disabled = true;
        });
    }

    _stopCurrentPlayback() {
        emitVoiceSpeaking(false);
        if (this.useBrowserTTS) {
            window.speechSynthesis.cancel();
            this.isPlaying = false;
        }
        if (this.currentAudio) {
            const audio = this.currentAudio;
            this.currentAudio = null;
            this.isPlaying = false;
            audio.pause();
            audio.currentTime = 0;
        }
    }

    skipToNext() {
        if (!this._canSkip()) return;
        const currentPara = this._queue[0]?.paragraphIndex ?? 0;
        this._skipToParagraph = currentPara + 1;
        if (this._synthAbort) {
            try { this._synthAbort.abort(); } catch (_) { /* ignore */ }
            this._synthAbort = null;
        }
        this._stopCurrentPlayback();
    }

    getCacheKey(text) {
        // Simple hash function for cache key
        let hash = 0;
        for (let i = 0; i < text.length; i++) {
            const char = text.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return hash.toString(36);
    }

    async synthesize(text, onProgress = null) {
        if (!this.available) {
            throw new Error('AI TTS service not available');
        }

        const plainText = this.extractPlainText(text);

        if (!plainText) {
            throw new Error('No text to synthesize');
        }

        // Browser TTS doesn't use synthesize — handled directly in play()
        if (this.useBrowserTTS) {
            return '__browser_tts__';
        }

        const cacheKey = this.getCacheKey(plainText);

        // Check cache first
        if (this.cache.has(cacheKey)) {
            return this.cache.get(cacheKey);
        }

        if (this._synthAbort) {
            try { this._synthAbort.abort(); } catch (_) { /* ignore */ }
        }
        const controller = new AbortController();
        this._synthAbort = controller;
        const timeoutId = setTimeout(() => controller.abort(), SYNTH_TIMEOUT_MS);

        try {
            if (onProgress) onProgress('synthesizing');

            const response = await fetch('/api/tts/synthesize', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    text: plainText,
                    format: 'audio'
                }),
                signal: controller.signal,
            });

            if (!response.ok) {
                let message = 'Synthesis failed';
                try {
                    const error = await response.json();
                    const detail = error?.detail;
                    if (typeof detail === 'string') message = detail;
                    else if (detail?.message) message = detail.message;
                    else if (error?.message) message = error.message;
                } catch (_) {
                    message = `Synthesis failed (${response.status})`;
                }
                throw new Error(message);
            }

            const audioBlob = await response.blob();
            if (!audioBlob || audioBlob.size === 0) {
                throw new Error('TTS returned empty audio');
            }
            const audioUrl = URL.createObjectURL(audioBlob);

            // Cache the result
            this.cache.set(cacheKey, audioUrl);

            if (onProgress) onProgress('complete');

            return audioUrl;

        } catch (error) {
            if (onProgress) onProgress('error');
            throw error;
        } finally {
            clearTimeout(timeoutId);
            if (this._synthAbort === controller) this._synthAbort = null;
        }
    }

    _findBrowserVoice() {
        if (!this.browserVoice) return null;
        const voices = window.speechSynthesis.getVoices();
        const target = this.browserVoice.toLowerCase();
        // Try exact match first, then partial
        return voices.find(v => v.name.toLowerCase() === target) ||
               voices.find(v => v.name.toLowerCase().includes(target)) ||
               null;
    }

    async play(text) {
        // Stop current audio if playing
        this.stop();
        const epoch = this._playEpoch;

        const plainText = this.extractPlainText(text);
        if (!plainText) return;

        if (this.useBrowserTTS) {
            return this._playBrowser(plainText);
        }

        try {
            const audioUrl = await this.synthesize(text);
            if (epoch !== this._playEpoch) return;

            const audio = this._getSharedAudio();
            audio.src = audioUrl;
            if (this._provider === 'local' && this.playbackSpeed !== 1) {
                audio.playbackRate = this.playbackSpeed;
            }
            this.currentAudio = audio;
            await applySinkToMediaElement(audio);
            if (epoch !== this._playEpoch) return;
            await audio.play();
            if (epoch !== this._playEpoch) return;
            _emitFirstAudioOut('server');
            this.isPlaying = true;
            emitVoiceSpeaking(true);
        } catch (error) {
            console.error('Failed to play audio:', error);
            throw error;
        }
    }

    _playBrowser(plainText) {
        return new Promise((resolve, reject) => {
            const utterance = new SpeechSynthesisUtterance(plainText);
            const voice = this._findBrowserVoice();
            if (voice) utterance.voice = voice;
            utterance.rate = this.playbackSpeed;

            utterance.onend = () => {
                this.isPlaying = false;
                emitVoiceSpeaking(false);
                resolve();
            };
            utterance.onerror = (e) => {
                this.isPlaying = false;
                emitVoiceSpeaking(false);
                reject(new Error('Browser TTS error: ' + e.error));
            };

            window.speechSynthesis.speak(utterance);
            _emitFirstAudioOut('browser');
            this.isPlaying = true;
            emitVoiceSpeaking(true);
        });
    }

    stop() {
        this._playEpoch += 1;
        emitVoiceSpeaking(false);
        if (this._synthAbort) {
            try { this._synthAbort.abort(); } catch (_) { /* ignore */ }
            this._synthAbort = null;
        }
        // Cancel streaming TTS
        this._streamActive = false;
        if (this._streamDebounceTimer) {
            clearTimeout(this._streamDebounceTimer);
            this._streamDebounceTimer = null;
        }
        this._streamSentencesSent = 0;

        // Clear the entire queue and reset all queued buttons
        for (const item of this._queue) {
            if (item.resetFn) item.resetFn();
        }
        this._queue = [];
        this._processing = false;
        this._skipToParagraph = null;
        this._hideSkipButton();

        if (this.useBrowserTTS) {
            window.speechSynthesis.cancel();
            this.isPlaying = false;
        }
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
            this.isPlaying = false;
        }
        window.dispatchEvent(new CustomEvent('odysseus:tts-idle'));
    }

    /**
     * Enqueue a message for auto-play. Long messages are split into paragraphs
     * so skip can advance by paragraph. Stopping any message clears the queue.
     */
    enqueue(text, button, resetFn, opts = {}) {
        if (opts.noSplit) {
            this._queue.push({
                text,
                button,
                resetFn,
                paragraphIndex: opts.paragraphIndex ?? 0,
            });
        } else {
            const plain = this.extractPlainText(text);
            const paragraphs = this._splitParagraphs(plain);
            const parts = paragraphs.length > 1 ? paragraphs : [text];
            const isSeries = parts.length > 1;
            parts.forEach((part, i) => {
                this._queue.push({
                    text: part,
                    button,
                    resetFn,
                    paragraphIndex: i,
                    isPartOfSeries: isSeries,
                    isLastInSeries: isSeries && i === parts.length - 1,
                });
            });
        }
        this._updateSkipButton();
        if (!this._processing) {
            this._processQueue();
        }
    }

    async _processQueue() {
        if (this._processing) return;
        this._processing = true;
        const epoch = this._playEpoch;

        while (this._queue.length > 0) {
            const item = this._queue[0];
            try {
                await this._playQueueItem(item, epoch);
            } catch (err) {
                console.error('TTS queue item error:', err);
                if (this._playEpoch !== epoch) {
                    // User stopped — swallow
                } else if (err?.name === 'AbortError') {
                    // Skip aborts in-flight synth on purpose; bare AbortError is a timeout
                    if (this._skipToParagraph == null) {
                        _toastTtsError(new Error('TTS timed out'));
                    }
                } else {
                    _toastTtsError(err);
                }
            }
            if (this._queue.length > 0 && this._queue[0] === item) {
                this._queue.shift();
            }
            if (this._skipToParagraph != null) {
                while (this._queue.length > 0 && (this._queue[0].paragraphIndex ?? 0) < this._skipToParagraph) {
                    this._queue.shift();
                }
                this._skipToParagraph = null;
            }
            this._updateSkipButton();
            if (!this._processing || this._playEpoch !== epoch) return;
        }

        this._processing = false;
        this._hideSkipButton();
        window.dispatchEvent(new CustomEvent('odysseus:tts-idle'));
    }

    async _playQueueItem(item, epoch = this._playEpoch) {
        const { text, button, resetFn } = item;
        const ICON_LOADING = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="9" stroke-dasharray="42" stroke-dashoffset="12" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/></circle></svg>';
        var ICON_STOP = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>';

        button.innerHTML = ICON_LOADING;
        button.classList.add('loading');
        button.style.color = '#ccc';
        button.title = 'Loading...';

        try {
            if (!this._isLive(epoch)) return;

            const audioUrl = await this.synthesize(text);

            if (!this._isLive(epoch) || this._skipToParagraph != null) return;

            button.innerHTML = ICON_STOP;
            button.classList.remove('loading');
            button.classList.add('playing');
            button.title = 'Stop';
            this._updateSkipButton();

            if (this.useBrowserTTS) {
                const plainText = this.extractPlainText(text);
                await this._playBrowser(plainText);
            } else {
                // Reuse the single blessed <audio> element so iOS keeps
                // allowing programmatic playback after the initial gesture.
                const audio = this._getSharedAudio();
                audio.pause();
                if (this._provider === 'local' && this.playbackSpeed !== 1) {
                    audio.playbackRate = this.playbackSpeed;
                } else {
                    audio.playbackRate = 1;
                }
                this.currentAudio = audio;

                await new Promise((resolve, reject) => {
                    const cleanup = () => {
                        audio.onended = null;
                        audio.onerror = null;
                        audio.onpause = null;
                    };
                    audio.onended = () => {
                        cleanup();
                        this.isPlaying = false;
                        if (this.currentAudio === audio) this.currentAudio = null;
                        emitVoiceSpeaking(false);
                        resolve();
                    };
                    audio.onerror = () => {
                        cleanup();
                        this.isPlaying = false;
                        if (this.currentAudio === audio) this.currentAudio = null;
                        emitVoiceSpeaking(false);
                        reject(new Error('Audio playback error'));
                    };
                    audio.onpause = () => {
                        // Resolve when stop() (or a new item) took over playback.
                        if (this.currentAudio !== audio) {
                            cleanup();
                            emitVoiceSpeaking(false);
                            resolve();
                        }
                    };
                    audio.src = audioUrl;
                    applySinkToMediaElement(audio).then(() => {
                        if (!this._isLive(epoch) || this.currentAudio !== audio) {
                            resolve();
                            return;
                        }
                        return audio.play();
                    }).then(() => {
                        if (!this._isLive(epoch) || this.currentAudio !== audio) {
                            resolve();
                            return;
                        }
                        _emitFirstAudioOut('server');
                        this.isPlaying = true;
                        emitVoiceSpeaking(true);
                    }).catch((err) => {
                        cleanup();
                        reject(err);
                    });
                });
            }
        } finally {
            const cancelled = this._playEpoch !== epoch;
            if (resetFn && (cancelled || !item.isPartOfSeries || item.isLastInSeries)) {
                resetFn();
                this._hideSkipButton();
            }
            this._updateSkipButton();
        }
    }

    // ── Streaming TTS (sentence-by-sentence) ──

    streamingStart() {
        this._streamSentencesSent = 0;
        this._streamActive = true;
        this._streamButton = null;
        this._streamResetFn = null;
    }

    streamingUpdate(accumulatedText) {
        if (!this._streamActive || !this.available || !this.autoPlay) return;
        if (this._streamDebounceTimer) return;
        this._streamDebounceTimer = setTimeout(() => {
            this._streamDebounceTimer = null;
            this._processStreamingSentences(accumulatedText);
        }, 150);
    }

    _processStreamingSentences(accumulatedText) {
        if (!this._streamActive) return;

        var text = accumulatedText
            .replace(/```[\s\S]*?```/g, '')
            .replace(/```[\s\S]*$/g, '');

        var plainText = this.extractPlainText(text);
        if (!plainText || plainText.length <= this._streamSentencesSent) return;

        var newRegion = plainText.substring(this._streamSentencesSent);

        var sentences = this._collectStreamingChunks(newRegion);
        if (sentences.length === 0) return;

        var advancedChars = 0;
        for (var j = 0; j < sentences.length; j++) {
            var sentence = sentences[j].text;
            if (sentence.length < 15) {
                advancedChars += sentences[j].advance;
                continue;
            }
            var btn = this._streamButton || this._createPlaceholderButton();
            var resetFn = this._streamResetFn || function() {};
            var paraIndex = this._paragraphIndexForOffset(plainText, this._streamSentencesSent + advancedChars);
            this.enqueue(sentence, btn, resetFn, { noSplit: true, paragraphIndex: paraIndex });
            advancedChars += sentences[j].advance;
        }

        this._streamSentencesSent += advancedChars;
    }

    _voiceStreamingMode() {
        return !!window.voiceChatModule?.isActive?.();
    }

    _collectStreamingChunks(newRegion) {
        var chunks = [];
        var start = 0;
        var current = '';
        for (var i = 0; i < newRegion.length; i++) {
            current += newRegion[i];
            var ch = newRegion[i];
            var next = newRegion[i + 1];
            if ((ch === '.' || ch === '!' || ch === '?') && next && /\s/.test(next)) {
                var lastWord = current.trim().split(/\s/).pop() || '';
                if (/^\d+\.$/.test(lastWord)) continue;
                if (/^[A-Z][a-z]?\.$/.test(lastWord)) continue;
                chunks.push({ text: current.trim(), advance: i + 1 - start });
                start = i + 1;
                current = '';
            }
        }

        if (chunks.length || !this._voiceStreamingMode()) return chunks;
        if (newRegion.length < VOICE_STREAM_MIN_CHARS + VOICE_STREAM_HOLD_CHARS) return chunks;

        var stableEnd = Math.max(0, newRegion.length - VOICE_STREAM_HOLD_CHARS);
        var earlyBoundary = -1;
        var phrase = newRegion.slice(0, stableEnd);
        var phraseMatch = phrase.match(/[\n,;:]\s+[^\n,;:]*$/);
        if (phraseMatch && phraseMatch.index >= VOICE_STREAM_MIN_CHARS) {
            earlyBoundary = phraseMatch.index + 1;
        }

        if (earlyBoundary < 0 && stableEnd >= VOICE_STREAM_MAX_CHARS) {
            var wordBoundary = phrase.lastIndexOf(' ', VOICE_STREAM_MAX_CHARS);
            if (wordBoundary >= VOICE_STREAM_MIN_CHARS) earlyBoundary = wordBoundary;
        }

        if (earlyBoundary >= VOICE_STREAM_MIN_CHARS) {
            chunks.push({
                text: newRegion.slice(0, earlyBoundary + 1).trim(),
                advance: earlyBoundary + 1,
            });
        }
        return chunks;
    }

    _createPlaceholderButton() {
        var btn = document.createElement('button');
        btn.style.display = 'none';
        btn.className = 'ai-tts-button streaming-placeholder';
        return btn;
    }

    streamingAttachButton(button, resetFn) {
        this._streamButton = button;
        this._streamResetFn = resetFn;
        for (var i = 0; i < this._queue.length; i++) {
            if (this._queue[i].button && this._queue[i].button.classList.contains('streaming-placeholder')) {
                this._queue[i].button = button;
                this._queue[i].resetFn = resetFn;
            }
        }
    }

    streamingEnd(finalText) {
        if (!this._streamActive) return;
        this._streamActive = false;
        if (this._streamDebounceTimer) {
            clearTimeout(this._streamDebounceTimer);
            this._streamDebounceTimer = null;
        }

        var text = finalText
            .replace(/```[\s\S]*?```/g, '')
            .replace(/```[\s\S]*$/g, '');

        var plainText = this.extractPlainText(text);
        if (!plainText) return;

        var remaining = plainText.substring(this._streamSentencesSent).trim();
        if (remaining.length >= 15) {
            var btn = this._streamButton || this._createPlaceholderButton();
            var resetFn = this._streamResetFn || function() {};
            var paraIndex = this._paragraphIndexForOffset(plainText, this._streamSentencesSent);
            this.enqueue(remaining, btn, resetFn, { noSplit: true, paragraphIndex: paraIndex });
        }
        this._streamSentencesSent = 0;
    }

    clearCache() {
        for (const url of this.cache.values()) {
            URL.revokeObjectURL(url);
        }
        this.cache.clear();
    }
}

// A short valid silent WAV (data URI) used only to "bless" the shared <audio>
// element during a user gesture on iOS/Safari. Playing real audio afterwards
// then works without a NotAllowedError.
AITTSManager.SILENT_AUDIO = 'data:audio/wav;base64,UklGRkQDAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YSADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==';

// Create global AI TTS manager instance
window.aiTTSManager = new AITTSManager();

function _messageTtsText(messageElement) {
    if (messageElement.dataset.raw) return messageElement.dataset.raw;
    const body = messageElement.querySelector('.body');
    if (!body) return '';
    // Exclude collapsible thinking UI — textContent would otherwise include it
    const clone = body.cloneNode(true);
    clone.querySelectorAll('.thinking-section').forEach((el) => el.remove());
    return clone.textContent || '';
}

/** Add read-aloud buttons to all assistant messages missing one. */
export function refreshAllTTSButtons(root) {
    const mgr = window.aiTTSManager;
    if (!mgr?.available || mgr._provider === 'disabled') return;
    const scope = root || document;
    scope.querySelectorAll('.msg-ai').forEach((wrap) => {
        if (wrap.querySelector('.msg-tts-play-btn')) {
            const actions = wrap.querySelector('.msg-actions');
            const ttsBtn = wrap.querySelector('.msg-tts-play-btn');
            if (actions && ttsBtn && actions.firstChild !== ttsBtn) {
                actions.insertBefore(ttsBtn, actions.firstChild);
            }
            if (ttsBtn && !wrap.querySelector('.ai-tts-skip-btn')) {
                ttsBtn.parentElement?.insertBefore(_createSkipButton(), ttsBtn.nextSibling);
            }
            return;
        }
        const text = _messageTtsText(wrap);
        if (text.trim()) addAITTSButton(wrap, text);
    });
}

/** Attach TTS to one message; waits for availability check if still in flight. */
export function ensureTTSButton(messageElement, text) {
    const content = (text || _messageTtsText(messageElement)).trim();
    if (!content) return;
    const mgr = window.aiTTSManager;
    if (!mgr) return;

    const attach = () => {
        if (mgr.available && mgr._provider !== 'disabled') {
            addAITTSButton(messageElement, content);
        }
    };

    attach();
    if (!messageElement.querySelector('.msg-tts-play-btn')) {
        (mgr._readyPromise || mgr.checkAvailability()).then(attach);
    }
}

// Function to add AI TTS button to a message element's action bar
function _createSkipButton() {
    var ICON_SKIP = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="5 4 15 12 5 20 5 4"/><rect x="17" y="4" width="3" height="16" rx="1"/></svg>';
    const skipButton = document.createElement('button');
    skipButton.className = 'ai-tts-button ai-tts-skip-btn msg-tts-skip-btn hidden';
    skipButton.type = 'button';
    skipButton.title = 'Skip to next paragraph';
    skipButton.setAttribute('aria-label', 'Skip to next paragraph');
    skipButton.innerHTML = ICON_SKIP;
    skipButton.disabled = true;
    skipButton.style.cssText = 'background:none;border:none;color:#6b7280;cursor:pointer;padding:2px 6px;border-radius:4px;transition:color .15s;line-height:1;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;';
    skipButton.addEventListener('mouseenter', () => { if (!skipButton.disabled) skipButton.style.color = '#ccc'; });
    skipButton.addEventListener('mouseleave', () => {
        if (!skipButton.disabled) skipButton.style.color = '#6b7280';
    });
    skipButton.addEventListener('click', (e) => {
        e.stopPropagation();
        window.aiTTSManager?.skipToNext();
    });
    return skipButton;
}

export function addAITTSButton(messageElement, text) {
    if (!window.aiTTSManager.available || window.aiTTSManager._provider === 'disabled') {
        return;
    }

    if (messageElement.querySelector('.msg-tts-play-btn')) {
        if (!messageElement.querySelector('.ai-tts-skip-btn')) {
            const existingPlay = messageElement.querySelector('.msg-tts-play-btn');
            existingPlay.parentElement?.insertBefore(_createSkipButton(), existingPlay.nextSibling);
        }
        return;
    }

    // Find the msg-actions container in the footer
    const actions = messageElement.querySelector('.msg-actions');
    if (!actions) return;

    var ICON_PLAY = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><polygon points="6 3 20 12 6 21 6 3"/></svg>';
    var ICON_STOP = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="5" y="5" width="14" height="14" rx="2"/></svg>';
    var ICON_LOADING = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="9" stroke-dasharray="42" stroke-dashoffset="12" stroke-linecap="round"><animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="0.8s" repeatCount="indefinite"/></circle></svg>';

    const skipButton = _createSkipButton();

    const playButton = document.createElement('button');
    playButton.className = 'ai-tts-button msg-tts-play-btn';
    playButton.type = 'button';
    playButton.title = 'Read aloud';
    playButton.setAttribute('aria-label', 'Read aloud');
    playButton.innerHTML = ICON_PLAY;
    playButton.style.cssText = 'background:none;border:none;color:#6b7280;cursor:pointer;padding:2px 6px;border-radius:4px;transition:color .15s;line-height:1;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;';

    playButton.addEventListener('mouseenter', () => { playButton.style.color = '#ccc'; });
    playButton.addEventListener('mouseleave', () => {
        if (!playButton.classList.contains('playing') && !playButton.classList.contains('loading')) playButton.style.color = '#6b7280';
    });

    function resetButton() {
        playButton.innerHTML = ICON_PLAY;
        playButton.classList.remove('playing', 'loading');
        playButton.style.color = '#6b7280';
        playButton.title = 'Read aloud';
    }

    playButton.addEventListener('click', async (e) => {
        e.stopPropagation();
        const mgr = window.aiTTSManager;
        if (!mgr) return;

        // Unlock audio synchronously inside this tap so iOS Safari will allow
        // the deferred play() that happens after the synth network request.
        mgr.unlockAudio();

        if (mgr.isPlaying || mgr._processing) {
            mgr.stop();
            resetButton();
            return;
        }

        // Prefer live message text — closed-over text can be stale for continuations
        const fresh = (_messageTtsText(messageElement) || text || '').trim();
        if (!fresh) {
            _toastTtsError(new Error('No text to read'));
            return;
        }
        mgr.enqueue(fresh, playButton, resetButton);
    });

    actions.insertBefore(playButton, actions.firstChild);
    actions.insertBefore(skipButton, playButton.nextSibling);
}

// Stop audio when navigating away
window.addEventListener('beforeunload', () => {
    if (window.aiTTSManager) {
        window.aiTTSManager.stop();
    }
});

export { AITTSManager };

const ttsModule = { AITTSManager, addAITTSButton, ensureTTSButton, refreshAllTTSButtons };
export default ttsModule;
