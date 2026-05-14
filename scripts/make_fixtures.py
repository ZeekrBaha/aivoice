"""Generate test audio fixtures using macOS `say` + ffmpeg conversion."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

FIX = Path(__file__).parent.parent / "tests" / "fixtures"
FIX.mkdir(parents=True, exist_ok=True)


def say_to_wav(text: str, out: Path, voice: str = "Samantha") -> None:
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-o", str(aiff), text], check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1", str(out)],
        check=True,
        capture_output=True,
    )
    aiff.unlink()


def silence(seconds: float, out: Path) -> None:
    sf.write(out, np.zeros(int(16000 * seconds), dtype=np.float32), 16000)


def main() -> None:
    if not shutil.which("ffmpeg"):
        raise SystemExit("install ffmpeg: brew install ffmpeg")
    say_to_wav("hello world", FIX / "hello_world.wav")
    say_to_wav("um so I uh think the API is broken", FIX / "with_fillers.wav")
    silence(5.0, FIX / "silence_5s.wav")

    # leading + trailing silence around "test"
    say_to_wav("test", FIX / "_test.wav")
    test, sr = sf.read(FIX / "_test.wav")
    pad = np.zeros(int(0.5 * sr), dtype=np.float32)
    sf.write(FIX / "leading_trailing_silence.wav", np.concatenate([pad, test, pad]), sr)
    (FIX / "_test.wav").unlink()


if __name__ == "__main__":
    main()
