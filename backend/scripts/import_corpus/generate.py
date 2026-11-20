"""
Generate the import test corpus: made-up schools whose every fact is known,
each written out in the messy layouts and file formats real schools send.

    python scripts/import_corpus/generate.py                  # 8 schools -> school-imports/generated
    python scripts/import_corpus/generate.py --schools 3 --seed 7 --out /tmp/corpus

Output (git-ignored - it reads like real people's names):

    <out>/schools/school_01.json      the truth for one school
    <out>/cases/<case id>/input.xlsx  what an importer is given
    <out>/cases/<case id>/expected.json
        kind      timetable | subjects | teachers | rules
        layout    which shape (layouts.py), format, options used
        school    which truth file
        shows     the sections / teachers this file actually contains
        written   how each truth value was written in it ("S. Sc." for Social Science)
    <out>/index.json                  every case, for the scorer

The same --seed always gives the same corpus, so a score can be compared
before and after a change.
"""
from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render  # noqa: E402
import school as school_mod  # noqa: E402
from layouts import RULE_LAYOUTS, SUBJECT_LAYOUTS, TEACHER_LAYOUTS, TIMETABLE_LAYOUTS  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

# Which formats each layout is sent in. Weighted by what schools actually send:
# mostly Excel, then PDF, then Word, then pictures.
FORMATS = {
    ("timetable", "class_grids"): ["xlsx_tabs", "xlsx_one", "pdf", "docx", "csv"],
    ("timetable", "keren"): ["xlsx_one", "xlsx_one", "pdf"],
    ("timetable", "transposed"): ["pdf", "docx", "xlsx_tabs"],
    ("timetable", "master"): ["xlsx_one", "csv"],
    ("timetable", "teacher_grids"): ["pdf", "xlsx_tabs", "xlsx_one"],
    ("subjects", "list"): ["xlsx_one", "csv", "docx"],
    ("subjects", "allotment"): ["xlsx_one", "pdf", "docx"],
    ("subjects", "by_grade"): ["docx", "xlsx_one", "txt"],
    ("teachers", "kv_table"): ["xlsx_one", "pdf", "csv"],
    ("teachers", "free_text"): ["xlsx_one", "csv"],
    ("teachers", "by_department"): ["xlsx_one", "docx", "pdf"],
    ("teachers", "allotment"): ["docx", "xlsx_one", "txt"],
    ("rules", "message"): ["txt"],
}
EXT = {"xlsx_tabs": "xlsx", "xlsx_one": "xlsx", "csv": "csv", "docx": "docx", "pdf": "pdf", "png": "png",
       "jpg": "jpg", "txt": "txt"}


def write(fmt: str, path: Path, sheets, rng: random.Random, options: dict) -> None:
    if fmt == "xlsx_tabs":
        render.write_xlsx(path, sheets, one_tab=False)
    elif fmt == "xlsx_one":
        render.write_xlsx(path, sheets, one_tab=True)
    elif fmt == "csv":
        render.write_csv(path, sheets)
    elif fmt == "docx":
        render.write_docx(path, sheets)
    elif fmt == "pdf":
        render.write_pdf(path, sheets)
    elif fmt in ("png", "jpg"):
        render.write_image(path, sheets, rng, photo=fmt == "jpg")
    elif fmt == "txt":
        if "text" in options:
            path.write_text(options["text"], encoding="utf-8")
        else:
            lines = []
            for sh in sheets:
                lines += sh.notes_above
                lines += ["\t".join(c for c in r if c) for r in sh.rows]
                lines.append("")
            path.write_text("\n".join(lines), encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schools", type=int, default=8)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--out", type=Path, default=ROOT / "school-imports" / "generated")
    args = ap.parse_args(argv)

    out: Path = args.out
    if out.exists():
        shutil.rmtree(out)
    (out / "schools").mkdir(parents=True)
    (out / "cases").mkdir()
    master = random.Random(args.seed)
    sizes = ["small", "medium", "large"]
    index = []

    for i in range(1, args.schools + 1):
        rng = random.Random(master.randint(0, 1_000_000))
        size = sizes[(i - 1) % len(sizes)]
        sch = school_mod.build(rng, size)
        sid = f"school_{i:02d}"
        (out / "schools" / f"{sid}.json").write_text(json.dumps(sch.to_truth(), indent=1), encoding="utf-8")

        jobs = []
        for name in TIMETABLE_LAYOUTS:
            for fmt in rng.sample(FORMATS[("timetable", name)], k=min(2, len(FORMATS[("timetable", name)]))):
                jobs.append(("timetable", name, fmt, None))
        # Pictures of a few sections: a scan and a phone photo.
        few = rng.sample(sch.sections, k=min(2, len(sch.sections)))
        jobs.append(("timetable", "class_grids", "png", few[:1]))
        jobs.append(("timetable", "class_grids", "jpg", few[-1:]))
        for kind, layouts in (("subjects", SUBJECT_LAYOUTS), ("teachers", TEACHER_LAYOUTS), ("rules", RULE_LAYOUTS)):
            for name in layouts:
                jobs.append((kind, name, rng.choice(FORMATS[(kind, name)]), None))

        for n, (kind, name, fmt, sections) in enumerate(jobs, start=1):
            layout = {"timetable": TIMETABLE_LAYOUTS, "subjects": SUBJECT_LAYOUTS, "teachers": TEACHER_LAYOUTS,
                      "rules": RULE_LAYOUTS}[kind][name]
            case_rng = random.Random(rng.randint(0, 1_000_000))
            if kind == "timetable" and name != "teacher_grids":
                sheets, written, options = layout(case_rng, sch, sections)
            else:
                sheets, written, options = layout(case_rng, sch)
            cid = f"{sid}_{n:02d}_{kind}_{name}_{fmt}"
            folder = out / "cases" / cid
            folder.mkdir()
            path = folder / f"input.{EXT[fmt]}"
            write(fmt, path, sheets, case_rng, options)
            shows = {"sections": sections or sch.sections}
            expected = {
                "id": cid, "kind": kind, "layout": name, "format": fmt, "school": f"schools/{sid}.json",
                "input": path.name, "shows": shows, "written": written.to_dict(),
                "options": {k: v for k, v in options.items() if k not in ("text",)},
            }
            (folder / "expected.json").write_text(json.dumps(expected, indent=1, default=str), encoding="utf-8")
            index.append({"id": cid, "kind": kind, "layout": name, "format": fmt, "school": sid, "size": size})
        print(f"{sid} ({size}): {len(sch.sections)} sections, {len(sch.teachers)} teachers, "
              f"{len(sch.blocks)} blocks, {len(jobs)} cases", flush=True)

    (out / "index.json").write_text(json.dumps({"seed": args.seed, "cases": index}, indent=1), encoding="utf-8")
    print(f"{len(index)} cases in {out}")


if __name__ == "__main__":
    main()
