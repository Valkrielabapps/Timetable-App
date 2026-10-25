"""
Pick the worked examples worth showing the rule parser for one sentence.

The examples are what teach the model to read school rules - every accuracy
gain in the evaluation runs came from adding one - but sending all of them on
every call has a ceiling: the prompt grows with each, and a long list of
loosely related examples dilutes the few that matter for the sentence in hand.

So the library is split in two:

  core       a dozen examples that span every form and the contrasts that are
             easiest to get wrong (a daily vs a weekly cap, one order vs both).
             Always sent, and cached with the rest of the stable prompt.
  retrieved  the K examples closest to this sentence, chosen here. Sent after
             the cache breakpoint, so they cost a few hundred uncached tokens
             and leave the cached prefix identical from call to call.

"Closest" is deliberately simple and deterministic: shared words, plus shared
*concepts*. "back to back", "in a row" and "consecutive" are different words
for one idea, and a sentence saying any of them should pull in the examples
saying the others. No embeddings, no network call, no new dependency - and the
same sentence always gets the same examples, which the evaluation relies on.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    typed: str   # the sentence, as a school would type it
    body: str    # the whole block shown to the model: sentence, rule, note


# Phrases that mean the same scheduling idea, folded into one concept token.
# Order does not matter; a sentence can carry several.
_CONCEPTS: dict[str, tuple[str, ...]] = {
    "C_RUN": (r"in a row", r"back[\s-]*to[\s-]*back", r"consecutive", r"continuous", r"double", r"together",
              r"one after (?:the )?other", r"straight", r"stretch"),
    "C_ADJ": (r"\bafter\b", r"\bbefore\b", r"follow", r"next to", r"immediately", r"precede", r"\bthen\b"),
    "C_SAMEDAY": (r"same day", r"different days?", r"\bdiff days?\b", r"separate days?"),
    "C_SAMETIME": (r"same time", r"same period", r"simultaneous", r"parallel", r"at once"),
    "C_DAYNAME": (r"\bmon(day)?\b", r"\btue(s|sday)?\b", r"\bwed(nesday)?\b", r"\bthu(rs|rsday)?\b",
                  r"\bfri(day)?\b", r"\bsat(urday)?\b", r"weekday"),
    "C_DAYOFF": (r"day off", r"days? off", r"off on", r"doesn'?t come", r"not come", r"\bonly (?:comes|works|on)\b",
                 r"available", r"leave", r"\bfree day\b"),
    "C_POSITION": (r"first period", r"last period", r"\b1st\b", r"\blast\b", r"\bp\d\b", r"period \d", r"\bmorning",
                   r"afternoon", r"lunch", r"break", r"zero period"),
    "C_LUNCH": (r"lunch", r"\bbreak\b", r"interval"),
    "C_MAX": (r"at ?most", r"\bmax", r"not more than", r"no more than", r"more than", r"up ?to", r"limit", r"exceed",
              r"\bcap\b"),
    "C_MIN": (r"at ?least", r"\bmin(imum)?\b", r"\bevery day\b", r"\bdaily\b", r"must have", r"should have"),
    "C_ONLY": (r"\bonly\b", r"\bjust\b"),
    "C_NEVER": (r"\bnever\b", r"\bno\b", r"\bnot\b", r"don'?t", r"can'?t", r"shouldn'?t", r"\bavoid"),
    "C_DISTINCT": (r"different subjects?", r"\bdiff(erent)? subj", r"same teacher", r"same period every",
                   r"vary", r"each section diff"),
    "C_BALANCE": (r"even(ly)?", r"spread", r"balanced?", r"roughly (?:the )?same", r"equal"),
    "C_SPAN": (r"free periods?", r"\bgaps?\b", r"\bidle\b", r"\bprep\b", r"within \d", r"continuous periods"),
    "C_COND": (r"^if\b", r"\bif\b", r"on days", r"\bwhen(ever)?\b", r"on the days"),
    "C_PREF": (r"\btry\b", r"prefer", r"if possible", r"where possible", r"ideally", r"would like", r"would be nice",
               r"as much as poss", r"\bpls\b", r"\bplease\b"),
    "C_OOS": (r"\broom\b", r"\blab\b", r"\bhall\b", r"\bjan(uary)?\b", r"\bfeb", r"\bnov", r"\bdec", r"\bexam",
              r"\b\d{1,2}(st|nd|rd|th)? (?:of )?(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
              r"equipment", r"projector", r"tabs?\b"),
    "C_TEACHER": (r"\bsir\b", r"\bma'?a?m\b", r"\bmadam\b", r"\bmiss\b", r"\bmrs?\.?\b", r"\bms\.?\b",
                  r"\bteachers?\b", r"\bnobody\b", r"\bpart[\s-]*time\b"),
    "C_CLASS": (r"\bgrade\b", r"\bclass(es)?\b", r"\bstd\b", r"\bsections?\b", r"\b\d{1,2}(st|nd|rd|th)\b",
                r"\b\d{1,2}\s?[a-e]\b"),
    "C_WEEK": (r"\bweek\b", r"\bweekly\b", r"a week", r"per week", r"in the week"),
    "C_DAY": (r"\ba day\b", r"per day", r"\bdaily\b", r"in a day", r"each day", r"any day", r"every day"),
    "C_VAGUE": (r"\bnice\b", r"\bhappy\b", r"\bgood\b", r"\bbalanced\b", r"\bfair\b"),
}
_COMPILED = {c: [re.compile(p, re.IGNORECASE) for p in pats] for c, pats in _CONCEPTS.items()}

_STOP = {
    "the", "a", "an", "of", "to", "for", "in", "on", "and", "or", "is", "be", "should", "shd", "must", "any",
    "it", "its", "that", "this", "with", "by", "at", "as", "are", "has", "have", "her", "his", "their", "them",
    "she", "he", "they", "we", "our", "all", "each", "every", "per", "can", "will", "would", "do", "does",
}


def _features(text: str) -> set[str]:
    low = text.lower()
    words = {w.rstrip("s") for w in re.findall(r"[a-z]+", low) if w not in _STOP and len(w) > 1}
    concepts = {c for c, pats in _COMPILED.items() if any(p.search(low) for p in pats)}
    return words | concepts


def parse_library(text: str) -> tuple[list[Example], list[str]]:
    """Split the examples text into (examples, guidance paragraphs).

    A block that opens with a quoted sentence is an example; any other block is
    guidance ("A two-sided form needs its sides to be DIFFERENT lessons...")
    and is always sent, since it is short and applies everywhere.
    """
    examples, guidance = [], []
    for block in re.split(r"\n\s*\n", text.strip()):
        block = block.strip("\n")
        if not block or block.strip() == "Worked examples:":
            continue
        if block.startswith('"'):
            end = block.find('"', 1)
            examples.append(Example(typed=block[1:end] if end > 0 else block, body=block))
        else:
            guidance.append(block)
    return examples, guidance


class Library:
    def __init__(self, examples: list[Example], core_typed: set[str]):
        self.examples = examples
        self.core = [e for e in examples if e.typed in core_typed]
        missing = core_typed - {e.typed for e in self.core}
        if missing:
            raise ValueError(f"core examples not in the library: {sorted(missing)}")
        self.rest = [e for e in examples if e.typed not in core_typed]
        self._feats = [(_features(e.typed), e) for e in self.rest]
        # Rarer features say more: "lunch" matching is worth more than "not".
        n = len(self._feats) or 1
        df: dict[str, int] = {}
        for feats, _ in self._feats:
            for f in feats:
                df[f] = df.get(f, 0) + 1
        self._idf = {f: math.log(1 + n / d) for f, d in df.items()}

    def closest(self, sentence: str, k: int = 12) -> list[Example]:
        """The k non-core examples most like `sentence`, best first. Ties keep
        library order, so the result is the same on every call."""
        want = _features(sentence)
        scored = []
        for i, (feats, ex) in enumerate(self._feats):
            shared = want & feats
            if not shared:
                continue
            score = sum(self._idf.get(f, 0) * (2.0 if f.startswith("C_") else 1.0) for f in shared)
            # A long example shares words by sheer length; don't let that win.
            score /= math.sqrt(len(feats))
            scored.append((-score, i, ex))
        scored.sort()
        return [ex for _, _, ex in scored[:k]]
