"""Load only the application's environment settings without changing os.environ."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_KEYS = {
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY", "GROQ_API_KEY2", "GROQ_API_KEY_2", "OPENROUTER_API_KEY",
    "GEMINI_MODEL", "GROQ_STT_MODEL", "GROQ_TTS_MODEL", "GROQ_TTS_VOICE", "GROQ_REASONING_MODEL", "OPENROUTER_MODEL",
    "HOST", "PORT",
}


def parse_env(content: str) -> dict[str, str]:
    values = {}
    for line in content.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match or match[1] not in ENV_KEYS:
            continue
        value = match[2]
        if value.startswith(("'", '"')):
            quote = value[0]
            escaped = False
            end = None
            for index, character in enumerate(value[1:], start=1):
                if character == quote and not escaped:
                    end = index
                    break
                escaped = character == "\\" and not escaped
                if character != "\\":
                    escaped = False
            value = value[1:end] if end is not None else value[1:]
        else:
            value = re.sub(r"\s+#.*$", "", value)
        value = value.strip()
        if value:
            values[match[1]] = value
    return values


@dataclass(frozen=True)
class Settings:
    gemini_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    groq_voice_key: str = field(default="", repr=False)
    openrouter_key: str = field(default="", repr=False)
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_reasoning_model: str = "openai/gpt-oss-20b"
    openrouter_model: str = "openai/gpt-oss-20b"
    stt_model: str = "whisper-large-v3-turbo"
    tts_model: str = "canopylabs/orpheus-v1-english"
    voice: str = "troy"
    host: str = "127.0.0.1"
    port: int = 4317
    timeout_seconds: float = 30
    retry_delay_seconds: float = 0.5


def load_settings(environment: Mapping[str, str] | None = None) -> Settings:
    values = {}
    env_paths = [
        *(PROJECT_ROOT.parents[i] / ".env" for i in (2, 1) if len(PROJECT_ROOT.parents) > i),
        PROJECT_ROOT / ".env",
    ]
    for path in env_paths:
        if path.is_file():
            values.update(parse_env(path.read_text(encoding="utf-8")))
    for key, raw_value in (environment if environment is not None else os.environ).items():
        if key in ENV_KEYS and isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if cleaned:
                values[key] = cleaned
    try:
        port = int(values.get("PORT", "4317"))
    except ValueError:
        raise ValueError("PORT must be a valid port number.") from None
    if not 0 <= port <= 65535:
        raise ValueError("PORT must be a valid port number.")
    return Settings(
        gemini_key=values.get("GEMINI_API_KEY") or values.get("GOOGLE_API_KEY", ""),
        groq_key=values.get("GROQ_API_KEY", ""),
        groq_voice_key=values.get("GROQ_API_KEY2") or values.get("GROQ_API_KEY_2", ""),
        openrouter_key=values.get("OPENROUTER_API_KEY", ""),
        gemini_model=values.get("GEMINI_MODEL", Settings.gemini_model),
        groq_reasoning_model=values.get("GROQ_REASONING_MODEL", Settings.groq_reasoning_model),
        openrouter_model=values.get("OPENROUTER_MODEL", Settings.openrouter_model),
        stt_model=values.get("GROQ_STT_MODEL", Settings.stt_model),
        tts_model=values.get("GROQ_TTS_MODEL", Settings.tts_model),
        voice=values.get("GROQ_TTS_VOICE", Settings.voice),
        host=values.get("HOST", Settings.host), port=port,
    )
