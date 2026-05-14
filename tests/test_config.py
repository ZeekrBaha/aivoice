from aivoice.config import Settings


def test_defaults_load_when_no_file(tmp_config_dir):
    s = Settings.load()
    assert s.stt_engine == "local_mlx"
    assert s.local_mlx_model == "mlx-community/distil-whisper-large-v3"
    assert s.cleanup_enabled is False
    assert s.hotkey == "alt"


def test_overrides_from_toml(tmp_config_dir):
    (tmp_config_dir / "settings.toml").write_text(
        'stt_engine = "cloud_groq"\ncleanup_enabled = true\n'
    )
    s = Settings.load()
    assert s.stt_engine == "cloud_groq"
    assert s.cleanup_enabled is True
