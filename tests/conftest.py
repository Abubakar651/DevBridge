import io
import wave

import pytest

from server.models import Context, validate_feedback
from server.scenario import DEFAULT_CONTEXT

QUESTION = "What is ready for Friday, and what do you recommend about PDF export?"
ANSWER = "Search is ready for Friday. PDF export needs two more working days. I recommend releasing search first."


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def context():
    return Context.model_validate(DEFAULT_CONTEXT)


def feedback_value(history, previous=None):
    quote = next(turn["content"] for turn in history if turn["role"] == "user")[:100]
    return {
        "strength": {"title": "You gave a direct update", "quote": quote, "reason": "You put your view into words rather than avoiding the decision."},
        "improvements": [{"dimension": "Accuracy and next steps", "quote": quote, "reason": "The scope decision could be more explicit.", "suggestion": "Ask which outcome is the priority."}],
        "improvedMessage": "Search is ready for Friday. PDF export needs two additional working days. I recommend releasing search first. Which outcome is the priority?",
        "summary": "You gave a direct update. Next, make the scope decision explicit.",
        "retryFocus": "Lead with what is ready and make a clear recommendation.",
        "missingFacts": [], "comparison": "Your latest recommendation can be compared with the first attempt." if previous else "",
    }


def wav_audio():
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\0\0" * 1600)
    return output.getvalue()


class FakeProvider:
    def __init__(self):
        self.roleplay_calls = []
        self.coach_calls = []
        self.transcribe_calls = []
        self.speak_calls = []

    async def roleplay(self, context, history):
        self.roleplay_calls.append((context.model_copy(deep=True), history.copy()))
        return QUESTION if not history else "Which outcome would you prioritize for this release?"

    async def coach(self, context, history, previous=None):
        self.coach_calls.append((context.model_copy(deep=True), history.copy(), previous))
        return validate_feedback(feedback_value(history, previous), history, context, previous)

    async def speak(self, text):
        self.speak_calls.append(text)
        return wav_audio()

    async def transcribe(self, audio, mime):
        self.transcribe_calls.append((audio, mime))
        return ANSWER
