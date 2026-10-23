"""Contract and bounded intent helpers for insurance workflow guidance."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any


def contains_phrase(message: str, phrase: str) -> bool:
    """Match English words as words while retaining Chinese substring matching."""
    if phrase.isascii():
        return re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])",
                         message, re.IGNORECASE) is not None
    return phrase in message


def contains_any(message: str, phrases: tuple[str, ...]) -> bool:
    return any(contains_phrase(message, phrase) for phrase in phrases)


BUSINESS_TERMS = (
    "业绩", "業績", "保费", "保費", "目标", "目標", "竞赛", "競賽",
    "荣誉", "榮譽", "达标", "達標", "销售", "銷售", "mdrt", "cot",
    "ttt", "ida", "performance", "premium", "target", "goal", "sales",
)


class InsuranceSkill(ABC):
    """Deterministically match an intent and provide non-executable guidance."""

    name: str = ""
    trigger_keywords: tuple[str, ...] = ()
    description: str = ""
    priority: int = 50
    required_tools: tuple[str, ...] = ()

    def match_intent(self, user_message: str) -> bool:
        if not isinstance(user_message, str) or not user_message.strip():
            return False
        return contains_any(user_message, self.trigger_keywords)

    @abstractmethod
    def get_skill_prompt(self, context: dict[str, Any]) -> str:
        """Return bounded instructions referring only to verified available Tools."""
