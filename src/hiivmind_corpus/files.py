"""The atomic multi-file write: temporary file and rename, restored on failure."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path

from .errors import WriteFailed

# (bytes, mode) of a file as it was, or None when it was absent.
_Snapshot = tuple[bytes, int] | None


def _snapshot(path: Path) -> _Snapshot:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return path.read_bytes(), stat.S_IMODE(st.st_mode)


def _put(path: Path, data: bytes, mode: int | None) -> None:
    """Write data to path by temporary file in the same directory and os.replace."""
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_bytes(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _restore(path: Path, snap: _Snapshot) -> None:
    if snap is None:
        path.unlink(missing_ok=True)
    else:
        _put(path, snap[0], snap[1])


def write_set(root: Path, writes: Mapping[str, str], removes: Sequence[str] = ()) -> tuple[str, ...]:
    """Write every text in `writes` and remove every name in `removes`, under `root`.

    Text equal to the file's bytes is not written. On failure each target the
    call touched is put back, in reverse order, each restore independent of the
    others, and WriteFailed names the restored and the unrestored targets.
    Returns the names changed.
    """
    root = Path(root)
    plan: list[tuple[str, bytes | None]] = []
    for name, text in writes.items():
        plan.append((name, text.encode("utf-8")))
    for name in removes:
        if name not in writes:
            plan.append((name, None))

    changed: list[str] = []
    touched: list[tuple[str, _Snapshot]] = []
    try:
        for name, data in plan:
            if data is None:
                continue
            path = root / name
            snap = _snapshot(path)
            if snap is not None and snap[0] == data:
                continue
            touched.append((name, snap))
            _put(path, data, snap[1] if snap else None)
            changed.append(name)
        for name, data in plan:
            if data is not None:
                continue
            path = root / name
            snap = _snapshot(path)
            if snap is None:
                continue
            touched.append((name, snap))
            os.unlink(path)
            changed.append(name)
    except Exception as cause:
        restored: list[str] = []
        unrestored: list[str] = []
        for name, snap in reversed(touched):
            try:
                _restore(root / name, snap)
                restored.append(name)
            except Exception:
                unrestored.append(name)
        raise WriteFailed(tuple(sorted(restored)), tuple(sorted(unrestored)), str(cause)) from cause
    return tuple(changed)
