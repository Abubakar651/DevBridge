from __future__ import annotations

from decimal import Decimal
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from .errors import AppError

MAX_ANSWERS = 10
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Dimension = Literal["Audience clarity", "Structure and relevance", "Assertiveness", "Respect", "Accuracy and next steps"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Context(Model):
    scenario_id: Literal["churn-pitch", "two-day-delay"] = Field(alias="scenarioId")
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


_TYPOGRAPHIC_TRANSLATION = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'", "\u02bc": "'", "\u2032": "'",
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"', "\u2033": '"',
    "\u2010": "-", "\u2011": "-",
    "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "",
})


def normalize_punctuation(value: str) -> str:
    """Collapse whitespace and normalize curly quotes, apostrophes, and Unicode hyphens."""
    return " ".join(value.translate(_TYPOGRAPHIC_TRANSLATION).split())


def normalize(value: str) -> str:
    """Normalize typography, whitespace, and case for grounded substring matching."""
    return normalize_punctuation(value).casefold()


_UNITS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
NUMBER_WORDS = {
    "zero": 0, **_UNITS, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, **_TENS,
}
_COMPOUND_NUMBER_PATTERN = re.compile(r"\b(" + "|".join(_TENS) + r")[-\s]+(" + "|".join(_UNITS) + r")\b", re.I)
NUMBER_WORD_PATTERN = re.compile(r"\b(?:" + "|".join(NUMBER_WORDS) + r")\b", re.I)
_MULTIPLIERS = (
    (re.compile(r"(?:\b(\d+)\s+|\ba\s+|\b)hundred(?:\s+(?:and\s+)?(\d{1,2}))?\b", re.I), 100),
    (re.compile(r"(?:\b(\d+(?:\.\d+)?)\s+|\ba\s+|\b)thousand(?:\s+(?:and\s+)?(\d{1,3}))?\b", re.I), 1_000),
    (re.compile(r"(?:\b(\d+(?:\.\d+)?)\s+|\ba\s+|\b)million\b", re.I), 1_000_000),
    (re.compile(r"(?:\b(\d+(?:\.\d+)?)\s+|\ba\s+|\b)billion\b", re.I), 1_000_000_000),
)
QUANTITY = r"(?:\d+(?:\s*(?:-|to)\s*\d+)?|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[-\s]+(?:one|two|three|four|five|six|seven|eight|nine))?|" + "|".join(NUMBER_WORDS) + r")"
_DELIVERY_VERB = r"(?:will|would|can|could|should|is|are)\s+(?:be\s+)?(?:ready|deliver(?:ed)?|complet(?:e|ed)|finish(?:ed)?|available|releas(?:e|ed)|ship(?:ped)?|launch(?:ed)?)"
_DURATION_DAYS = QUANTITY + r"\s+(?:(?:additional|more|extra)\s+)?(?:(?:working|business)\s+)?days?"
DELIVERY_TIMING_PATTERNS = (
    re.compile(r"\b" + _DELIVERY_VERB + r"\s+(?:in|within|after|by)\s+(?:the\s+next\s+)?" + _DURATION_DAYS + r"\b", re.I),
    re.compile(r"\b" + _DELIVERY_VERB + r"\s+for\s+(?:the\s+next\s+)?" + QUANTITY + r"\b", re.I),
    re.compile(r"\bfor\s+the\s+next\s+" + _DURATION_DAYS + r"\b", re.I),
    re.compile(r"\b" + _DURATION_DAYS + r"\s+(?:after|later|from)\b", re.I),
)
ZERO_IMPACT_PATTERNS = (
    re.compile(r"\bthere(?:\s+is|'s)\s+no\s+customer\s+impact\b", re.I),
    re.compile(r"\bno\s+customer\s+impact\s+(?:to\s+consider|exists|is\s+expected)\b", re.I),
    re.compile(r"\b(?:zero|without\s+any)\s+customer\s+impact\b", re.I),
    re.compile(r"\bcustomer\s+impact\s+(?:is|was|will\s+be)\s+(?:zero|none|non-?existent)\b", re.I),
    re.compile(r"\b(?:has|have|had|carries|poses|creates|causes)\s+no\s+customer\s+impact\b", re.I),
)

