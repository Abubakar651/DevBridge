from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from .errors import AppError

MAX_ANSWERS = 3
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Dimension = Literal["Audience clarity", "Structure and relevance", "Assertiveness", "Respect", "Accuracy and next steps"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Context(Model):
    scenario_id: Literal["release-update"] = Field(alias="scenarioId")
    discipline: Literal["Software developer", "AI/ML engineer"]
    familiarity: ShortText = Field(max_length=200)
    known_facts: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=4000)] = Field(alias="knownFacts")
    goal: Annotated[str, StringConstraints(strip_whitespace=True, min_length=10, max_length=600)]


class SpeechRequest(Model):
    text: ShortText = Field(max_length=200)


class RoleplayResponse(Model):
    reply: ShortText = Field(max_length=1500, description="The project manager asks the learner one short question about the supplied scenario. Include exactly one question mark; do not answer the question for the learner.")


class Strength(Model):
    title: ShortText = Field(max_length=160)
    quote: ShortText = Field(max_length=500)
    reason: ShortText = Field(max_length=700)


class Improvement(Model):
    dimension: Dimension
    quote: ShortText = Field(max_length=500)
    reason: ShortText = Field(max_length=700)
    suggestion: ShortText = Field(max_length=700, description="One specific wording improvement. Recommendations and polite decision questions are already legitimate assertiveness. Preserve the scenario's facts and approval authority.")


class Feedback(Model):
    strength: Strength
    improvements: list[Improvement] = Field(min_length=1, max_length=2)
    improved_message: ShortText = Field(alias="improvedMessage", max_length=1800, description="A natural alternative using only knownFacts. Preserve ready versus future work, exact timeframes, uncertainty and who can approve. Never introduce a sprint or other schedule absent from knownFacts.")
    summary: ShortText = Field(max_length=900)
    retry_focus: ShortText = Field(alias="retryFocus", max_length=500)
    missing_facts: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]] = Field(alias="missingFacts", max_length=5)
    comparison: str = Field(max_length=900)


def normalize(value: str) -> str:
    return " ".join(value.casefold().split())


NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
NUMBER_WORD_PATTERN = re.compile(r"\b(?:" + "|".join(NUMBER_WORDS) + r")\b", re.I)
QUANTITY = r"(?:\d+|" + "|".join(NUMBER_WORDS) + r")"
DELIVERY_TIMING_PATTERNS = (
    re.compile(r"\b(?:will|would|can|could|should|is|are)\s+(?:be\s+)?(?:ready|delivered|completed|finished|available|released|shipped|launched)\s+(?:in|within|after|by)\s+(?:the\s+next\s+)?" + QUANTITY + r"\s+(?:additional\s+)?(?:working\s+)?days?\b", re.I),
    re.compile(r"\b(?:will|would|can|could|should|is|are)\s+(?:be\s+)?(?:ready|delivered|completed|finished|available|released|shipped|launched)\s+for\s+(?:the\s+next\s+)?" + QUANTITY + r"\b", re.I),
    re.compile(r"\bfor\s+the\s+next\s+" + QUANTITY + r"\s+(?:additional\s+)?(?:working\s+)?days?\b", re.I),
    re.compile(r"\b" + QUANTITY + r"\s+(?:additional\s+)?(?:working\s+)?days?\s+(?:after|later|from)\b", re.I),
)
ZERO_IMPACT_PATTERNS = (
    re.compile(r"\bthere(?:\s+is|'s)\s+no\s+customer\s+impact\b", re.I),
    re.compile(r"\bno\s+customer\s+impact\s+(?:to\s+consider|exists|is\s+expected)\b", re.I),
    re.compile(r"\b(?:zero|without\s+any)\s+customer\s+impact\b", re.I),
    re.compile(r"\bcustomer\s+impact\s+(?:is|was|will\s+be)\s+(?:zero|none|nonexistent)\b", re.I),
)


def normalize_number_words(value: str) -> str:
    return NUMBER_WORD_PATTERN.sub(lambda match: str(NUMBER_WORDS[match.group(0).casefold()]), normalize(value))


def feedback_claim_texts(feedback: Feedback) -> list[str]:
    return [
        feedback.improved_message,
        feedback.summary,
        feedback.retry_focus,
        feedback.comparison,
        *(item.suggestion for item in feedback.improvements),
        *feedback.missing_facts,
    ]


def validate_feedback(value: dict, history: list[dict], context: Context, previous_history: list[dict] | None = None) -> Feedback:
    try:
        feedback = Feedback.model_validate(value)
        utterances = [normalize(turn["content"]) for turn in history if turn["role"] == "user"]
        for quote in [feedback.strength.quote, *(item.quote for item in feedback.improvements)]:
            if not any(normalize(quote) in utterance for utterance in utterances):
                raise ValueError("Evidence quote is absent from the learner's actual words.")
        if previous_history is None and feedback.comparison.strip():
            raise ValueError("Comparison must be empty on the first attempt.")
        facts_text = normalize(context.known_facts)
        facts = normalize_number_words(context.known_facts)
        allowed_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?%?", facts))
        rewrite_numbers = re.findall(r"\b\d+(?:[.,]\d+)?%?", normalize_number_words(feedback.improved_message))
        if any(number not in allowed_numbers for number in rewrite_numbers):
            raise ValueError("The rewrite introduces a new numeric claim.")
        claim_texts = feedback_claim_texts(feedback)
        dates = []
        for text in claim_texts:
            dates.extend(re.findall(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", text, re.I))
            dates.extend(re.findall(r"\b(?:in|by|before|after|on)\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b", text, re.I))
        if any(normalize(date) not in facts_text for date in dates):
            raise ValueError("The feedback introduces a new date.")
        relative_schedule = [
            schedule
            for text in claim_texts
            for schedule in re.findall(r"\b(?:this|next|following)\s+(?:sprint|week|month|quarter|year|cycle|iteration|release)\b", text, re.I)
        ]

        def schedule_is_grounded(schedule: str) -> bool:
            normalized = normalize(schedule)
            return normalized in facts_text or (normalized == "this release" and re.search(r"\brelease\b", facts_text) is not None)

        if any(not schedule_is_grounded(schedule) for schedule in relative_schedule):
            unsupported = sorted({schedule.lower() for schedule in relative_schedule if not schedule_is_grounded(schedule)})
            raise ValueError("The rewrite introduces an unsupported schedule: " + ", ".join(unsupported) + ". Remove that schedule; retain only the work duration supplied in knownFacts.")
        if any(pattern.search(text) for text in claim_texts for pattern in DELIVERY_TIMING_PATTERNS):
            raise ValueError("The feedback turns a work duration into an unsupported delivery promise. Retain the duration without assigning a delivery date or start window.")
        impact_is_unmeasured = re.search(r"\b(?:customer\s+)?impact\b.{0,60}\bnot\s+(?:been\s+)?measured\b", facts_text) or re.search(r"\bno\s+customer\s+impact\b.{0,40}\bmeasured\b", facts_text)
        if impact_is_unmeasured and any(pattern.search(text) for text in claim_texts for pattern in ZERO_IMPACT_PATTERNS):
            raise ValueError("The feedback treats unmeasured customer impact as zero impact. Preserve the uncertainty instead.")
        return feedback
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        hint = str(error) if isinstance(error, ValueError) and not isinstance(error, ValidationError) else "Match every required feedback field and its size limits."
        raise AppError(502, "The coach returned incomplete or ungrounded feedback. Please try feedback again.", "INVALID_PROVIDER_OUTPUT", validation_hint=hint) from None
