"""Tests for incremental PixelRAG embedding (Task A).

These tests NEVER trigger a real embed run (that takes hours on CPU). The
subprocess embedding call is monkeypatched so we only exercise the diff logic,
shard naming, and orchestration wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from tools import embed_incremental


def _write_png(path: Path) -> None:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)


def _make_tile_dir(tiles_root: Path, article_id: int, chunks: list[dict]) -> Path:
    """Create an N.png.tiles dir with chunk_*.png files and a chunks.json manifest."""
    td = tiles_root / f"{article_id}.png.tiles"
    td.mkdir(parents=True, exist_ok=True)
    manifest = {"chunks": []}
    for c in chunks:
        fname = c["file"]
        _write_png(td / fname)
        manifest["chunks"].append(
            {
                "file": fname,
                "tile_index": c["tile_index"],
                "chunk_index": c["chunk_index"],
                "y_offset": c.get("y_offset", 0),
                "height": c.get("height", 1024),
            }
        )
    (td / "chunks.json").write_text(json.dumps(manifest), encoding="utf-8")
    return td


def _write_shard(path: Path, article_ids, tile_indices, chunk_indices) -> None:
    n = len(article_ids)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        path,
        embeddings=np.zeros((n, 2048), dtype=np.float16),
        article_ids=np.array(article_ids, dtype=np.int64),
        tile_indices=np.array(tile_indices, dtype=np.int32),
        chunk_indices=np.array(chunk_indices, dtype=np.int32),
        y_offsets=np.zeros(n, dtype=np.int32),
        tile_heights=np.zeros(n, dtype=np.int32),
    )


def test_find_missing_items_returns_only_unembedded_chunks(tmp_path):
    tiles = tmp_path / "tiles"
    embeddings = tmp_path / "embeddings"

    # Article 0: 2 chunks, both embedded
    _make_tile_dir(
        tiles,
        0,
        [
            {"file": "chunk_0_0.png", "tile_index": 0, "chunk_index": 0},
            {"file": "chunk_0_1.png", "tile_index": 0, "chunk_index": 1},
        ],
    )
    # Article 1: 2 chunks, both embedded
    _make_tile_dir(
        tiles,
        1,
        [
            {"file": "chunk_0_0.png", "tile_index": 0, "chunk_index": 0},
            {"file": "chunk_0_1.png", "tile_index": 0, "chunk_index": 1},
        ],
    )
    # Article 2: 2 chunks, NOT embedded yet
    _make_tile_dir(
        tiles,
        2,
        [
            {"file": "chunk_0_0.png", "tile_index": 0, "chunk_index": 0},
            {"file": "chunk_0_1.png", "tile_index": 0, "chunk_index": 1},
        ],
    )

    _write_shard(
        embeddings / "shard_000.npz",
        article_ids=[0, 0, 1, 1],
        tile_indices=[0, 0, 0, 0],
        chunk_indices=[0, 1, 0, 1],
    )

    missing = embed_incremental.find_missing_items(tiles, embeddings)

    assert len(missing) == 2
    assert all(item["article_id"] == 2 for item in missing)
    missing_keys = sorted(
        (item["article_id"], item["tile_index"], item["chunk_index"]) for item in missing
    )
    assert missing_keys == [(2, 0, 0), (2, 0, 1)]


def test_find_missing_items_empty_when_up_to_date(tmp_path):
    tiles = tmp_path / "tiles"
    embeddings = tmp_path / "embeddings"

    _make_tile_dir(
        tiles,
        0,
        [{"file": "chunk_0_0.png", "tile_index": 0, "chunk_index": 0}],
    )
    _write_shard(
        embeddings / "shard_000.npz",
        article_ids=[0],
        tile_indices=[0],
        chunk_indices=[0],
    )

    assert embed_incremental.find_missing_items(tiles, embeddings) == []


def test_find_missing_items_handles_empty_embeddings_dir(tmp_path):
    tiles = tmp_path / "tiles"
    embeddings = tmp_path / "embeddings"

    _make_tile_dir(
        tiles,
        0,
        [{"file": "chunk_0_0.png", "tile_index": 0, "chunk_index": 0}],
    )

    missing = embed_incremental.find_missing_items(tiles, embeddings)
    assert len(missing) == 1
    assert missing[0]["article_id"] == 0


def test_next_shard_path_returns_first_free_name(tmp_path):
    embeddings = tmp_path / "embeddings"
    embeddings.mkdir()
    (embeddings / "shard_000.npz").write_bytes(b"fake")
    (embeddings / "shard_002.npz").write_bytes(b"fake")

    assert embed_incremental.next_shard_path(embeddings).name == "shard_001.npz"

    (embeddings / "shard_001.npz").write_bytes(b"fake")
    assert embed_incremental.next_shard_path(embeddings).name == "shard_003.npz"


def test_build_incremental_index_skips_when_up_to_date(tmp_path, monkeypatch, capsys):
    """No missing items -> prints 'up to date', does NOT embed or rebuild index."""
    tiles = tmp_path / "tiles"
    embeddings = tmp_path / "embeddings"
    index_dir = tmp_path / "index"

    _make_tile_dir(
        tiles,
        0,
        [{"file": "chunk_0_0.png", "tile_index": 0, "chunk_index": 0}],
    )
    _write_shard(
        embeddings / "shard_000.npz",
        article_ids=[0],
        tile_indices=[0],
        chunk_indices=[0],
    )

    # Guards: the chunk stage legitimately runs first; only the build-index
    # rebuild must be skipped when there is nothing new to embed.
    def _no_embed(*a, **kw):
        raise AssertionError("embed_items_subprocess should not run when up to date")

    def _allow_chunk_only(args):
        if args and args[0] == "build-index":
            raise AssertionError("build-index should not run when up to date")

    monkeypatch.setattr(embed_incremental, "embed_items_subprocess", _no_embed)
    monkeypatch.setattr(embed_incremental, "_run_pixelrag_cli", _allow_chunk_only)
    monkeypatch.setattr(embed_incremental, "resolve_pixelrag_python", lambda: "python")

    result = embed_incremental.build_incremental_index(
        tiles_dir=tiles,
        index_dir=index_dir,
        embeddings_dir=embeddings,
    )

    assert result is None
    assert "up to date" in capsys.readouterr().out


def test_build_incremental_index_embeds_missing_and_rebuilds(tmp_path, monkeypatch):
    """Missing items -> calls embed worker once, then rebuilds the FAISS index."""
    tiles = tmp_path / "tiles"
    embeddings = tmp_path / "embeddings"
    index_dir = tmp_path / "index"

    _make_tile_dir(
        tiles,
        0,
        [{"file": "chunk_0_0.png", "tile_index": 0, "chunk_index": 0}],
    )
    _make_tile_dir(
        tiles,
        1,
        [{"file": "chunk_0_1.png", "tile_index": 0, "chunk_index": 0}],
    )
    _write_shard(
        embeddings / "shard_000.npz",
        article_ids=[0],
        tile_indices=[0],
        chunk_indices=[0],
    )

    embed_calls: list[tuple] = []
    build_calls: list[list[str]] = []

    def fake_embed(items, output_npz, *, model, device, python_exe=None):
        embed_calls.append((len(items), str(output_npz), model, device))
        # Simulate the worker writing a shard with the missing ids.
        _write_shard(
            output_npz,
            article_ids=[it["article_id"] for it in items],
            tile_indices=[it["tile_index"] for it in items],
            chunk_indices=[it["chunk_index"] for it in items],
        )
        return output_npz

    def fake_cli(args):
        build_calls.append(list(args))

    monkeypatch.setattr(embed_incremental, "embed_items_subprocess", fake_embed)
    monkeypatch.setattr(embed_incremental, "_run_pixelrag_cli", fake_cli)
    monkeypatch.setattr(embed_incremental, "resolve_pixelrag_python", lambda: "python")

    result = embed_incremental.build_incremental_index(
        tiles_dir=tiles,
        index_dir=index_dir,
        embeddings_dir=embeddings,
        model="Qwen/Qwen3-VL-Embedding-2B",
        device="cpu",
    )

    assert result == index_dir
    assert len(embed_calls) == 1
    assert embed_calls[0][0] == 1  # only article 1's chunk
    assert embed_calls[0][1].endswith("shard_001.npz")
    # First build call is the chunk stage; second is build-index build.
    assert any(a[:2] == ["build-index", "build"] for a in build_calls)