_WEEKDAY_PATTERN = re.compile(r"\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b", re.I)
_REL_WEEKDAY_PATTERN = re.compile(r"\b((?:next|following)[-\s]+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b", re.I)
_MONTH_MAP = {
    "january": "january", "jan": "january",
    "february": "february", "feb": "february",
    "march": "march", "mar": "march",
    "april": "april", "apr": "april",
    "may": "may",
    "june": "june", "jun": "june",
    "july": "july", "jul": "july",
    "august": "august", "aug": "august",
    "september": "september", "sep": "september", "sept": "september",
    "october": "october", "oct": "october",
    "november": "november", "nov": "november",
    "december": "december", "dec": "december",
}
_FULL_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_UNAMBIGUOUS_MONTHS = "January|February|April|June|July|August|September|October|November|December"
_ABBR_MONTHS = "Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec"
_MONTH_ANY = rf"(?:(?i:{_FULL_MONTHS})|(?:{_ABBR_MONTHS}))"
_DATE_PREPOSITIONS = r"(?:in|by|before|after|on|during|until|till|through|since|for|from|around|to|early|mid|late|this|next|last|end\s+of|start\s+of)"
_STRICT_TIME_PREPOSITIONS = r"(?:in|by|before|after|on|during|until|till|through|since)"

_MONTH_DAY_PATTERN = re.compile(rf"\b({_MONTH_ANY})\.?[-\s]+(\d{{1,2}})(?:st|nd|rd|th)?\b")
_DAY_MONTH_PATTERN = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?[-\s]+(?:of\s+)?({_MONTH_ANY})\.?\b")
_MONTH_YEAR_PATTERN = re.compile(rf"\b({_MONTH_ANY})\.?,?\s+((?:19|20)\d{{2}})\b")
_ISO_DATE_PATTERN = re.compile(r"\b((?:19|20)\d{2}-\d{2}-\d{2})\b")
_UNAMBIGUOUS_MONTH_PATTERN = re.compile(rf"\b({_UNAMBIGUOUS_MONTHS})\b", re.I)
_MARCH_PATTERN = re.compile(rf"\bMarch\b|\b(?i:{_DATE_PREPOSITIONS})(?:\s+|-)march\b")
_MAY_PATTERN = re.compile(rf"\b(?i:{_DATE_PREPOSITIONS}|a|the)(?:\s+|-)May\b|\b(?i:{_STRICT_TIME_PREPOSITIONS})(?:\s+|-)may(?=$|[.,;:!?)\]])")
_ABBR_PREPOSITION_PATTERN = re.compile(rf"\b(?i:{_DATE_PREPOSITIONS})(?:\s+|-)({_ABBR_MONTHS})\.?(?!\w)")
_RELATIVE_SCHEDULE_PATTERN = re.compile(
    r"\b(?:(?:this|next|following)[-\s]+(?:sprint|week|month|quarter|year|cycle|iteration|release)"
    r"|(?:upcoming|future|subsequent)[-\s]+(?:sprint|week|month|quarter|year|cycle|iteration))\b",
    re.I,
)


def _scale_number(match: re.Match, factor: int) -> str:
    base = Decimal(match.group(1)) if match.group(1) is not None else Decimal(1)
    remainder = Decimal(match.group(2)) if match.lastindex and match.lastindex >= 2 and match.group(2) is not None else Decimal(0)
    total = base * factor + remainder
    if total == total.to_integral_value():
        return str(int(total))
    return format(total.normalize(), "f")


def normalize_number_words(value: str) -> str:
    """Convert English number words, compound tens, multipliers, and percent phrases into digits."""
    text = normalize(value)
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", text)
    text = _COMPOUND_NUMBER_PATTERN.sub(
        lambda match: str(_TENS[match.group(1).casefold()] + _UNITS[match.group(2).casefold()]),
        text,
    )
    text = NUMBER_WORD_PATTERN.sub(lambda match: str(NUMBER_WORDS[match.group(0).casefold()]), text)
    for pattern, factor in _MULTIPLIERS:
        text = pattern.sub(lambda match, f=factor: _scale_number(match, f), text)
    return re.sub(r"(\b\d+(?:[.,]\d+)?)\s+(?:per\s?cent\b|%)", r"\1%", text)


