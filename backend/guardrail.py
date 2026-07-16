"""Guardrail: pre-check and post-check for advisory language."""

from __future__ import annotations

import re
from datetime import datetime

from shared.schemas import GuardrailEvent


ADVISORY_PATTERNS = [
    re.compile(r"should (I|we) (buy|sell|hold|invest)", re.IGNORECASE),
    re.compile(r"(recommend|suggest) (buying|selling|holding)", re.IGNORECASE),
    re.compile(r"(recommend|suggest)\b", re.IGNORECASE),  # Match "recommend" or "suggest" standalone
    re.compile(r"(overweight|underweight|outperform|underperform)", re.IGNORECASE),
]

ADVISORY_KEYWORDS = [
    "you should", "recommend", "buy", "sell", "hold",
    "overweight", "underweight", "outperform", "underperform",
    "suggest", "advise", "opinion",
]


def pre_check_guardrail(query: str) -> dict:
    """Detect advisory-seeking patterns in user input."""
    patterns_matched = []
    for pattern in ADVISORY_PATTERNS:
        if pattern.search(query):
            patterns_matched.append(pattern.pattern)

    detected = len(patterns_matched) > 0
    augmented_query = query
    if detected:
        augmented_query = (
            f"[ANALYSIS REQUEST] {query}\n"
            "SYSTEM NOTE: User may be seeking advice. "
            "Respond with factual analysis only. No recommendations."
        )

    return {
        "detected": detected,
        "patterns_matched": patterns_matched,
        "augmented_query": augmented_query,
    }


def post_check_guardrail(response: str) -> dict:
    """Scan response for advisory language and rewrite if needed."""
    interceptions: list[GuardrailEvent] = []
    sentences = _split_sentences(response)
    rewritten_sentences = []

    for sentence in sentences:
        sentence_lower = sentence.lower()
        matched = [kw for kw in ADVISORY_KEYWORDS if kw in sentence_lower]
        if matched:
            rewritten = _rewrite_to_observational(sentence)
            interceptions.append(GuardrailEvent(
                timestamp=datetime.utcnow().isoformat(),
                original_text=sentence,
                rewritten_text=rewritten,
                trigger_keywords=matched,
            ))
            rewritten_sentences.append(rewritten)
        else:
            rewritten_sentences.append(sentence)

    return {
        "intercepted": len(interceptions) > 0,
        "interceptions": interceptions,
        "rewritten_response": " ".join(rewritten_sentences),
    }


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r'(?<=[.!?])\s+', text)
    return [p.strip() for p in parts if p.strip()]


def _rewrite_to_observational(sentence: str) -> str:
    """Simple rule-based rewrite to remove advisory language."""
    rewritten = sentence
    rules = [
        (r"You should buy (\w+)", r"\1 is under consideration"),
        (r"You should sell (\w+)", r"\1 is under consideration"),
        (r"I recommend (selling|buying|holding)", r"Analysis indicates \1"),
        (r"I recommend (\w+)", r"Analysis indicates \1"),
        (r"selling", r"potential sale"),  # Convert "selling" to observational
        (r"buying", r"potential purchase"),  # Convert "buying" to observational
        (r"The stock is likely to outperform", r"The stock has shown performance trends"),
        (r"You should hold", r"The position remains unchanged"),
        (r"Consider overweighting", r"The stock has certain characteristics"),
        (r"The stock looks like a sell", r"The stock has shown declining metrics"),
        (r"I advise you to", r"Analysis suggests"),
        (r"This is a strong buy", r"This is noteworthy"),
    ]
    for pattern, replacement in rules:
        rewritten = re.sub(pattern, replacement, rewritten, flags=re.IGNORECASE)
    return rewritten
