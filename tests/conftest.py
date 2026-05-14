import pytest


@pytest.fixture
def tmp_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AIVOICE_CONFIG_DIR", str(tmp_path))
    return tmp_path
