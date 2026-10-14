"""Replay ticks persist to disk: a restart reads them back instead of recomputing; a changed model or data file recomputes."""
import shutil
from pathlib import Path

import pytest

from app import replay
from app.schemas import Weights
from tests.test_backend import T0, synthetic_snapshot


@pytest.fixture
def tmp_path():
    """A folder beside the tests (the system temp folder is not writable here), removed afterwards."""
    d = Path(__file__).parent / "_tick_cache_test"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_ticks_are_saved_and_read_back_and_a_changed_input_recomputes(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "TICK_DIR", tmp_path)
    replay._snaps[998] = synthetic_snapshot()
    calls = []
    real = replay.run_tick
    monkeypatch.setattr(replay, "run_tick", lambda *a: calls.append(1) or real(*a))
    replay.tick.cache_clear()
    first = replay.tick(998, T0, Weights())
    assert len(calls) == 1 and len(list(tmp_path.rglob("*.json.gz"))) == 1
    replay.tick.cache_clear()  # what a backend restart does to the in-memory memo
    again = replay.tick(998, T0, Weights())
    assert len(calls) == 1 and again == first  # read from disk, identical payloads
    replay.tick.cache_clear()
    replay.tick(998, T0, Weights(probability=0.9))  # other weights: their own file
    assert len(calls) == 2
    marker = tmp_path / "model.bin"
    marker.write_text("v1")
    monkeypatch.setattr(replay, "_INPUTS", [marker])
    replay.tick.cache_clear()
    replay.tick(998, T0, Weights())
    assert len(calls) == 3  # a model file the fingerprint covers changed: recompute, never serve stale


def test_an_unreadable_cache_file_is_recomputed_not_served(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, "TICK_DIR", tmp_path)
    replay._snaps[998] = synthetic_snapshot()
    replay.tick.cache_clear()
    path = replay._tick_path(998, T0, Weights())
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not gzip")
    assert len(replay.tick(998, T0, Weights())) == 3
