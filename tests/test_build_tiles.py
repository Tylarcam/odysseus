"""Tests for Screenpipe → PixelRAG tile builder."""

from __future__ import annotations

import json
from pathlib import Path

from tools.build_tiles import build_tiles


def _write_png(path: Path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)


def test_build_tiles_creates_pixelrag_layout_and_metadata(tmp_path):
    screens = tmp_path / "screens"
    transcripts = tmp_path / "transcripts"
    index_dir = tmp_path / "my_index"
    tiles = index_dir / "tiles"
    metadata_path = tmp_path / "tiles_metadata.json"
    screens.mkdir()
    transcripts.mkdir()

    names = [
        "screen_2026-07-07T01-05-00.png",
        "screen_2026-07-07T01-06-00.png",
        "screen_2026-07-07T01-07-00.png",
    ]
    for name in names:
        _write_png(screens / name)

    (transcripts / "2026-07-07.json").write_text(
        json.dumps(
            {
                "timestamp": "2026-07-07T01:05:00",
                "url": "https://github.com/StarTrail-org/PixelRAG",
                "window_title": "PixelRAG — GitHub",
            }
        ),
        encoding="utf-8",
    )

    metadata = build_tiles(
        screens_dir=screens,
        tiles_dir=tiles,
        index_dir=index_dir,
        transcripts_dir=transcripts,
        metadata_path=metadata_path,
    )

    assert len([k for k in metadata if k.isdigit()]) == 3
    assert metadata_path.is_file()
    articles = json.loads((index_dir / "articles.json").read_text(encoding="utf-8"))
    assert len(articles) == 3

    for article_id, name in enumerate(names):
        article_dir = tiles / f"{article_id}.png.tiles"
        assert (article_dir / "tile_0000.png").is_file()
        manifest = json.loads((article_dir / "tiles.json").read_text(encoding="utf-8"))
        assert manifest["tiles"] == ["tile_0000.png"]
        assert manifest["complete"] is True

        assert name in metadata
        assert metadata[str(article_id)]["article_id"] == article_id
        assert metadata[name]["timestamp"].startswith("2026-07-07")
        assert metadata[name]["screenpipe_path"]

    first = metadata[names[0]]
    assert first["url"] == "https://github.com/StarTrail-org/PixelRAG"
    assert first["window_title"] == "PixelRAG — GitHub"
