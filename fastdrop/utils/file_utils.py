from __future__ import annotations

from pathlib import Path

from fastdrop.security.hashing import sanitize_filename


def ensure_directory(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory.resolve()


def assert_path_within_directory(directory: Path, target: Path) -> Path:
    """Ensure resolved target path stays inside the receive directory."""
    base = directory.resolve()
    resolved = target.resolve()
    if base == resolved:
        raise ValueError("Invalid save path")
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError("Refusing to write outside the receive directory") from exc
    return resolved


def build_receive_path(directory: str | Path, filename: str) -> Path:
    target_directory = ensure_directory(directory)
    safe_name = sanitize_filename(filename)
    candidate = target_directory / safe_name
    counter = 1
    while candidate.exists():
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        candidate = target_directory / f"{stem}_{counter}{suffix}"
        counter += 1
        if counter > 10_000:
            raise ValueError("Too many duplicate file names")
    return assert_path_within_directory(target_directory, candidate)


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    index = 0
    while value >= 1024 and index < len(units) - 1:
        value /= 1024.0
        index += 1
    return f"{value:.2f} {units[index]}"
