from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 digest for a file without loading it fully in memory."""
    digest = hashlib.sha256()
    path_obj = Path(path)
    with path_obj.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_filename(filename: str) -> str:
    """Strip directory traversal and unsafe characters from a file name."""
    candidate = filename.strip().replace("\\", "/")
    segments = [part for part in candidate.split("/") if part and part not in {".", ".."}]
    cleaned = "".join(segment for segment in segments if segment)
    cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_", ".", "(", ")", " "})
    return cleaned or "received_file.bin"
