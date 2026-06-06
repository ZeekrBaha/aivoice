import fcntl

from aivoice import __main__ as entrypoint


def test_single_instance_lock_rejects_second_holder(monkeypatch, tmp_path):
    monkeypatch.setenv("AIVOICE_LOCK_PATH", str(tmp_path / "aivoice.lock"))
    entrypoint._LOCK_FILE = None

    assert entrypoint._acquire_single_instance_lock() is True
    first = entrypoint._LOCK_FILE
    assert entrypoint._acquire_single_instance_lock() is False

    fcntl.flock(first.fileno(), fcntl.LOCK_UN)
    first.close()
    entrypoint._LOCK_FILE = None

    assert entrypoint._acquire_single_instance_lock() is True
    fcntl.flock(entrypoint._LOCK_FILE.fileno(), fcntl.LOCK_UN)
    entrypoint._LOCK_FILE.close()
    entrypoint._LOCK_FILE = None
