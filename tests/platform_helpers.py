"""Keep subprocess tests isolated from credentials on every OS."""

import os


def subprocess_env(hashseed=None):
    # Windows needs SystemRoot and its native PATH. Preserve OS settings,
    # but never inherit credentials/configuration for the real arena path.
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("ARENA_")}
    env.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if hashseed is not None:
        env["PYTHONHASHSEED"] = str(hashseed)
    return env
