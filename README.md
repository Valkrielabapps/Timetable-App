# Timetablz

Clash-free school timetables, built from the files a school already has.
A school uploads last year's timetable, its staff list or its allotment sheet
in whatever layout it uses; Timetablz reads it, asks about anything it can't
tell, and a constraint solver (Google OR-Tools CP-SAT) builds a timetable for
every section at once, with no teacher or class double-booked.

Live at [timetablz.com](https://timetablz.com).

## Who it's for

Schools in India, starting with CBSE/ICSE schools of roughly 1,000–4,000
students. Users are timetable coordinators and administrators, not technical
people, so the product is "simple surface, powerful engine": imports that read the files they already have,
plain-English rules, and questions instead of guesses.

## How a school uses it

1. **Start from last year's timetable** (top of Setup). Each
   section's printed week is read into its class teacher, subjects, periods
   per subject (counted from the cells), the teacher who took each one, and
   the shape of the week. Add the staff list too and short names in the
   cells ("KRITHI", "V'G", "SUBHA") are matched to full names, using the
   subject to tell alike names apart.
2. **Import anything.** Teachers, subjects and each class's plan can come from
   Excel, CSV or Word, in any of these layouts:
   - ordinary columns (any headings, mapped by rules and confirmed by AI)
   - a grid of ticks, or teachers listed across the top
   - one small table per class (Subjects | Periods | Teacher)
   - an allotment grid: classes down, subjects across, periods in the cells
     (or the other way round), and side-by-side stream columns (NEET/JEE/CUET)
   - a list under each teacher's name ("VIII A-3 PHY", "I A,B,C - 3")
   - a staff list by department ("HIGH SCHOOL ENGLISH", then names)
   - last year's timetable
   Every import shows a preview first, flags doubtful rows, and asks about
   look-alike names and spellings before anything is saved.
3. **Rules.** Common ones are tick boxes (teacher daily/weekly caps, spread,
   core subjects in the morning). Anything else is written in plain English
   and turned into a structured rule (see "Rules" below). Setup also covers
   breaks, a school-wide class teacher or zero period, shorter days for some
   grades, and **fixed periods for some grades** (e.g. the class teacher period
   in period 8 for Grades 1–5, counted in that teacher's week).
4. **Generate.** The whole school is solved together. A setup check runs first
   and lists anything that would make generation fail, with a link to fix it.
   If the rules can't all be met, it explains which ones conflict, and can
   produce a compromise timetable that says what it relaxed.
5. **Adjust without rebuilding.** Drag lessons (the grid colours where a lesson
   can go and suggests chains of moves), lock or freeze what's right, replace
   one teacher with another everywhere, and update only what changed when the
   plan changes mid-year. Up to five versions are kept.
6. **Day to day.** Mark absences, get substitute suggestions, and email
   teachers their cover with calendar invites (updates and cancellations
   included).
7. **Export** by section or teacher, to Excel or PDF.

## Plans and billing

Priced per year by number of sections, with a 14-day free trial that has
everything unlocked:

| Plan | Sections | Software | Done for you (first year incl. setup) |
|---|---|---|---|
| Starter | up to 30 | ₹9,999 | ₹17,999 |
| Standard | 31–50 | ₹14,999 | ₹26,999 |
| Plus | 51–80 | ₹19,999 | ₹34,999 |
| Large / Group | 80+ | ₹19,999 + ₹250/section above 80 | quoted |

Visitors outside India see US dollar prices ($149 / $229 / $299; done for you
$279 / $399 / $529) and request an invoice by email. Payments in India go
through Cashfree. Catalogue: `backend/app/services/plans.py` and
`frontend/src/lib/plans.js` (keep the two in step).

Users accept the Terms on first sign-in and again whenever they change
(`CURRENT_TERMS_VERSION`). Legal texts are in `docs/legal/` and
`frontend/src/legal/`.

## Tech stack

| Layer | Technology |
|---|---|
| Solver | Google OR-Tools CP-SAT |
| Backend | Python, FastAPI, SQLAlchemy, Alembic |
| Database | PostgreSQL (SQLite in tests) |
| Frontend | React 19, Vite, Tailwind CSS 4, React Query |
| AI | Anthropic Claude: reading rules, mapping import columns, explaining conflicts, conversational edits. Every AI step has a rule-based fallback |
| Email | Resend (transactional, cover emails); Zoho / Gmail for outreach |
| Payments | Cashfree |
| Hosting | Railway (API; pre-deploy runs `alembic upgrade head`), Vercel (frontend, proxies `/api`) |

## Project structure

```
timetable-app/
├── backend/
│   ├── app/
│   │   ├── core/        config, database, auth, access control
│   │   ├── models/      SQLAlchemy models
│   │   ├── schemas/     Pydantic request/response schemas
│   │   ├── routers/     API endpoints
│   │   └── services/    solver, imports, rules, billing, email, ...
│   ├── alembic/         database migrations (one head - see tests/test_migration_chain.py)
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/  every screen and panel
│       ├── lib/         plans, SEO, helpers
│       ├── legal/       Terms, Privacy, Refunds (rendered on the site)
│       └── api.js       every API call the UI makes
└── docs/                architecture, getting started, deployment, legal
```

Key backend services:

| Service | What it does |
|---|---|
| `solver.py` | Builds and solves the CP-SAT model; update mode keeps valid lessons |
| `smart_import.py` | Reads any sheet/document layout into teachers, subjects and class tables |
| `class_plan.py` | Each section's weekly plan from a file: preview, questions, commit |
| `setup_check.py` | Finds what would make generation fail, before generating |
| `constraint_ir*.py`, `llm_ir_parser.py` | Plain-English rules → structured rules → solver constraints |
| `infeasibility_explainer.py` | Why a timetable can't be made, in plain words |
| `adjust.py` | Plan changes since the last timetable; replace a teacher |
| `timetable_structure.py` | Days, periods, breaks, shorter days, fixed periods |
| `substitution_notify.py` | Cover emails with calendar invites |
| `plans.py`, `billing.py`, `cashfree_service.py` | Plans, trial, checkout, invoices |
| `erase.py` | Deleting a school or account (payment records kept, unlinked) |

## Rules

Rules are stored in a small general form rather than one type per rule:
**count**, **run**, **adjacency**, **bucket** and **conditional**, each with a
selector (which lessons: subject, teacher, class, day, period) and a scope
(what it's counted over). That lets five forms cover the large majority of
the rules schools actually write (see `docs/research/` and
`docs/Timetablz_Constraint_Catalogue.xlsx`). Each rule is shown back in
English before it's saved, and a rule that can't be enforced says so.

## Admin

`/admin` (platform admins only): schools, accounts, plans and payments,
mark-paid and custom offers, view or download a school's data, delete schools
and accounts, rule-reading failures and problem reports.

## Running it

See [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) to run it locally and
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for Railway and Vercel. In short:

```bash
# backend
cd backend
pip install -r requirements.txt
cp .env.example .env        # DATABASE_URL, JWT_SECRET; the rest are optional
alembic upgrade head
uvicorn app.main:app --reload

# frontend
cd frontend
npm ci
npm run dev
```

Optional settings in `.env`: `ANTHROPIC_API_KEY` (AI features; without it the
rule-based fallbacks are used), `RESEND_API_KEY` and `EMAIL_FROM_ADDRESS`
(email), `CASHFREE_*` (payments), `SENTRY_DSN`. Never commit keys; set them
in Railway.

Interactive API docs are at `/docs` on the running backend.

## Tests

```bash
cd backend && pytest        # solver, imports, rules, billing, migrations, ...
cd frontend && npx vitest run
```
