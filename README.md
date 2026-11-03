# Timetable Generator

A web application that generates conflict-free school timetables automatically.
School administrators upload their data (teachers, classes, subjects, rooms,
constraints) and the app produces an optimized, conflict-free schedule using a
constraint solver - instead of building timetables by hand in a spreadsheet.

## Who this is for

Non-technical school administrators (initial target market: schools in India).
The product philosophy is "simple surface, powerful engine": the UI stays
minimal, and advanced scheduling rules are opt-in rather than required.

## How it works (MVP flow)

1. **Import** - admin uploads teacher/class/subject/room data via CSV or Excel.
2. **Configure constraints** - admin describes scheduling rules in plain terms
   (e.g. "Teacher X is unavailable on Fridays", "Math must not be the last
   period for Grade 5").
3. **Generate** - one click triggers the solver, which produces a complete
   timetable satisfying all hard constraints and as many soft preferences as
   possible.
4. **Resolve conflicts** - if no fully valid schedule exists, the app shows
   *why* (which constraints conflict) so the admin can adjust.
5. **Lock & regenerate** - admin can lock parts of the schedule they like and
   regenerate the rest.
6. **Export** - download as PDF/Excel or push to existing school
   calendar/ERP systems.

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Solver | Google OR-Tools (CP-SAT) | Purpose-built constraint solver; handles hard + soft scheduling constraints well |
| Backend | Python + FastAPI | Best-supported language for OR-Tools; FastAPI gives free auto-generated API docs |
| Frontend | React + Tailwind CSS | Component-based UI, fast to style, widely supported |
| Database | PostgreSQL | Relational data (schools, teachers, classes, constraints) with strong consistency guarantees |
| Import/Export | SheetJS (xlsx) | Reads/writes Excel files in-browser and on the server |
| Hosting | Railway or Render | Simple deploys for a Postgres + API + static frontend stack |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how the pieces fit
together, and [`docs/GETTING_STARTED.md`](docs/GETTING_STARTED.md) to run the
project locally.

## Project structure

```
timetable-app/
├── backend/          FastAPI application + OR-Tools solver
│   ├── app/
│   │   ├── core/         config, database connection
│   │   ├── models/       SQLAlchemy database models
│   │   ├── schemas/       Pydantic request/response schemas
│   │   ├── routers/      API endpoints
│   │   └── services/     business logic, incl. the solver service
│   └── tests/
├── frontend/          React + Tailwind admin UI
└── docs/              Architecture and setup documentation
```

## API endpoints (current)

Full interactive docs (try-it-out included) are at `/docs` once the backend
is running. Currently available:

- `/api/auth/signup`, `/api/auth/login`, `/api/auth/me` - email/password
  auth, returns a JWT used as `Authorization: Bearer <token>` on every
  other request
- `/api/schools` - create/list/get, scoped to the logged-in user
  (`owner_id`)
- `/api/subjects`, `/api/rooms`, `/api/periods`, `/api/teachers`,
  `/api/class-groups`, `/api/constraints` - full CRUD (create, list, get,
  update, delete), each filterable by `?school_id=`. Class groups also
  carry a `grade` field (e.g. "Grade 8") for the Grade > Section hierarchy.
- `/api/class-groups/{id}/requirements` - how many periods/week a class
  group needs of a subject (nested under class groups)
- `/api/constraints/parse` (POST) - turns plain-English constraint text
  into a structured Constraint row; see "NLP constraints" below
- `/api/timetables/generate?school_id=` (POST) - runs the real solver
  against a school's teachers/class groups/subject requirements/periods
  and saves the result as a draft timetable
- `/api/timetables/{id}` and `/api/timetables?school_id=` - fetch a
  generated timetable with human-readable names filled in
- `/api/solver/test` - diagnostic endpoint that runs a small built-in
  OR-Tools example, useful to confirm the solver install works

Also built (this section previously said "not yet"): CSV/Excel bulk
import for subjects, rooms, teachers, and class groups
(`/api/{resource}/bulk-import`, `app/services/bulk_import.py`), and
best-effort room assignment as a second solver pass
(`_assign_rooms` in `app/services/solver.py`). Not yet built: Google
sign-in (needs an OAuth client only you can create).

## NLP constraints

`POST /api/constraints/parse` tries an LLM call first
(`app/services/llm_constraint_parser.py`, calls Claude with the school's
real teacher/subject/class-group names so it only ever returns names that
actually exist) and falls back to a pattern-matching parser
(`app/services/constraint_parser.py`) if no `ANTHROPIC_API_KEY` is set or
the call fails for any reason - same input/output shape either way, so
the rest of the router doesn't care which one produced a given result.

Most constraint types are read directly by the solver
(`app/services/solver.py`), not just recorded: workload limits
(`Teacher.max_periods_per_week`), availability
(`Teacher.unavailable_period_ids`, e.g. "not available on Fridays"),
subject-vs-first/last-period placement, subject-vs-day placement, max
consecutive periods (per subject or per teacher), minimum gap between two
subjects, and subject-sequencing ("Math can't immediately follow PE") are
all hard constraints in the CP-SAT model - see `backend/tests/test_solver.py`
for a couple of regression tests proving the availability and placement
cases actually hold. The one exception is the catch-all
`scheduling_rule` type: free-text that doesn't match any of the specific
patterns above is still saved and shown in the Constraints tab, but isn't
mechanically enforceable, so the UI marks that one honestly as "Not yet
enforced by the solver" (`ConstraintOut.enforced`, computed in
`app/routers/constraints.py`).