def _extract_dates(text_punct: str) -> set[tuple[str, ...]]:
    """Extract canonical date tokens while avoiding modal 'may' false positives."""
    dates: set[tuple[str, ...]] = set()
    for match in _WEEKDAY_PATTERN.finditer(text_punct):
        dates.add(("weekday", match.group(1).casefold()))
    for match in _REL_WEEKDAY_PATTERN.finditer(text_punct):
        dates.add(("rel_weekday", " ".join(match.group(1).replace("-", " ").casefold().split())))
    for pattern, month_group, day_group in ((_MONTH_DAY_PATTERN, 1, 2), (_DAY_MONTH_PATTERN, 2, 1)):
        for match in pattern.finditer(text_punct):
            day = int(match.group(day_group))
            if 1 <= day <= 31:
                month = _MONTH_MAP[match.group(month_group).casefold()]
                dates.add(("month", month))
                dates.add(("month_day", month, str(day)))
    for match in _MONTH_YEAR_PATTERN.finditer(text_punct):
        month = _MONTH_MAP[match.group(1).casefold()]
        dates.add(("month", month))
        dates.add(("month_year", month, match.group(2)))
    for match in _ISO_DATE_PATTERN.finditer(text_punct):
        dates.add(("iso", match.group(1)))
    for match in _UNAMBIGUOUS_MONTH_PATTERN.finditer(text_punct):
        dates.add(("month", _MONTH_MAP[match.group(1).casefold()]))
    if _MARCH_PATTERN.search(text_punct):
        dates.add(("month", "march"))
    if _MAY_PATTERN.search(text_punct):
        dates.add(("month", "may"))
    for match in _ABBR_PREPOSITION_PATTERN.finditer(text_punct):
        dates.add(("month", _MONTH_MAP[match.group(1).casefold()]))
    return dates


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
            normalized_quote = normalize(quote)
            if not any(ch.isalnum() for ch in normalized_quote) or not any(normalized_quote in utterance for utterance in utterances):
                raise ValueError("Evidence quote is absent from the learner's actual words.")
        if not previous_history and feedback.comparison.strip():
            raise ValueError("Comparison must be empty on the first attempt.")
        if feedback.comparison != feedback.comparison.strip():
            feedback = feedback.model_copy(update={"comparison": feedback.comparison.strip()})

        facts_punct = normalize_punctuation(context.known_facts)
        facts_text = facts_punct.casefold()
        facts = normalize_number_words(context.known_facts)
        allowed_numbers = set(re.findall(r"\b\d+(?:[.,]\d+)?%?", facts))
        rewrite_numbers = re.findall(r"\b\d+(?:[.,]\d+)?%?", normalize_number_words(feedback.improved_message))
        if any(number not in allowed_numbers for number in rewrite_numbers):
            raise ValueError("The rewrite introduces a new numeric claim.")

        claim_texts = feedback_claim_texts(feedback)
        claim_texts_punct = [normalize_punctuation(text) for text in claim_texts]
        claim_texts_norm = [text.casefold() for text in claim_texts_punct]
        claim_texts_num = [normalize_number_words(text) for text in claim_texts_punct]

        known_dates = _extract_dates(facts_punct)
        if any(date not in known_dates for text in claim_texts_punct for date in _extract_dates(text)):
            raise ValueError("The feedback introduces a new date.")

        relative_schedule = [
            schedule
            for text in claim_texts_punct
            for schedule in _RELATIVE_SCHEDULE_PATTERN.findall(text)
        ]
        facts_schedules = facts_text.replace("-", " ")

        def schedule_is_grounded(schedule: str) -> bool:
            normalized = " ".join(schedule.replace("-", " ").casefold().split())
            return re.search(rf"\b{re.escape(normalized)}\b", facts_schedules) is not None or (
                normalized == "this release" and re.search(r"\brelease\b", facts_text) is not None
            )

        if any(not schedule_is_grounded(schedule) for schedule in relative_schedule):
            unsupported = sorted({schedule.lower() for schedule in relative_schedule if not schedule_is_grounded(schedule)})
            raise ValueError("The rewrite introduces an unsupported schedule: " + ", ".join(unsupported) + ". Remove that schedule; retain only the work duration supplied in knownFacts.")
        if any(pattern.search(text) for text in claim_texts_num for pattern in DELIVERY_TIMING_PATTERNS):
            raise ValueError("The feedback turns a work duration into an unsupported delivery promise. Retain the duration without assigning a delivery date or start window.")
        impact_is_unmeasured = re.search(r"\b(?:customer\s+)?impact\b.{0,60}\bnot\s+(?:been\s+)?measured\b", facts_text) or re.search(r"\bno\s+customer\s+impact\b.{0,40}\bmeasured\b", facts_text)
        if impact_is_unmeasured and any(pattern.search(text) for text in claim_texts_norm for pattern in ZERO_IMPACT_PATTERNS):
            raise ValueError("The feedback treats unmeasured customer impact as zero impact. Preserve the uncertainty instead.")
        return feedback
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        hint = str(error) if isinstance(error, ValueError) and not isinstance(error, ValidationError) else "Match every required feedback field and its size limits."
        raise AppError(502, "The coach returned incomplete or ungrounded feedback. Please try feedback again.", "INVALID_PROVIDER_OUTPUT", validation_hint=hint) from None
