"""
Reading aids for one rule sentence, worked out from the school's own data.

Schools don't type names the way the database stores them. "rao maam",
"khan sir", "6th std", "9A", "PT" and "maths" all have to become Mrs. Rao,
Mr. Khan, Grade 6, Grade 9 - A, PE and Mathematics before a rule can name them -
and the parser is told to use only names that appear verbatim in the school's
lists. Left to the model, a nickname is a coin toss between guessing and
declining with "unknown reference".

This does the matching deterministically, before the model sees the sentence,
and hands it over as hints ("'rao maam' = Mrs. Rao"). Hints, not a rewrite: the
sentence itself is never changed, so a wrong hint can be overruled by the model
and can never silently alter what the admin typed. A hint is only offered when
exactly one thing in the school matches; two candidates means no hint, and the
model asks, as it would have anyway.
"""
from __future__ import annotations

import re

_HONORIFICS = r"(?:sir|ma'?a?m|madam|miss|teacher|tr|mrs\.?|mr\.?|ms\.?|dr\.?|fr\.?|coach)"
_TITLE_WORDS = {"mr", "mrs", "ms", "miss", "dr", "fr", "coach", "sir", "madam", "teacher", "prof"}

# Informal subject names -> words that identify the subject in the school's list.
_SUBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "maths": ("math",), "math": ("math",), "mathematics": ("math",),
    "pe": ("physical education", "pe", "p.e", "games", "pt", "sports"),
    "pt": ("physical education", "pe", "p.e", "games", "pt", "sports"),
    "games": ("physical education", "pe", "p.e", "games", "pt", "sports"),
    "p.e": ("physical education", "pe", "p.e", "games", "pt", "sports"),
    "eng": ("english",), "english": ("english",),
    "sci": ("science",), "science": ("science",),
    "sst": ("social",), "social": ("social",), "soc": ("social",), "evs": ("environment", "evs"),
    "comp": ("computer",), "computers": ("computer",), "cs": ("computer",),
    "hin": ("hindi",), "bio": ("biology",), "chem": ("chemistry",), "phy": ("physics",), "phys": ("physics",),
    "lib": ("library",), "mal": ("malayalam",), "sans": ("sanskrit",), "geo": ("geograph",), "hist": ("histor",),
    "acc": ("accountancy", "accounts"), "eco": ("economics",), "bst": ("business",),
}

_SPELLINGS = {
    "shd": "should", "shld": "should", "atleast": "at least", "atmost": "at most", "b4": "before",
    "aftr": "after", "dont": "don't", "cant": "can't", "wont": "won't", "shouldnt": "shouldn't",
    "doesnt": "doesn't", "isnt": "isn't", "wk": "week", "pls": "please", "plz": "please",
    "diff": "different", "btw": "between", "thru": "through", "frm": "from", "nd": "and",
    "perod": "period", "periods": None, "practicle": "practical", "libary": "library",
}

_ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
          "xi": 11, "xii": 12}


def _name_core(name: str) -> list[str]:
    """'Mrs. Rao' -> ['rao']; 'Coach Biju' -> ['biju']; 'Arjun Kumar' -> ['arjun', 'kumar']."""
    words = [w.strip(".").lower() for w in name.split()]
    return [w for w in words if w and w not in _TITLE_WORDS and len(w) >= 3]


def _near(a: str, b: str) -> bool:
    """Same word, or one letter off for longer words ('priyaa', 'pria')."""
    if a == b:
        return True
    if min(len(a), len(b)) < 5 or abs(len(a) - len(b)) > 1:
        return False
    # Levenshtein distance <= 1
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


def _teacher_hints(text: str, teacher_names: list[str]) -> list[str]:
    low = text.lower()
    if not teacher_names:
        return []
    words = re.findall(r"[a-z']+", low)
    hints, seen = [], set()
    for i, w in enumerate(words):
        if len(w) < 3 or w in _TITLE_WORDS:
            continue
        matches = [t for t in teacher_names if any(_near(w, c) for c in _name_core(t))]
        if len(matches) != 1:
            continue
        teacher = matches[0]
        if teacher.lower() in low or teacher in seen:
            continue  # already written the way the school stores it
        # Quote the phrase as typed, honorific included: "rao maam", "khan sir".
        m = re.search(rf"(?:{_HONORIFICS}\s+)?\b{re.escape(w)}\b(?:\s+{_HONORIFICS})?", low)
        phrase = m.group(0).strip() if m else w
        # A bare common word that happens to be a name ("das", "mary") is only
        # trusted with an honorific next to it, or when it is a longer name.
        honorific = bool(re.search(_HONORIFICS, phrase)) and phrase != w
        if not honorific and len(w) < 5:
            continue
        hints.append(f"'{phrase}' = {teacher}")
        seen.add(teacher)
    return hints


