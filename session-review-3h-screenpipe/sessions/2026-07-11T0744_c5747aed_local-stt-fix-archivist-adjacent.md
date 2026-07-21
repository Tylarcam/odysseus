# Local STT fix (archivist-adjacent)

| Field | Value |
|-------|-------|
| **Session ID** | `c5747aed-4e05-444a-b10a-2251cae2c6f2` |
| **Project** | odysseus |
| **When** | 2026-07-11T07:44 |
| **Size** | 98.8 KB · 7 user turns |
| **Theme** | Voice / Local Whisper STT — archivist boot nearby |
| **Status** | Shipped (STT); Screenpipe not the primary task |
| **Resume** | `agent --resume="c5747aed-4e05-444a-b10a-2251cae2c6f2"` |
| **Transcript** | `%USERPROFILE%\.cursor\projects\c-Users-tylar-code-odysseus\agent-transcripts\c5747aed-4e05-444a-b10a-2251cae2c6f2\c5747aed-4e05-444a-b10a-2251cae2c6f2.jsonl` |

## Summary

Fixed Odysseus Local STT (faster-whisper in Docker via `INSTALL_STT`). End-chat saved Odysseus note + AgentMemory; archivist `POST /remember` returned 200 on `:40001` during this window. Same morning terminal ran `start-archivist.ps1` screen-only boot + export.

## Outcomes

- Local STT available in container path
- Archivist remember path exercised (`mem-2db23e9e`)
- Screenpipe started screen-only (`windows-native` OCR, `--disable-audio`); export reported 100 rows / 78 frames / 950 tiles; FAISS rebuild skipped

## Actionable follow-ups

- [ ] Confirm STT green in Settings live QA (from end-session next steps)
- [ ] Treat archivist boot as ops debt: `:3030` and `:30001` later went down while `:40001` stayed up

## Concepts

- Voice stack (Realtime vs PTT STT→LLM→TTS) separate from Screenpipe mic
- Screen-only Screenpipe protects Clicky/Odysseus voice

## Ready-to-paste prompts

1. `Verify Odysseus Settings → Audio STT green after INSTALL_STT image. Do not touch Screenpipe.`

## Missed / under-captured (reviewer callouts)

- ⚠️ Session is STT-primary; Screenpipe signal is from adjacent terminal boot, not chat work

## Original user queries

### Q1

/problem-statement (Local STT unavailable)

### Q5–Q6

Fix Local STT / implement plan

## Assistant digest (truncated)

Session closed with Odysseus note `7288c2b1…` and AgentMemory. Next: live QA Settings STT status.