## Frontend screens (current)

The admin UI matches the uploaded design: auth screen, then a Grade >
Section sidebar with four tabs per section.

- **Auth** - real email/password login and signup. "Continue with Google"
  is shown but disabled (needs Google OAuth credentials from you first).
- **Sidebar** - school switcher plus a Grade > Section tree built from
  class groups; "+ Add" creates a new grade/section on the fly.
- **Overview** - 3-step status summary (data entry → constraints →
  generate) with quick links into each tab.
- **Data Entry** - one table: subjects, periods/week for the selected
  section, and which teacher(s) are qualified for each subject (chips +
  dropdown). Includes a one-click "Quick setup: Mon–Fri, 8 periods/day" for
  schools that don't have periods configured yet.
- **Constraints** - the NLP input described above, rendered as removable
  cards.
- **Timetable** - "Generate Timetable" solves for the *whole school* at
  once (every section + every shared teacher together, so there are no
  cross-section conflicts), then displays the result as a day × period
  grid with a By Section / By Teacher toggle.

See `frontend/src/api.js` for the full list of API calls the UI makes, and
`frontend/src/components/` for each screen. A few older components
(`SubjectsPanel`, `TeachersPanel`, `ClassGroupsPanel`, `RoomsPanel`,
`TimetablePanel`) are left in place but unused/superseded - each has a
comment saying so and is safe to delete.

## Status

Full auth (signup/login/JWT) is in place, schools are scoped to their
owner (plus invite-based admin/viewer memberships), and the frontend
matches the uploaded design end-to-end: sidebar grade/section tree,
combined subjects+teachers data entry, NLP-style constraint input, and a
generate flow with By Section / By Teacher views. The real solver reads a
school's actual data from the database, builds a CP-SAT model (subject
requirements met exactly, no teacher/class double-booking, teacher
max-hours and availability respected, plus the placement/consecutive/
sequencing constraint types described above), assigns rooms as a
best-effort second pass, and either returns a conflict-free schedule or a
clear reason it couldn't. CSV/Excel bulk import, Excel/PDF export, and a
manual same-day substitution log are also built. Scope is intentionally
generic (not locked to one curriculum or school type yet) - see
`docs/ARCHITECTURE.md` for the data model reasoning and open decisions.

Next up, roughly in priority order: Google sign-in (once you've created
OAuth credentials), per-resource ownership checks now that multiple
admins per school are possible (see "Open decisions" in
`docs/ARCHITECTURE.md`), and diagnosing infeasibility caused by an
*interaction* between several constraints rather than one alone.
