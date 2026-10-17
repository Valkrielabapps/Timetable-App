# Test school: Greenfield International School, Kochi

A deliberately hard school for testing generation. It has been run through the real solver with everything below switched on: **it solves** (656 lessons placed, a few seconds), with every section keeping one teacher per subject all week.

What makes it hard:

- 14 sections over 7 grades.
- 33 teachers, most limited to certain grades.
- A half-day Saturday.
- 3 elective blocks.
- 3 split labs.
- Rooms that certain subjects need.
- Part-time teachers.
- Staffing kept tight on purpose: English needs 80 periods and its teachers can give 86, but because each section keeps one English teacher all week, the sections have to divide up exactly.

> **Plan limit:** Free allows only 5 sections. Before you start, open timetablz.com/admin, find the test school, and click **Mark paid** (Pro) or **Extend free**.

---

## Step 1: Setup (timetable structure)

| Setting | Value |
|---|---|
| School days | Monday to Saturday |
| Periods per day | 8 |
| Shorter day | Saturday: 4 periods |
| Break 1 | after period 3, "Short break" |
| Break 2 | after period 5, "Lunch" |
| Class teacher period | optional, start of the day (see the optional extras at the end) |

That's 44 teaching periods a week.

Then, on Setup, use **Bulk import** in this order. Order matters: teachers refer to subjects and grades.

1. `1_subjects.csv`: 25 subjects
2. `2_rooms.csv`: 24 rooms
3. `3_sections.csv`: 14 sections
4. `4_teachers.csv`: 33 teachers

## Step 2: Subjects, lab batches

Open each of these subjects' advanced settings and set **lab batches = 2**. The class splits in half, and each half needs its own teacher and lab at the same time.

| Subject | Lab batches |
|---|---|
| Science Lab | 2 |
| Physics Lab | 2 |
| Chemistry Lab | 2 |

The room types (lab, computer, sports, art, music) come in with the import.

## Step 3: Weekly plan for each section

Leave the teacher as **any qualified teacher** unless you want to test fixed teachers. Enter one section of each kind, then use **Copy to other sections**.

### Grades 6, 7, 8 (sections A and B), 42 periods

| Subject | Periods/week |
|---|---|
| English | 6 |
| Hindi | 5 |
| Mathematics | 7 |
| Science | 6 |
| Social Studies | 5 |
| Computer | 2 |
| Physical Education | 3 |
| Art | 2 |
| Music | 1 |
| Library | 1 |
| Value Education | 1 |
| **Elective block "Third language"**: Malayalam / French / Sanskrit | 3 |

### Grades 9, 10 (sections A and B), 43 periods

| Subject | Periods/week |
|---|---|
| English | 6 |
| Hindi | 4 |
| Mathematics | 7 |
| Physics | 4 |
| Chemistry | 4 |
| Biology | 4 |
| Social Studies | 6 |
| Computer Science | 3 |
| Science Lab | 2 |
| Physical Education | 2 |
| Library | 1 |

### Grade 11 Science and Grade 12 Science, 40 periods

| Subject | Periods/week |
|---|---|
| English | 5 |
| Physics | 7 |
| Chemistry | 7 |
| Mathematics | 7 |
| Physics Lab | 2 |
| Chemistry Lab | 2 |
| Physical Education | 2 |
| Library | 1 |
| **Elective block "Science elective"**: Biology / Computer Science | 7 |

### Grade 11 Commerce and Grade 12 Commerce, 36 periods

| Subject | Periods/week |
|---|---|
| English | 5 |
| Accountancy | 7 |
| Business Studies | 7 |
| Economics | 7 |
| Physical Education | 2 |
| Library | 1 |
| **Elective block "Commerce elective"**: Mathematics / Informatics Practices | 7 |

## Step 4: Constraints

Type these in, one at a time or all together in batch entry. They also test how well the app reads plain English.

1. Anu Thomas is not available on Thursday, Friday and Saturday.
2. Vinod Kumar only comes in on Thursday and Friday.
3. Claire D'Souza is not available on Saturday.
4. No Physical Education in the first period.
5. No section should have more than 2 Mathematics periods in a day.
6. No labs on Saturday (Physics Lab, Chemistry Lab and Science Lab).
7. No teacher should teach more than 6 periods in a day.
8. English at most once a day for every section.
9. Grade 12 Science should never have Physics in the last period.

After entering them, check that each one shows as **enforced** on the Constraints tab.

## Step 5: Generate

Expect a few seconds to under a minute. Things to check:

- [ ] No teacher appears twice in the same period (use By Teacher view).
- [ ] Each section has the same teacher for a subject on every day (e.g. Grade 9 A English is always the same person).
- [ ] Each elective block shows as one cell. Grade 6 to 8 "Third language" needs Lakshmi, Claire and Ganesh free at once.
- [ ] Lab periods show two batches, each with its own teacher.
- [ ] No PE in period 1, no labs on Saturday, at most 2 Maths a day.
- [ ] Anu Thomas only on Mon to Wed, Vinod Kumar only on Thu/Fri.
- [ ] Saturday only has 4 periods.
- [ ] Drag a slot, lock a slot, regenerate: locked slots stay put.
- [ ] Export PDF and Excel: pages go Grade 6 A, 6 B, 7 A … then teachers A to Z.
- [ ] Student timetables export for Grade 11 Science (2 combinations) and Grade 6 A (3 combinations).
- [ ] Substitutions: mark Priya Nair absent on a Monday and check the suggestions.

---

## Break it on purpose (tests the error popup)

Do these one at a time, generate, read the popup, then undo.

| # | Change | What it should say |
|---|---|---|
| 1 | Grade 9 A: Mathematics from 7 to 9 periods/week | 45 periods needed, only 44 in the week |
| 2 | Delete Claire D'Souza | No teacher can teach French for the Third language block |
| 3 | Add the rule: "Every section has English in period 1 on Monday" | 14 sections need English at once with only 3 English teachers |
| 4 | Change Priya Nair's max periods/week from 32 to 30 | Not enough English teaching time for Grades 9 to 12 |
| 5 | Add the rule: "Vinod Kumar only teaches in periods 1 and 2" (with rule 2 above) | 6 Music lessons into 4 possible slots |
| 6 | Grade 12 Science: Physics Lab batches from 2 to 3 | A third Physics Lab teacher is needed at the same time |

Test 6 may solve, because Sreeja Lab can cover it. If it does, that's correct; it shows the solver using every qualified teacher.

## Optional extras for later

- **Class teacher period:** turn it on at the start of the day, then set a class teacher for each section, e.g. Anita Menon (6 A), Joseph Thomas (6 B), Ramesh Kumar (7 A), and so on.
- **Fixed teachers:** set Grade 12 Science Physics to Vivek Menon and Grade 11 Science Physics to Anil Joseph. This tests fixed assignments, and generation should get faster.
- **Plain-English edits:** after generating, try "move Grade 10 A's Hindi on Tuesday to period 6".
