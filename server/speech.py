"""Prepare bounded, plain-text speech segments on the Python server."""

import re


def speech_segments(value: str, limit: int = 200) -> list[str]:
    if limit < 1:
        raise ValueError("Speech segment limit must be positive.")
    remaining = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    remaining = re.sub(r"^\s*#{1,6}\s+", "", remaining, flags=re.M)
    remaining = re.sub(r"[`*_]", "", remaining)
    remaining = re.sub(r"^\s*[-•]\s+", "", remaining, flags=re.M)
    remaining = " ".join(remaining.split())
    segments = []
    while len(remaining) > limit:
        prefix = remaining[:limit]
        sentence = max(prefix.rfind(". "), prefix.rfind("? "), prefix.rfind("! "))
        space = prefix.rfind(" ")
        cut = sentence + 1 if sentence > len(prefix) / 2 else space if space > 0 else limit
        segments.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    if remaining:
        segments.append(remaining)
    return segments
