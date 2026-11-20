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

# Hinglish words that carry the rule's meaning. Common in North Indian schools'
# WhatsApp messages; the model usually knows them, but "baad" vs "pehle" is the
# whole rule, so it is spelled out rather than left to chance.
_HINGLISH = {
    "baad": "after", "turant": "immediately", "fauran": "immediately", "lagatar": "back to back", "bad": None, "pehle": "before", "pahle": "before", "sirf": "only", "bas": None,
    "mat": "don't", "nahi": "not", "nahin": "not", "na": None, "zyada": "more", "jyada": "more",
    "kam": "fewer", "kabhi": "ever", "hamesha": "always", "roz": "every day", "rozana": "every day",
    "din": "day", "hafte": "week", "hafta": "week", "ek": "one", "do": None, "teen": "three", "char": "four",
    "somvar": "Monday", "mangalvar": "Tuesday", "budhvar": "Wednesday", "guruvar": "Thursday",
    "brihaspativar": "Thursday", "shukravar": "Friday", "shanivar": "Saturday", "ravivar": "Sunday",
    "ke": None, "ko": None, "mein": "in", "chahiye": "should", "dena": "give", "rakho": "put",
    "lagao": "schedule", "jana": "leave", "jaana": "leave", "aana": "come", "ata": "come", "aata": "come",
}

# Hinglish words that are never English, so they are glossed even alone.
_HINGLISH_SURE = {"turant", "lagatar", "baad", "pehle", "pahle", "sirf", "nahi", "nahin", "zyada", "jyada", "kabhi", "hamesha",
                  "rozana", "hafte", "chahiye", "somvar", "mangalvar", "budhvar", "guruvar", "brihaspativar",
                  "shukravar", "shanivar", "ravivar"}

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
    words = re.findall(r"[a-z0-9']+", text.lower())
    # Hinglish only when the sentence is clearly in it, so "do" and "bad" in an
    # English sentence aren't translated.
    hinglish = sum(w in _HINGLISH for w in words) >= 2
    for word in words:
        meaning = _SPELLINGS.get(word) or (_HINGLISH.get(word) if hinglish or word in _HINGLISH_SURE else None)
        if meaning and f"'{word}' = {meaning}" not in found:
            found.append(f"'{word}' = {meaning}")
    return found


def _misspelt_subject_hints(text: str, subject_names: list[str]) -> list[str]:
    """'libry' = Library, 'chemestry' = Chemistry: one or two letters off a
    subject the school has, and not a near-miss of anything else."""
    out = []
    singles = {s.lower(): s for s in subject_names if " " not in s}
    for word in set(re.findall(r"[a-z]+", text.lower())):
        if len(word) < 5 or word in singles:
            continue
        close = [s for low, s in singles.items() if len(low) >= 5 and _edits(word, low) <= (1 if len(low) < 7 else 2)]
        if len(close) == 1:
            out.append(f"'{word}' = {close[0]}")
    return out


def _edits(a: str, b: str) -> int:
    """Levenshtein distance, early-out above 2."""
    if abs(len(a) - len(b)) > 2:
        return 3
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _phrases(text: str, longest: int = 3):
    """Every run of one to three words, as typed, without edge punctuation."""
    words = text.split()
    for n in range(longest, 0, -1):
        for i in range(len(words) - n + 1):
            phrase = " ".join(words[i:i + n]).strip(",;:!?()\"'")
            if phrase:
                yield phrase


def _alias_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def typed_short_forms(text: str, short_forms: dict | None) -> dict[str, str]:
    """{name in lower case: short form as typed} for every short form the
    school confirmed that this sentence uses ("BEAUL", "S. Sc.")."""
    out: dict[str, str] = {}
    if not short_forms or not text:
        return out
    for phrase in _phrases(text):
        k = _alias_key(phrase)
        if len(k) < 2:
            continue
        for kind in ("teacher", "subject"):
            name = (short_forms.get(kind) or {}).get(k)
            if name and name.lower() not in out:
                out[name.lower()] = phrase
    return out


def _short_form_hints(text: str, short_forms: dict | None) -> list[str]:
    """The school's own confirmed short forms, which it was told it would
    never be asked about again: 'BEAUL' = Beula Rao."""
    hints = []
    if not short_forms:
        return hints
    for kind in ("teacher", "subject"):
        forms = short_forms.get(kind) or {}
        seen = set()
        for phrase in _phrases(text):
            k = _alias_key(phrase)
            if len(k) >= 2 and k in forms and k not in seen and phrase.lower() != forms[k].lower():
                seen.add(k)
                hints.append(f"'{phrase}' = {forms[k]} (the school's own short form)")
    return hints


