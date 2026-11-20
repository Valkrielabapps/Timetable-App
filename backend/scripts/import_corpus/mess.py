"""
The ways schools write names, seen in school-imports/public/samples.json and
the Keren files: short forms, cut-off names, titles, capitals, stray marks.

Every function takes the random.Random driving the case and returns the
written form; the caller records truth -> written so the scorer can tell a
correct reading of "S. Sc." from a wrong one.
"""
from __future__ import annotations

import random

from school import SUBJECTS

ROMAN = ["", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"]
WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven", 8: "Eight", 9: "Nine",
         10: "Ten", 11: "Eleven", 12: "Twelve"}


def subject(rng: random.Random, name: str, style: str) -> str:
    """'full' keeps the name; 'short' picks one of the school's short forms;
    'mixed' does either; 'caps' is the name in capitals."""
    forms = SUBJECTS.get(name, [])
    if style == "full":
        return name
    if style == "caps":
        return name.upper()
    if style == "short" and forms:
        return forms[0]
    if style == "mixed" and forms and rng.random() < 0.6:
        return rng.choice(forms)
    return name


def teacher(rng: random.Random, name: str, title: str, style: str) -> str:
    """How a teacher's name is written: 'plain', 'titled' (Mrs. Kavitha Rao),
    'caps' (MRS. KAVITHA RAO), 'initial' (K. Rao / Kavitha R), 'short' (cut to
    5 letters, Keren's BEAUL), 'first' (first name only), 'mixed' (any)."""
    parts = name.split()
    if style == "mixed":
        style = rng.choice(["plain", "titled", "caps", "initial", "first", "short"])
    if style == "plain":
        return name
    if style == "titled":
        return f"{title} {name}"
    if style == "caps":
        return f"{title.upper()}{name.upper()}" if rng.random() < 0.5 else name.upper()
    if style == "initial" and len(parts) > 1:
        return rng.choice([f"{parts[0][0]}. {parts[-1]}", f"{parts[0]} {parts[-1][0]}", f"{parts[-1]} {parts[0][0]}."])
    if style == "short":
        return parts[0][:5].upper()
    if style in ("first", "initial"):
        return parts[0]
    return name


def section(rng: random.Random, sec: str, style: str) -> str:
    """'7A' as '7A', '7-A', 'VII A', 'VII-A', 'Class 7 A', 'Grade 7 - A', 'Std VII A'."""
    g, s = int(sec[:-1]), sec[-1]
    forms = {
        "plain": f"{g}{s}", "dash": f"{g}-{s}", "roman": f"{ROMAN[g]} {s}", "roman_dash": f"{ROMAN[g]}-{s}",
        "class": f"Class {g} {s}", "grade": f"Grade {g} - {s}", "std": f"Std {ROMAN[g]} {s}",
        "class_roman": f"CLASS – {ROMAN[g]} - {s}",
    }
    if style == "mixed":
        style = rng.choice(list(forms))
    return forms.get(style, sec)


def noisy(rng: random.Random, text: str, level: float) -> str:
    """Occasional typing slips: a doubled space, a stray '|', a dropped letter,
    swapped neighbours. `level` 0..1 is how often."""
    if not text or rng.random() > level:
        return text
    kind = rng.choice(["space", "pipe", "drop", "swap", "trail"])
    if kind == "space":
        return text.replace(" ", "  ", 1)
    if kind == "pipe":
        return "|" + text
    if kind == "trail":
        return text + " "
    if len(text) < 4:
        return text
    i = rng.randrange(1, len(text) - 1)
    if kind == "drop":
        return text[:i] + text[i + 1:]
    return text[:i - 1] + text[i] + text[i - 1] + text[i + 1:]
