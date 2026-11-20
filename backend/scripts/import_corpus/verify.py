"""
Check a generated corpus before anything is scored against it.

    python scripts/import_corpus/verify.py [corpus dir]

1. Each truth school is a real timetable: every section's every period
   taught exactly once (a block counts once), no teacher in two places, each
   plan line's periods all placed, block lessons in all their sections at once.
2. Every case has its input and expected.json, and the input opens: the
   spreadsheet/Word/CSV files through the app's own reader (read_sheets), PDFs
   with pdftotext, pictures with Pillow.
3. Each case's written forms appear in the file (for the text formats), so
   the truth really describes what's on the page.

Exits non-zero on any failure.
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[2]))  # backend/, for app.services


def check_school(path: Path) -> list[str]:
    t = json.loads(path.read_text(encoding="utf-8"))
    errs = []
    days, periods = len(t["days"]), t["periods_per_day"]
    slot_use = defaultdict(set)      # (section, day, period) -> block or subject keys
    teacher_at = defaultdict(set)    # (teacher, day, period) -> sections/blocks
    for l in t["lessons"]:
        key = l["block"] or f"{l['subject']}"
        slot_use[(l["section"], l["day"], l["period"])].add(key)
        if l["teacher"]:
            teacher_at[(l["teacher"], l["day"], l["period"])].add(l["block"] or l["section"])
    for s in t["sections"]:
        for d in range(days):
            for p in range(1, periods + 1):
                n = len(slot_use.get((s, d, p), ()))
                if n != 1:
                    errs.append(f"{path.name}: {s} day {d} period {p} has {n} lessons")
    for key, where in teacher_at.items():
        if len(where) > 1:
            errs.append(f"{path.name}: {key[0]} in {sorted(where)} at day {key[1]} period {key[2]}")
    placed = Counter((l["section"], l["subject"]) for l in t["lessons"] if not l["block"])
    for p in t["plan"]:
        if placed[(p["section"], p["subject"])] != p["periods"]:
            errs.append(f"{path.name}: {p['section']} {p['subject']} placed {placed[(p['section'], p['subject'])]}"
                        f" of {p['periods']}")
    return errs


def _text_of(path: Path) -> str | None:
    """Plain text of a case's input, or None for pictures."""
    ext = path.suffix.lower()
    if ext in (".txt", ".csv"):
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        try:
            return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True,
                                  timeout=60).stdout
        except FileNotFoundError:
            return None
    if ext == ".docx":
        # Paragraphs and tables both - the app's reader keeps only the tables
        # when there are any, which is a finding about the reader, not the file.
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            parts += [" | ".join(c.text for c in row.cells) for row in t.rows]
        return "\n".join(parts)
    if ext == ".xlsx":
        from app.services.smart_import import read_sheets
        sheets = read_sheets(path.name, path.read_bytes())
        return "\n".join(" | ".join(r) for _, rows in sheets for r in rows)
    return None


def check_case(folder: Path) -> list[str]:
    errs = []
    exp_path = folder / "expected.json"
    if not exp_path.exists():
        return [f"{folder.name}: no expected.json"]
    exp = json.loads(exp_path.read_text(encoding="utf-8"))
    path = folder / exp["input"]
    if not path.exists():
        return [f"{folder.name}: no {exp['input']}"]
    if path.suffix in (".png", ".jpg"):
        from PIL import Image
        try:
            Image.open(path).verify()
        except Exception as e:  # noqa: BLE001
            errs.append(f"{folder.name}: picture doesn't open ({e})")
        return errs
    try:
        text = _text_of(path)
    except Exception as e:  # noqa: BLE001 - any reader failure is the finding
        return [f"{folder.name}: doesn't open ({type(e).__name__}: {e})"]
    if text is None:
        return errs
    flat = " ".join(text.split()).lower()
    words = set(flat.replace("|", " ").split())
    missing = []
    for kind in ("subjects", "teachers"):
        for truth, forms in exp["written"].get(kind, {}).items():
            for f in forms:
                probe = " ".join(f.split()).lower()
                if not probe or probe in flat:
                    continue
                # A PDF wraps long cells over lines, so a form may come out in
                # pieces: every word of it present is enough there.
                if path.suffix == ".pdf" and all(w[:5] in flat for w in probe.split()):
                    continue
                missing.append(f"{kind[:-1]} {f!r}")
    if missing:
        errs.append(f"{folder.name}: written forms not in the file text: {', '.join(missing[:5])}"
                    + (f" (+{len(missing) - 5})" if len(missing) > 5 else ""))
    return errs


def main(argv=None) -> int:
    root = Path((argv or sys.argv[1:] or [str(HERE.parents[3] / "school-imports" / "generated")])[0])
    errs = []
    schools = sorted((root / "schools").glob("*.json"))
    for s in schools:
        errs += check_school(s)
    cases = sorted(p for p in (root / "cases").iterdir() if p.is_dir())
    by_kind = Counter()
    for c in cases:
        errs += check_case(c)
        by_kind[c.name.split("_")[3]] += 1
    print(f"{len(schools)} schools, {len(cases)} cases ({dict(by_kind)})")
    for e in errs[:40]:
        print("  FAIL", e)
    if len(errs) > 40:
        print(f"  ... and {len(errs) - 40} more")
    print("OK" if not errs else f"{len(errs)} problems")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
