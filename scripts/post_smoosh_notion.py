#!/usr/bin/env python3
"""Post Smoosh research summary to Notion page via API key from .env."""
from __future__ import annotations

import json
import os
import urllib.request

PAGE_ID = "441855ec1f424265886679dddb8b129a"
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")


def load_notion_key() -> str:
    candidates = [
        os.path.join(os.path.dirname(__file__), "..", "..", "research-agent", ".env"),
        ENV_PATH,
    ]
    for path in candidates:
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith(("NOTION_API_KEY=", "NOTION_TOKEN=")):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("NOTION_API_KEY/NOTION_TOKEN not found")


def rt(text: str, *, link: str | None = None) -> dict:
    payload: dict = {"type": "text", "text": {"content": text}}
    if link:
        payload["text"]["link"] = {"url": link}
    return payload


def main() -> int:
    key = load_notion_key()
    children = [
        {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [rt("Smoosh AI CTO — Research Swarm (2026-07-12)")]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
            rt("Session: "), rt("rp-smoosh-ai-20260712", link="http://localhost:7000/api/research/report/rp-smoosh-ai-20260712"),
        ]}},
        {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [rt("smoosh.dev = calendar scheduling SaaS (Google Calendar OAuth, Clerk, PlanetScale, Vercel) — not generative AI on the public site today.")]}},
        {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [rt("Smoosh AI ↔ smoosh.dev identity unconfirmed. Brand collision with smoosh.app (fan data) and Rwanda registry (gen-AI/CV).")]}},
        {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [rt("Revised fit: 4/5 for founding CTO (integrations, OAuth, early-stage SaaS). Ask Janice discovery questions before gen-AI claims.")]}},
        {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [rt("Pipeline: job-application-ops/positions/_active/SmooshAI_CTO_2026-07 — cover letter + resume PDF ready.")]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [rt("Apply: Reply to Janice Nam on Handshake (UID 19f3f173ddb843a8). Paste cover letter, attach PDF. User sends manually.")]}},
        {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [rt("Full report orch: SmooshAI_CTO_2026-07/_orch/master_report.md")]}},
    ]
    body = json.dumps({"children": children}).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.notion.com/v1/blocks/441855ec-1f42-4265-8866-79dddb8b129a/children",
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {key}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    print(f"NOTION ok blocks={len(result.get('results', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
