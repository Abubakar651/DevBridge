"""Prepare bounded, plain-text speech segments on the Python server."""

import re


def speech_segments(value: str, limit: int = 200) -> list[str]:
    """Strip Markdown formatting and split text into <=limit plain-text speech segments."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Speech segment limit must be positive.")
    remaining = re.sub(r"\[([^\]]+)\]\((?:[^()\s]+|\([^()\s]*\))+\)", r"\1", value)
    remaining = re.sub(r"^\s*(?:#{1,6}|>|[-+•])\s+", "", remaining, flags=re.M)
    remaining = re.sub(r"[`*]|~~|(?<!\w)_+|_+(?!\w)", "", remaining)
    remaining = " ".join(remaining.split())
    segments = []
    while len(remaining) > limit:
        window = remaining[: limit + 1]
        sentence = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
        space = window.rfind(" ")
        cut = sentence + 1 if sentence > limit / 2 else space if space > 0 else limit
        segments.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    if remaining:
        segments.append(remaining)
    return segments