_CLOCK = re.compile(r"(?<![\d:.])(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?|o'?clock|hrs)?(?![\d:])", re.I)
_CLOCK_CONTEXT = re.compile(r"\b(?:at|by|after|before|till|until|upto|up to|from|to|since|past)\s*$", re.I)


def period_times(periods) -> list[tuple[int, int, int]]:
    """[(period number, start minute, end minute)] from the school's period
    labels that carry their times ("Period 3 (10:20-11:00)", "10:20 - 11:00"),
    Monday's - or the first day that has them."""
    by_day: dict[int, list] = {}
    for p in periods or []:
        day, order, label, kind = (list(p) + [None, None, None, None])[:4]
        # The fourth value is the slot's kind ("lesson", "break"...), or in
        # older callers whether it is a break.
        if kind is True or (isinstance(kind, str) and kind != "lesson"):
            continue
        m = re.search(r"(\d{1,2})[:.](\d{2})\s*(?:-|–|to)\s*(\d{1,2})[:.](\d{2})", str(label or ""))
        if m:
            by_day.setdefault(day, []).append((order, _minutes(int(m.group(1)), int(m.group(2))),
                                               _minutes(int(m.group(3)), int(m.group(4)))))
    for day in sorted(by_day):
        rows = sorted(by_day[day])
        if len(rows) >= 3:
            return [(i, a, b) for i, (_, a, b) in enumerate(rows, start=1)]
    return []


def _minutes(h: int, m: int) -> int:
    # A school day runs about 7:00 to 18:00: "1:20" written without pm is 13:20.
    return (h + 12 if h < 7 else h) * 60 + m


def _clock_hints(text: str, periods) -> list[str]:
    """'12.40' = the start of period 6: clock times as the school's periods,
    from the bell times on its period labels."""
    times = period_times(periods)
    if not times:
        return []
    out = []
    for m in _CLOCK.finditer(text):
        h, mm, suffix = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if not m.group(2) and not suffix:
            # A bare number is a time only after "at", "by", "after"...: "after 1", not "period 1".
            if not _CLOCK_CONTEXT.search(text[:m.start()]) or h > 12:
                continue
        if h > 23 or mm > 59:
            continue
        if suffix.startswith("p") and h < 12:
            h += 12
        minute = h * 60 + mm if suffix.startswith(("a", "p")) or h >= 7 else _minutes(h, mm)
        written = m.group(0).strip()
        start = next((n for n, a, _ in times if a == minute), None)
        end = next((n for n, _, b in times if b == minute), None)
        inside = next((n for n, a, b in times if a < minute < b), None)
        last = times[-1][0]
        if start:
            before = f"periods 1-{start - 1}" if start > 2 else ("period 1" if start == 2 else "no period")
            after = f"periods {start}-{last}" if start < last else f"period {last}"
            out.append(f"'{written}' = the start of period {start} (before it: {before}; from it on: {after})")
        elif end:
            after = f"periods {end + 1}-{last}" if end + 1 < last else (f"period {last}" if end < last else "none")
            out.append(f"'{written}' = the end of period {end} (up to it: periods 1-{end}; after it: {after})")
        elif inside:
            out.append(f"'{written}' falls during period {inside}")
        elif minute < times[0][1]:
            out.append(f"'{written}' is before the school day starts")
        elif minute >= times[-1][2]:
            out.append(f"'{written}' is after the last period")
    return list(dict.fromkeys(out))


def sentence_hints(text: str, teacher_names: list[str], subject_names: list[str],
                   class_group_labels: list[str], short_forms: dict | None = None, periods=None) -> list[str]:
    """Hints for the parser, each "'as typed' = as the school stores it".
    `short_forms`: what the school confirmed in its imports (services/aliases.py),
    read before the built-in guesses and taking their place."""
    try:
        own = _short_form_hints(text, short_forms)
        mine = {h.split("'")[1].lower() for h in own}
        built_in = [h for h in _teacher_hints(text, teacher_names) + _class_hints(text, class_group_labels)
                    + _subject_hints(text, subject_names) + _misspelt_subject_hints(text, subject_names)
                    if h.split("'")[1].lower() not in mine]
        return own + built_in + _clock_hints(text, periods) + _spelling_hints(text)
    except Exception:  # noqa: BLE001 - reading aids must never break parsing
        return []

