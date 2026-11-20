import os
import stat

import pytest

from hiivmind_corpus import files
from hiivmind_corpus.errors import WriteFailed


def failing_replace(monkeypatch, fail_on):
    """fail_on(n, dst_name, calls) -> bool; n is the 1-based replace call number."""
    real = os.replace
    state = {"n": 0}

    def replace(src, dst, *a, **k):
        state["n"] += 1
        if fail_on(state["n"], os.path.basename(dst)):
            raise OSError("disk full")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(files.os, "replace", replace)


def test_unchanged_text_writes_nothing(tmp_path):
    p = tmp_path / "a.yaml"
    p.write_text("x: 1\n")
    os.utime(p, (1000, 1000))
    before = p.stat()
    assert files.write_set(tmp_path, {"a.yaml": "x: 1\n"}) == ()
    after = p.stat()
    assert (after.st_ino, after.st_mtime) == (before.st_ino, before.st_mtime)


def test_every_file_is_written_and_a_listed_removal_is_removed(tmp_path):
    (tmp_path / "a.yaml").write_text("old")
    (tmp_path / "gone.yaml").write_text("bye")
    changed = files.write_set(tmp_path, {"a.yaml": "new", "b.yaml": "fresh"}, ["gone.yaml"])
    assert (tmp_path / "a.yaml").read_text() == "new"
    assert (tmp_path / "b.yaml").read_text() == "fresh"
    assert not (tmp_path / "gone.yaml").exists()
    assert set(changed) == {"a.yaml", "b.yaml", "gone.yaml"}


def test_a_failure_midway_restores_every_file_written(tmp_path, monkeypatch):
    (tmp_path / "a.yaml").write_bytes(b"old-a")
    (tmp_path / "b.yaml").write_bytes(b"old-b")
    failing_replace(monkeypatch, lambda n, name: n == 3)
    with pytest.raises(WriteFailed) as e:
        files.write_set(tmp_path, {"a.yaml": "A", "b.yaml": "B", "c.yaml": "C"})
    assert (tmp_path / "a.yaml").read_bytes() == b"old-a"
    assert (tmp_path / "b.yaml").read_bytes() == b"old-b"
    assert not (tmp_path / "c.yaml").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.yaml", "b.yaml"]
    assert e.value.restored == ("a.yaml", "b.yaml", "c.yaml")
    assert e.value.unrestored == ()


def test_a_read_only_file_is_put_back_with_its_bytes_and_mode(tmp_path, monkeypatch):
    idx = tmp_path / "index.yaml"
    idx.write_bytes(b"old-index")
    idx.chmod(0o444)
    failing_replace(monkeypatch, lambda n, name: name == "z.yaml")
    with pytest.raises(WriteFailed) as e:
        files.write_set(tmp_path, {"index.yaml": "new", "z.yaml": "Z"})
    assert idx.read_bytes() == b"old-index"
    assert stat.S_IMODE(idx.stat().st_mode) == 0o444
    assert "index.yaml" in e.value.restored
    assert e.value.unrestored == ()


def test_a_file_that_cannot_be_restored_is_named_and_the_rest_are_restored(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_bytes(b"old-config")
    (tmp_path / "index.yaml").write_bytes(b"old-index")
    seen = {"config": 0}

    def fail_on(n, name):
        if name == "config.yaml":
            seen["config"] += 1
            return seen["config"] == 2  # the restore
        return name == "z.yaml"

    failing_replace(monkeypatch, fail_on)
    with pytest.raises(WriteFailed) as e:
        files.write_set(tmp_path, {"config.yaml": "C", "index.yaml": "I", "z.yaml": "Z"})
    assert e.value.unrestored == ("config.yaml",)
    assert (tmp_path / "index.yaml").read_bytes() == b"old-index"
    assert "index.yaml" in e.value.restored and "config.yaml" not in e.value.restored


def test_a_removed_file_is_restored_on_failure(tmp_path, monkeypatch):
    gone = tmp_path / "gone.yaml"
    gone.write_bytes(b"keep me")
    gone.chmod(0o640)
    failing_replace(monkeypatch, lambda n, name: name == "z.yaml")
    with pytest.raises(WriteFailed):
        files.write_set(tmp_path, {"z.yaml": "Z"}, ["gone.yaml"])
    # removals run last, so force failure after removal instead
    monkeypatch.undo()
    real_unlink = os.unlink
    calls = []

    def unlink(path, *a, **k):
        calls.append(path)
        real_unlink(path, *a, **k)
        if os.path.basename(path) == "gone.yaml":
            raise OSError("late failure")

    monkeypatch.setattr(files.os, "unlink", unlink)
    with pytest.raises(WriteFailed) as e:
        files.write_set(tmp_path, {"y.yaml": "Y"}, ["gone.yaml"])
    assert gone.read_bytes() == b"keep me"
    assert stat.S_IMODE(gone.stat().st_mode) == 0o640
    assert not (tmp_path / "y.yaml").exists()
    assert e.value.restored == ("gone.yaml", "y.yaml")


def test_an_interrupt_between_replaces_restores_and_is_reraised_unchanged(tmp_path, monkeypatch):
    (tmp_path / "a.yaml").write_text("old a")
    (tmp_path / "b.yaml").write_text("old b")
    real = os.replace
    state = {"n": 0}

    def replace(src, dst, *a, **k):
        state["n"] += 1
        if state["n"] == 2:
            raise KeyboardInterrupt
        return real(src, dst, *a, **k)

    monkeypatch.setattr(files.os, "replace", replace)
    with pytest.raises(KeyboardInterrupt):
        files.write_set(tmp_path, {"a.yaml": "new a", "b.yaml": "new b"})
    assert (tmp_path / "a.yaml").read_text() == "old a" and (tmp_path / "b.yaml").read_text() == "old b"
