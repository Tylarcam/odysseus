#!/usr/bin/env python3
"""Quiet wrapper for pixelrag serve that avoids broken %(req)s log format."""

from __future__ import annotations

import logging


def _configure_plain_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )


def main() -> None:
    _configure_plain_logging()
    from pixelrag_serve.api import main as serve_main

    serve_main()


if __name__ == "__main__":
    main()
