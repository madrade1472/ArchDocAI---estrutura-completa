"""
Render Mermaid diagrams to PNG via the public kroki.io service.

Used by docx_gen and pdf_gen to embed sequence diagrams as actual images
instead of monospace text. Falls back gracefully (returns None) when the
service is unreachable, the diagram is invalid, or the response is too small.

Cache lives in ~/.cache/archdocai/mermaid/ keyed by SHA-256 of the diagram
text, so identical diagrams across runs reuse the same PNG.
"""

from __future__ import annotations

import hashlib
import os
import threading
import urllib.request
import urllib.error
from pathlib import Path

from src.logger import get_logger

log = get_logger(__name__)


_KROKI_URL = "https://kroki.io/mermaid/png"
_TIMEOUT_SECONDS = 12
_MIN_PNG_BYTES = 500  # smaller than this is almost certainly an error response

_render_lock = threading.Lock()
_failed_hashes: set[str] = set()


def _cache_dir() -> Path:
    base = os.getenv("ARCHDOC_MERMAID_CACHE",
                     str(Path.home() / ".cache" / "archdocai" / "mermaid"))
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def render_mermaid_png(mermaid_text: str) -> Path | None:
    """Render a Mermaid diagram to a PNG file and return its path.

    Returns None when:
      - The diagram text is empty
      - kroki.io rejects the diagram syntax
      - The download fails or the response is suspiciously small
      - We already failed on this exact diagram earlier in the process

    Caller should fall back to embedding the raw Mermaid text when None.
    """
    text = (mermaid_text or "").strip()
    if not text:
        return None

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    if digest in _failed_hashes:
        return None

    cache_path = _cache_dir() / f"{digest}.png"
    if cache_path.exists() and cache_path.stat().st_size >= _MIN_PNG_BYTES:
        return cache_path

    with _render_lock:
        # Double-check inside the lock in case a sibling thread just rendered it
        if cache_path.exists() and cache_path.stat().st_size >= _MIN_PNG_BYTES:
            return cache_path
        try:
            req = urllib.request.Request(
                _KROKI_URL,
                data=text.encode("utf-8"),
                headers={
                    "Content-Type": "text/plain",
                    "User-Agent": "ArchDocAI/1.0",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(
                        _KROKI_URL, resp.status, "non-200", resp.headers, None,
                    )
                data = resp.read()
            if len(data) < _MIN_PNG_BYTES:
                raise ValueError(f"response too small ({len(data)} bytes)")
            cache_path.write_bytes(data)
            log.info("Rendered Mermaid diagram via kroki: %s (%d bytes)", digest, len(data))
            return cache_path
        except Exception as exc:
            log.warning("Failed to render Mermaid diagram via kroki (%s): %s", digest, exc)
            _failed_hashes.add(digest)
            return None
