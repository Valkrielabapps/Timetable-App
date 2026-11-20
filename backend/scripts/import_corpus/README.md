# Import test corpus

Made-up schools whose every fact is known, written out in the messy layouts and file formats real schools send, so the four importers (last year's timetable, subjects, teachers, rules) can be scored instead of judged by eye.

```
python scripts/import_corpus/generate.py            # 8 schools, 160 cases -> school-imports/generated/
python scripts/import_corpus/verify.py              # checks the truths are real timetables and every file opens
python scripts/import_corpus/score.py --save ../school-imports/scores/today.json
python scripts/import_corpus/score.py --compare ../school-imports/scores/2026-11-20-baseline.json
```

`score.py` runs each case through the code the website uses and scores it 0-100 against the truth. It reports an overall score per area, a breakdown by layout and format, why files were refused, and, with `--compare`, which files moved since a saved run. `--detail` prints every case's findings, for example "6A Mathematics: 6 not 5" or "extra lines: S, H, O, R, T" for a break column spelt one letter per row. Rule messages need the AI key, and their scoring comes with Phase 5.

For timetables there is a second number, "+ more": what `app/services/timetable_reader.py` reads beyond the plan - every lesson at its day and period (for keeping last year's timetable as it is), the bell times, the breaks, the blocks and the fixed periods - scored over the parts each file shows. A grid per teacher that never names the subject in its cells can only be as right as the subject in its title; a file that writes only first names can't tell two teachers called Mythili apart, and the importer asks.

PDFs and photos are written out by the AI before they're read, so without `ANTHROPIC_API_KEY` they are refused, and scored 0. Run the scorer with the key set to score them.

## Rule messages

```
python scripts/import_corpus/rules_corpus.py     # 96 messages with known meanings -> school-imports/generated/rules/
python scripts/import_corpus/score_rules.py      # splitting and clock times, no AI
python scripts/import_corpus/score_rules.py --ai # also reads every rule with the AI and checks what it would do (needs ANTHROPIC_API_KEY)
```

Each message is a coordinator's note the way it arrives - a WhatsApp forward, a greeting, numbered or one paragraph, two rules on a line, clock times - with what it means as facts: when a teacher can't be given a lesson, which periods a subject can't be in, a daily limit. `--ai` checks the rules the parser made by trying lessons against them (a lesson of that teacher in every period of the week, a day of N and N+1 lessons), so any wording or rule shape that would give the right timetable scores full marks.

`--seed` fixes the corpus: the same seed always gives the same files, so a score before a change can be compared with one after.

## Where the shapes come from

Every layout copies something a real school published. See `school-imports/public/samples.json`, which holds the source, the features and a transcription for each. Those files are git-ignored because they name real staff.

| Kind | Layouts | Modelled on |
|---|---|---|
| Timetable | `class_grids` (days down, periods across, breaks as columns or spelt one letter per row, bell-time row, class teacher line, BBPS legend codes) | Aditya Birla, BBPS Noida, Baptist Convent |
| | `keren` ("Teacher's Name : MS.X  VII A", cells `ENG-SARA`, `2LN-BEAUL`) | Keren school |
| | `transposed` (times down, days across, breaks as rows) | KVS model timetable |
| | `master` (every section on one sheet, day merged over its periods) | common coordinator sheet |
| | `teacher_grids` (a grid per teacher titled by name or post `TGT: MATHS 2`, cells `VII B/SCI`, `XI A+B+C`) | KV Tezpur |
| Subjects | `list`, `allotment` (periods per grade), `by_grade` ("Class VI: Eng, Maths, ...") | KVS allotment, school lists |
| Teachers | `kv_table` (`TGT (Maths)`, non-teaching rows), `free_text` ("Eng & SST", "6 to 8"), `by_department`, `allotment` ("VIII B - SCI - 6") | KV Chheoki, NPS, Podar |
| Rules | `message` (a WhatsApp note) with its meaning as facts | Keren's messages |

Formats: `.xlsx` (one tab per section, or all stacked on one tab, with merged cells), `.csv`, `.docx`, `.pdf`, `.png` (a clean scan) and `.jpg` (a tilted, soft phone photo).

## What a case holds

```
cases/school_03_09_timetable_teacher_grids_pdf/
  input.pdf
  expected.json    kind, layout, format, options, which school truth, which sections it shows,
                   and "written": how each truth value appears in this file
                   ({"subjects": {"Social Science": ["S. Sc."]}, "teachers": {"Beula Rao": ["BEAUL"]}})
schools/school_03.json   the full truth: week, bell times, sections, teachers, plan, blocks, fixed periods, every lesson
```

A teacher grid titled only by post ("TGT: MATHS 2") records the post as the teacher's written form. That file never names the teacher, and a scorer must not expect a name from it.

## Adding real schools

Put real files in `school-imports/real/` (git-ignored), with an `expected.json` written by hand in the same shape. The scorer will treat them like generated cases. Before a real file joins the permanent set, swap the names for fake ones consistently.