def _grade_number(label: str) -> int | None:
    m = re.search(r"(\d{1,2})", label)
    return int(m.group(1)) if m else None


def _class_hints(text: str, labels: list[str]) -> list[str]:
    """'6th std', 'class VI', '9A', '10th B', 'grade 9' -> the school's labels."""
    if not labels:
        return []
    grades = {}      # number -> grade label ("Grade 6")
    sections = {}    # (number, letter) -> section label ("Grade 6 - A")
    for label in labels:
        n = _grade_number(label)
        if n is None:
            continue
        m = re.match(r"^(.*?)\s*-\s*([A-Za-z0-9]+)$", label)
        if m:
            sections[(n, m.group(2).lower())] = label
        else:
            grades.setdefault(n, label)
    hints, seen = [], set()
    low = text.lower()
    patterns = [
        # 9A, 9-A, 9 A, 10th B, class 6 a  (a letter right after the number)
        r"(?:(?:class|grade|std|standard)\s*)?\b(?P<num>\d{1,2})(?:st|nd|rd|th)?\s*-?\s*(?P<sec>[a-e])\b(?!\w)",
        # 6th std, 6th standard, 10th, class 6, grade 6, std 6
        r"\b(?P<num>\d{1,2})(?:st|nd|rd|th)\b(?:\s*(?:std|standard|grade|class))?",
        r"\b(?:class|grade|std|standard)\s*(?P<num>\d{1,2})\b",
        r"\b(?:class|grade|std|standard)\s+(?P<roman>xii|xi|ix|x|viii|vii|vi|iv|v|iii|ii|i)\b",
    ]
    for pat in patterns:
        for m in re.finditer(pat, low):
            phrase = m.group(0).strip()
            after = low[m.end():m.end() + 8]
            if re.match(r"\s*(?:period|lesson|lecture|p\b)", after):
                continue  # "6th period" is a period, not a class
            num = m.groupdict().get("num")
            n = int(num) if num else _ROMAN.get(m.groupdict().get("roman") or "")
            if n is None:
                continue
            sec = m.groupdict().get("sec")
            target = sections.get((n, sec)) if sec else grades.get(n)
            if sec and target is None:
                continue
            if target is None or target.lower() in low or phrase in seen:
                continue
            seen.add(phrase)
            hints.append(f"'{phrase}' = {target}")
    return hints


def _subject_hints(text: str, subject_names: list[str]) -> list[str]:
    low = text.lower()
    hints = []
    for alias, keys in _SUBJECT_ALIASES.items():
        if not re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", low):
            continue
        if any(s.lower() == alias for s in subject_names):
            continue  # typed exactly as the school names it
        matches = [s for s in subject_names if any(k in s.lower() for k in keys)]
        # Two candidates ("Computer" and "Computer Science" for "comp") is a
        # question for the admin, not something to settle here.
        if len(matches) == 1 and not re.search(rf"(?<![a-z]){re.escape(matches[0].lower())}(?![a-z])", low):
            hints.append(f"'{alias}' = {matches[0]}")
    return hints


def _spelling_hints(text: str) -> list[str]:
    found = []
    for word in re.findall(r"[a-z0-9']+", text.lower()):
        meaning = _SPELLINGS.get(word)
        if meaning and f"'{word}' = {meaning}" not in found:
            found.append(f"'{word}' = {meaning}")
    return found


def sentence_hints(text: str, teacher_names: list[str], subject_names: list[str],
                   class_group_labels: list[str]) -> list[str]:
    """Hints for the parser, each "'as typed' = as the school stores it"."""
    try:
        return (_teacher_hints(text, teacher_names) + _class_hints(text, class_group_labels)
                + _subject_hints(text, subject_names) + _spelling_hints(text))
    except Exception:  # noqa: BLE001 - reading aids must never break parsing
        return []
