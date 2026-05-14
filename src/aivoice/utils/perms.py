from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PermissionStatus:
    microphone: bool
    accessibility: bool
    input_monitoring: bool

    @property
    def all_ok(self) -> bool:
        return all([self.microphone, self.accessibility, self.input_monitoring])


def check_microphone() -> bool:
    try:
        import sounddevice as sd
        sd.check_input_settings(samplerate=16000, channels=1)
        return True
    except Exception:
        return False


def check_accessibility() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        # prompt=True shows the system dialog the first time
        return bool(AXIsProcessTrustedWithOptions({"AXTrustedCheckOptionPrompt": True}))
    except Exception:
        try:
            from ApplicationServices import AXIsProcessTrusted
            return bool(AXIsProcessTrusted())
        except Exception:
            return False


def check_input_monitoring() -> bool:
    # No direct macOS API for Input Monitoring status.
    # Accessibility is a prerequisite for pynput's event tap — piggy-back on it.
    return check_accessibility()


def check_all() -> PermissionStatus:
    return PermissionStatus(
        microphone=check_microphone(),
        accessibility=check_accessibility(),
        input_monitoring=check_input_monitoring(),
    )
