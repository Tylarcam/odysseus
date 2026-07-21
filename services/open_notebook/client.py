"""Minimal async client for the Open Notebook REST API.

Only covers what the document "Listen" audio brief needs:
  - ensure a single-narrator speaker profile + episode profile exist
  - submit a podcast generation job with inline content (no notebook needed)
  - poll the job and download the finished MP3

API shape verified against lfnovo/open-notebook main (api/routers/podcasts.py,
episode_profiles.py, speaker_profiles.py, api/auth.py). Auth is a simple
Bearer password; profiles must reference Open Notebook's model registry, so
we resolve the instance's configured default models when creating them.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

import httpx

from src.constants import (
    OPEN_NOTEBOOK_PASSWORD,
    OPEN_NOTEBOOK_URL,
    OPEN_NOTEBOOK_VOICE_ID,
)

logger = logging.getLogger(__name__)

SPEAKER_PROFILE_NAME = "odysseus-brief-narrator"
EPISODE_PROFILE_NAME = "odysseus-executive-brief"

# One narrator reading a report — explicitly NOT a two-host podcast.
_NARRATOR_BRIEFING = (
    "This is a single-voice executive audio report, not a conversational "
    "podcast. One narrator reads a CEO-level brief aloud. No banter, no "
    "interviews, no second speaker, no intro music cues. Deliver the "
    "provided brief content faithfully in a clear, confident, boardroom "
    "tone: lead with the executive summary, then key concepts and points, "
    "then next steps. Do not invent facts beyond the provided content."
)

_TERMINAL_OK = {"completed", "success", "succeeded"}
_TERMINAL_FAIL = {"failed", "error", "cancelled", "canceled"}


class OpenNotebookError(RuntimeError):
    """Raised for any Open Notebook API failure (config, HTTP, job errors)."""


def open_notebook_configured() -> bool:
    return bool(OPEN_NOTEBOOK_URL)


class OpenNotebookClient:
    def __init__(
        self,
        base_url: str = "",
        password: str = "",
        timeout: float = 30.0,
    ):
        self.base_url = (base_url or OPEN_NOTEBOOK_URL).rstrip("/")
        self.password = password if password else OPEN_NOTEBOOK_PASSWORD
        self.timeout = timeout
        if not self.base_url:
            raise OpenNotebookError("OPEN_NOTEBOOK_URL is not configured")

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.password:
            headers["Authorization"] = f"Bearer {self.password}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        json_body: Optional[dict] = None,
        expect_bytes: bool = False,
        timeout: Optional[float] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout) as client:
                resp = await client.request(
                    method, url, json=json_body, headers=self._headers()
                )
        except httpx.HTTPError as e:
            raise OpenNotebookError(f"Open Notebook unreachable at {url}: {e}") from e
        if resp.status_code == 404:
            return None
        if resp.status_code >= 400:
            detail = ""
            try:
                detail = resp.json().get("detail") or ""
            except Exception:
                detail = resp.text[:300]
            raise OpenNotebookError(
                f"Open Notebook {method} {path} failed ({resp.status_code}): {detail}"
            )
        return resp.content if expect_bytes else resp.json()

    # ── Profiles ─────────────────────────────────────────────────────

    async def _default_models(self) -> Dict[str, Any]:
        defaults = await self._request("GET", "/api/models/defaults")
        return defaults or {}

    async def ensure_profiles(self) -> Tuple[str, str]:
        """Get-or-create the single-narrator speaker + episode profiles.

        Returns (episode_profile_name, speaker_profile_name).
        """
        speaker = await self._request(
            "GET", f"/api/speaker-profiles/{SPEAKER_PROFILE_NAME}"
        )
        episode = await self._request(
            "GET", f"/api/episode-profiles/{EPISODE_PROFILE_NAME}"
        )
        if speaker and episode:
            return EPISODE_PROFILE_NAME, SPEAKER_PROFILE_NAME

        defaults = await self._default_models()
        tts_model = defaults.get("default_text_to_speech_model")
        chat_model = (
            defaults.get("default_transformation_model")
            or defaults.get("default_chat_model")
            or defaults.get("large_context_model")
        )
        if not speaker:
            if not tts_model:
                raise OpenNotebookError(
                    "Open Notebook has no default text-to-speech model configured "
                    "— set one under Settings > Models in Open Notebook"
                )
            await self._request(
                "POST",
                "/api/speaker-profiles",
                json_body={
                    "name": SPEAKER_PROFILE_NAME,
                    "description": "Single narrator for Odysseus executive audio briefs",
                    "voice_model": tts_model,
                    "speakers": [
                        {
                            "name": "Narrator",
                            "voice_id": OPEN_NOTEBOOK_VOICE_ID,
                            "backstory": (
                                "A seasoned executive communications professional "
                                "who delivers concise briefings to leadership."
                            ),
                            "personality": (
                                "Calm, clear, authoritative and efficient. Reads "
                                "reports verbatim in spirit, never chatty."
                            ),
                        }
                    ],
                },
            )
        if not episode:
            if not chat_model:
                raise OpenNotebookError(
                    "Open Notebook has no default chat/transformation model "
                    "configured — set one under Settings > Models in Open Notebook"
                )
            await self._request(
                "POST",
                "/api/episode-profiles",
                json_body={
                    "name": EPISODE_PROFILE_NAME,
                    "description": (
                        "Odysseus CEO-level brief — one narrator reads an "
                        "executive audio report (not a two-host podcast)"
                    ),
                    "speaker_config": SPEAKER_PROFILE_NAME,
                    "outline_llm": chat_model,
                    "transcript_llm": chat_model,
                    "default_briefing": _NARRATOR_BRIEFING,
                    # Minimum allowed; keeps the report tight and linear.
                    "num_segments": 3,
                },
            )
        return EPISODE_PROFILE_NAME, SPEAKER_PROFILE_NAME

    # ── Podcast generation ───────────────────────────────────────────

    async def submit_brief_audio(self, episode_name: str, content: str) -> str:
        """Submit a generation job for the brief text. Returns job id."""
        episode_profile, speaker_profile = await self.ensure_profiles()
        resp = await self._request(
            "POST",
            "/api/podcasts/generate",
            json_body={
                "episode_profile": episode_profile,
                "speaker_profile": speaker_profile,
                "episode_name": episode_name,
                "content": content,
            },
        )
        if not resp or not resp.get("job_id"):
            raise OpenNotebookError("Open Notebook did not return a job id")
        return str(resp["job_id"])

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        job = await self._request("GET", f"/api/podcasts/jobs/{job_id}")
        if job is None:
            raise OpenNotebookError(f"Podcast job {job_id} not found")
        return job

    async def wait_for_job(
        self,
        job_id: str,
        timeout_s: float = 900.0,
        poll_s: float = 5.0,
    ) -> Dict[str, Any]:
        """Poll until the job reaches a terminal state. Returns result dict."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_s
        while True:
            job = await self.get_job(job_id)
            status = str(job.get("status") or "").lower()
            if status in _TERMINAL_OK:
                return job.get("result") or {}
            if status in _TERMINAL_FAIL:
                raise OpenNotebookError(
                    job.get("error_message")
                    or f"Podcast generation {status} (job {job_id})"
                )
            if loop.time() > deadline:
                raise OpenNotebookError(
                    f"Timed out after {int(timeout_s)}s waiting for podcast job {job_id}"
                )
            await asyncio.sleep(poll_s)

    async def download_episode_audio(self, episode_id: str) -> bytes:
        data = await self._request(
            "GET",
            f"/api/podcasts/episodes/{episode_id}/audio",
            expect_bytes=True,
            timeout=120.0,
        )
        if not data:
            raise OpenNotebookError(f"Episode {episode_id} has no audio")
        return data

    async def generate_brief_audio(
        self,
        episode_name: str,
        content: str,
        timeout_s: float = 900.0,
    ) -> Tuple[bytes, str]:
        """Full pipeline: submit → wait → download. Returns (mp3_bytes, episode_id)."""
        job_id = await self.submit_brief_audio(episode_name, content)
        result = await self.wait_for_job(job_id, timeout_s=timeout_s)
        episode_id = result.get("episode_id")
        if not episode_id:
            raise OpenNotebookError(
                "Podcast job finished without an episode id "
                f"(job {job_id}, result keys: {sorted(result.keys())})"
            )
        audio = await self.download_episode_audio(str(episode_id))
        return audio, str(episode_id)
