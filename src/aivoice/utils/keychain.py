from __future__ import annotations

import os

import keyring

SERVICE = "aivoice"


def get_secret(key: str) -> str | None:
    env_val = os.environ.get(key)
    if env_val:
        return env_val
    return keyring.get_password(SERVICE, key)


def set_secret(key: str, value: str) -> None:
    keyring.set_password(SERVICE, key, value)
