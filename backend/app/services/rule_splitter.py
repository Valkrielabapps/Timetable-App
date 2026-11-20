"""
A pasted message into the rules in it, one sentence each.

Coordinators send rules the way they send everything else - a WhatsApp
forward with its timestamp, "Respected Sir, please find the requests below",
numbered or bulleted or all in one paragraph, two rules in one line, and
"Thanks 🙏" at the end:

    [20/11/25, 9:14 am] Principal: Sir pls note the following for next year's TT:
    1) Priya is off on Monday and can't take more than 4 periods a day
    2) No PE in the last period; Ravi leaves after lunch
    Thanks 🙏

split_rules() gives the rule parser one rule at a time:

    Priya is off on Monday
    Priya can't take more than 4 periods a day
    No PE in the last period
    Ravi leaves after lunch

Nothing here decides what a rule means. It only takes away what isn't a rule
and cuts at the places a person would: a new sentence, a semicolon, "also",
or an "and" that starts a new rule (a new name, "no ...", or a verb whose
person is the one before it - who is then written in, so each piece reads
on its own). "Only on Mon, Wed and Fri" and "Thu morning and Mon afternoon"
are never cut: an "and" before a day, a time or a number joins a list.
"""
from __future__ import annotations

import re

_STAMP = re.compile(r"^\s*\[\d{1,2}/\d{1,2}/\d{2,4},?\s*[^\]]{1,20}\]\s*[^:\n]{1,40}:\s*"   # [20/11/25, 9:14 am] Name:
                    r"|^\s*\d{1,2}/\d{1,2}/\d{2,4},?\s*\d{1,2}:\d{2}\s*(?:[ap]m)?\s*-\s*[^:\n]{1,40}:\s*", re.I)
_MARKER = re.compile(r"^\s*(?:\(?\d{1,2}[.)]|\(?[a-hA-H]\)|[-–•*·▪➢>→]+|\d{1,2}\s*[-–])\s*")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]+")
_DAYS = r"(?:mon|tue|tues|wed|thu|thur|thurs|fri|sat|sun)(?:day|s|\.)?"
_SIGNAL = re.compile(
    rf"\b(?:{_DAYS}|periods?|lessons?|classes|class|only|not|no|avoid|never|leaves?|leaving|off|available|"
    r"before|after|max|maximum|minimum|more than|less than|fewer than|at least|at most|first|last|morning|"
    r"afternoon|lunch|break|free|double|consecutive|together|same day|in a row|per day|a day|a week|"
    r"weekly|daily|part[- ]time|comes?|reach(?:es)?|late|early|teach(?:es)?|prefer|should|must|can'?t|"
    r"cannot|won'?t|don'?t)\b|\d", re.I)
_GREETING = re.compile(r"^\s*(?:(?:hello|hi|hey|dear|respected|good\s+(?:morning|eve(?:ning)?|afternoon)|greetings)"
                       r"\b[^,.:!\n]*[,.:!]?\s*)+", re.I)
_SIGNOFF = re.compile(r"^\s*(?:thanks?(?:\s*you)?|thank\s*u|regards|warm regards|best regards|yours (?:truly|faithfully|"
                      r"sincerely)|sent from my \w+|with regards|ok\s*sir|noted)\b", re.I)
_INTRO = re.compile(r"\b(?:pls|please|kindly)\b.*\b(?:note|find|following|below|requests?|points?)\b|"
                    r"\b(?:the following|as follows|below are|requests? (?:for|from))\b", re.I)
# Words that start a new rule after "and" / "," with nothing carried over.
_NEW_RULE = re.compile(r"^(?:no|avoid|don'?t|do not|never|not more|max(?:imum)?|keep|give|put|make|let|"
                       r"all|every|each|only)\b", re.I)
# A verb whose subject is the person named before it.
_CARRY = re.compile(r"^(?:can|can'?t|cannot|could|should|shouldn'?t|must|mustn'?t|will|won'?t|would|is|isn'?t|"
                    r"was|has|hasn'?t|have|needs?|wants?|prefers?|leaves?|comes?|reach(?:es)?|takes?|teach(?:es)?|"
                    r"may|might|does|doesn'?t|only|also|goes|works?|is not|not available|won'?t be)\b", re.I)
# An "and" in front of these joins a list, it doesn't start a rule.
_LIST_ITEM = re.compile(rf"^(?:{_DAYS}|\d|period|lesson|morning|afternoon|evening|first|last|the (?:first|last)|"
                        r"lunch|break|before|after|grade|class|std|section|[ivx]+\b|[a-h]\b)", re.I)


def _has_rule(text: str, names: list[str]) -> bool:
    low = text.lower()
    return bool(_SIGNAL.search(text)) or any(n and n.lower() in low for n in names)


def _clean_line(line: str) -> str:
    line = _EMOJI.sub(" ", _STAMP.sub("", line))
    line = _MARKER.sub("", line)
    return re.sub(r"\s+", " ", line).strip(" \t,")


