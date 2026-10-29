"""Naive keyword baseline. Cue lists were fixed before the first evaluation run; do not edit them after seeing results."""
from __future__ import annotations

import re

RECOMMEND_CUES = (
    "recommend",
    "top pick",
    "best choice",
    "best option",
    "you should",
    "we suggest",
    "i suggest",
    "go with",
    "ideal for",
    "well suited",
    "good fit",
    "strong option",
    "worth considering",
    "choose kasparro",
    "use kasparro",
)
NEGATIVE_CUES = (
    "no evidence",
    "no public",
    "limited",
    "lack",
    "unclear",
    "unverified",
    "caution",
    "risk",
    "concern",
    "poor fit",
    "weak",
    "avoid",
    "cannot",
    "unable",
)
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n+")
NUMBERED_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?\(?(\d{1,2})[.)]\s")


def baseline_labels(answer_text: str) -> dict:
    folded = answer_text.casefold()
    mentioned = "kasparro" in folded
    brand_sentences = [
        piece.casefold() for piece in SENTENCE_BREAK.split(answer_text) if "kasparro" in piece.casefold()
    ]
    position = None
    for line in answer_text.splitlines():
        if "kasparro" in line.casefold():
            match = NUMBERED_LINE.match(line)
            if match:
                position = int(match.group(1))
                break
    return {
        "brand_mentioned": mentioned,
        "recommended": mentioned
        and any(cue in sentence for sentence in brand_sentences for cue in RECOMMEND_CUES),
        "negative_characterization": mentioned
        and any(cue in sentence for sentence in brand_sentences for cue in NEGATIVE_CUES),
        "observable_position": position,
    }