def _subject(clause: str, teacher_names: list[str]) -> str:
    """The person (or subject) a clause is about: a name it starts with, else
    the words before its first verb."""
    low = clause.lower()
    best = ""
    for n in teacher_names:
        for form in {n, n.split()[0]}:
            f = form.lower()
            if low.startswith(f) and len(f) > len(best) and (len(low) == len(f) or not low[len(f)].isalpha()):
                best = clause[:len(form)]
    if best:
        return best
    # "No classes for Jayanthi Begum on Tue": the person named in it.
    found = [(low.find(f.lower()), form) for n in teacher_names for form in {n, n.split()[0]}
             for f in [form] if len(f) >= 3 and re.search(rf"\b{re.escape(f.lower())}\b", low)]
    if found:
        pos, form = min(found, key=lambda x: (x[0], -len(x[1])))
        return clause[pos:pos + len(form)]
    m = re.match(r"^((?:(?:mrs|mr|ms|miss|dr)\.?\s*)?[A-Za-z.'\s]{2,40}?)\s+(?=" + _CARRY.pattern[1:] + r")",
                 clause, re.I)
    if m and len(m.group(1).split()) <= 4 and not _NEW_RULE.match(m.group(1)):
        return m.group(1).strip(" -–:,")
    m = re.match(r"^([^-–:]{2,40}?)\s*[-–:]\s+", clause)   # "Ravi - only Mon to Wed"
    return m.group(1).strip() if m else ""


def _cut_ands(sentence: str, teacher_names: list[str], subject_names: list[str]) -> list[str]:
    """", and" / " and" where a new rule starts."""
    known = [n.lower() for n in teacher_names + subject_names if n] + \
        [n.split()[0].lower() for n in teacher_names if n and len(n.split()[0]) >= 3]
    parts = re.split(r"(,?\s+and\s+|,\s+(?=no\b|avoid\b))", sentence, flags=re.I)
    out = [parts[0]]
    i = 1
    while i < len(parts):
        joiner, right = parts[i], parts[i + 1] if i + 1 < len(parts) else ""
        r = right.strip()
        rl = re.sub(r"^(?:mrs|mr|ms|miss|dr|smt|shri|sri)\.?\s*", "", r.lower())
        starts_name = any(rl.startswith(k) and (len(rl) == len(k) or not rl[len(k)].isalpha()) and
                          len(rl) > len(k) + 3 for k in known)
        # Only cut when what comes before is a rule on its own: "PE and Games
        # should not be on the same day" is one rule about two subjects.
        whole = bool(_SIGNAL.search(out[-1]))
        if r and whole and not _LIST_ITEM.match(r) and re.match(r"^(?:not more|max(?:imum)?|only)\b", r, re.I) \
                and _subject(out[-1], teacher_names):
            out.append(f"{_subject(out[-1], teacher_names)} {r}")   # "... and not more than 30 a week"
        elif r and whole and not _LIST_ITEM.match(r) and (_NEW_RULE.match(r) or starts_name):
            out.append(r)
        elif r and whole and not _LIST_ITEM.match(r) and _CARRY.match(r):
            who = _subject(out[-1], teacher_names)
            out.append(f"{who} {r}" if who else r)
        else:
            out[-1] = out[-1] + joiner + right
        i += 2
    return out


def split_rules(text: str, teacher_names=(), subject_names=()) -> list[str]:
    """Every rule in a pasted message, one sentence each, chrome removed."""
    teacher_names, subject_names = list(teacher_names), list(subject_names)
    names = teacher_names + subject_names
    lines = [_clean_line(ln) for ln in (text or "").splitlines()]
    pieces: list[str] = []
    for ln in lines:
        if not ln:
            continue
        ln = _GREETING.sub("", ln).strip(" ,")
        ln = ln.lstrip(".").strip()
        if not ln.strip(". ") or _SIGNOFF.match(ln):
            continue
        if ln.endswith(":") or (_INTRO.search(ln) and not _has_rule(_INTRO.sub(" ", ln), names)):
            continue
        if not _has_rule(ln, names):
            continue  # "Coordinator", "Respected Sir, please find the requests below"
        # Sentences: ". " before a capital, ";", "Also".
        line_pieces: list[str] = []
        for sent in re.split(r"(?<=[a-z0-9)])(?<!\bmr)(?<!\bmrs)(?<!\bms)(?<!\bdr)(?<!\bsmt)(?<!\bsh)(?<!\bsr)(?<!\bst)(?<!\bno)\.\s+(?=[A-Z])|;\s*|\.\s*(?=also\b)|,\s*(?=also\b)", ln, flags=re.I):
            sent = re.sub(r"^also\b[,:]?\s*", "", sent.strip(" .,"), flags=re.I)
            if not sent or not _has_rule(sent, names):
                continue
            for p in _cut_ands(sent, teacher_names, subject_names):
                p = p.strip(" .,")
                if p and _has_rule(p, names):
                    line_pieces.append(p[0].upper() + p[1:])
        # A line that is one rule is passed on exactly as typed.
        if len(line_pieces) == 1 and line_pieces[0].lower() == ln.strip(" .,").lower():
            line_pieces = [ln.strip(" ,")]
        pieces += line_pieces
    return list(dict.fromkeys(pieces))
