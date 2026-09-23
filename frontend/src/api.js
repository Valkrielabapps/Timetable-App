/**
 * Thin wrapper around fetch() for the backend API.
 *
 * All calls go through the `/api` prefix, which vite.config.js proxies to
 * the FastAPI backend during local dev. Every function returns parsed JSON
 * and throws an Error with a readable message on non-2xx responses, so
 * components can just try/catch or let it bubble to a state.error field.
 *
 * Auth: the JWT from login/signup is kept in localStorage (this is a real
 * standalone app, not a sandboxed artifact, so persisting it across page
 * reloads is expected) and attached to every request automatically.
 */

const TOKEN_KEY = "timetable_auth_token";

export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

/**
 * Turn a failed response into an Error worth showing a user.
 *
 * Shared by every call below, which previously each had their own copy of
 * this block. Beyond the duplication, that meant a 429 surfaced as the raw
 * `429 "Too many requests..."` - status code and JSON quotes included - in
 * whatever toast the caller rendered.
 *
 * 429 is singled out because it is the one failure the user can actually do
 * something about: wait. Retry-After (set by backend/app/core/rate_limit.py)
 * says how long, so say so rather than making them guess.
 */
async function toError(res) {
  let detail = res.statusText;
  try {
    const body = await res.json();
    if (body.detail) {
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    }
  } catch {
    // response wasn't JSON; fall back to statusText
  }

  if (res.status === 429) {
    const seconds = parseInt(res.headers.get("Retry-After") || "", 10);
    const wait = Number.isFinite(seconds)
      ? seconds < 60
        ? ` Try again in ${seconds} seconds.`
        : ` Try again in ${Math.ceil(seconds / 60)} minutes.`
      : "";
    const error = new Error(`${detail}${wait}`);
    error.status = 429;
    error.retryAfter = Number.isFinite(seconds) ? seconds : null;
    return error;
  }

  const error = new Error(`${res.status} ${detail}`);
  error.status = res.status;
  return error;
}

async function request(path, options = {}) {
  const token = getToken();
  const headers = { "Content-Type": "application/json", ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, { ...options, headers });

  if (!res.ok) throw await toError(res);
  if (res.status === 204) return null;
  return res.json();
}

// Separate from request() because a plain <a href> download can't attach
// an Authorization header — and every /api endpoint now requires one,
// including exports (see app/core/access.py's require_school_access
// rollout across every router). Fetches the file with auth, then
// triggers a save exactly like a normal link would have, via a temporary
// blob URL and a synthetic click.
async function downloadFile(path, filename) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`/api${path}`, { headers });
  if (!res.ok) throw await toError(res);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Separate from request() because bulk-import posts multipart/form-data
// (a file, not JSON) — must NOT set a Content-Type header (the browser
// sets its own with the multipart boundary) or the upload gets mangled.
async function uploadFile(path, schoolId, file) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const body = new FormData();
  body.append("school_id", schoolId);
  body.append("file", file);

  const res = await fetch(`/api${path}`, { method: "POST", headers, body });
  if (!res.ok) throw await toError(res);
  return res.json();
}

// Setup extraction's upload endpoint takes only a file — no school_id
// form field, since the school is already in the URL path — so it can't
// reuse uploadFile() above, which always appends school_id to the body.
async function uploadFileOnly(path, file) {
  const token = getToken();
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  const body = new FormData();
  body.append("file", file);

  const res = await fetch(`/api${path}`, { method: "POST", headers, body });
  if (!res.ok) throw await toError(res);
  return res.json();
}

const get = (path) => request(path);
const post = (path, body) => request(path, { method: "POST", body: JSON.stringify(body) });
const put = (path, body) => request(path, { method: "PUT", body: JSON.stringify(body) });
const patch = (path, body) => request(path, { method: "PATCH", body: JSON.stringify(body) });
const del = (path) => request(path, { method: "DELETE" });

export const api = {
  // Auth
  signup: (data) => post("/auth/signup", data),
  login: (data) => post("/auth/login", data),
  // `credential` is the ID token Google's Sign-In button hands back via
  // its callback — see components/AuthPage.jsx and
  // backend/app/routers/auth.py's /auth/google endpoint, which verifies
  // it server-side rather than trusting it as-is.
  loginWithGoogle: (credential) => post("/auth/google", { credential }),
  me: () => get("/auth/me"),
  forgotPassword: (email) => post("/auth/forgot-password", { email }),
  resetPassword: (token, newPassword) => post("/auth/reset-password", { token, new_password: newPassword }),

  // Schools
  listSchools: () => get("/schools"),
  createSchool: (data) => post("/schools", data),
  updateSchoolGradeOrder: (schoolId, gradeOrder) =>
    put(`/schools/${schoolId}/grade-order`, { grade_order: gradeOrder }),
  updateSchoolInstitutionType: (schoolId, institutionType) =>
    put(`/schools/${schoolId}/institution-type`, { institution_type: institutionType }),

  // Subjects
  listSubjects: (schoolId) => get(`/subjects?school_id=${schoolId}`),
  createSubject: (data) => post("/subjects", data),
  updateSubject: (id, data) => put(`/subjects/${id}`, data),
  deleteSubject: (id) => del(`/subjects/${id}`),

  // Rooms
  listRooms: (schoolId) => get(`/rooms?school_id=${schoolId}`),
  createRoom: (data) => post("/rooms", data),
  deleteRoom: (id) => del(`/rooms/${id}`),

  // Periods
  listPeriods: (schoolId) => get(`/periods?school_id=${schoolId}`),
  createPeriod: (data) => post("/periods", data),
  deletePeriod: (id) => del(`/periods/${id}`),

  // Teachers
  listTeachers: (schoolId) => get(`/teachers?school_id=${schoolId}`),
  createTeacher: (data) => post("/teachers", data),
  updateTeacher: (id, data) => put(`/teachers/${id}`, data),
  deleteTeacher: (id) => del(`/teachers/${id}`),

  // Class groups (sections, grouped by `grade` for the sidebar tree)
  listClassGroups: (schoolId) => get(`/class-groups?school_id=${schoolId}`),
  createClassGroup: (data) => post("/class-groups", data),
  updateClassGroup: (id, data) => put(`/class-groups/${id}`, data),
  deleteClassGroup: (id) => del(`/class-groups/${id}`),

  // Subject requirements (nested under class groups)
  listRequirements: (classGroupId) => get(`/class-groups/${classGroupId}/requirements`),
  listAllRequirements: (schoolId) => get(`/class-groups/requirements?school_id=${schoolId}`),
  createRequirement: (classGroupId, data) =>
    post(`/class-groups/${classGroupId}/requirements`, data),
  updateRequirement: (id, data) => put(`/class-groups/requirements/${id}`, data),
  deleteRequirement: (id) => del(`/class-groups/requirements/${id}`),

  // Constraints
  listConstraints: (schoolId) => get(`/constraints?school_id=${schoolId}`),
  parseConstraint: (schoolId, text) => post("/constraints/parse", { school_id: schoolId, text }),
  // Batch counterpart to parseConstraint — `text` can contain several
  // rules at once (one per line works best); returns one parse-response
  // per distinct rule found. See backend/app/routers/constraints.py's
  // POST /batch docstring for how it splits multi-rule text with and
  // without an LLM available.
  parseConstraintsBatch: (schoolId, text) => post("/constraints/batch", { school_id: schoolId, text }),
  // Re-parses new text into an EXISTING constraint (same id) instead of
  // creating a new one — used by the Edit affordance on a constraint card.
  reparseConstraint: (id, text) => put(`/constraints/${id}/reparse`, { text }),
  // Direct field edit — used for the scope picker (parameters.class_group_ids)
  // without re-typing/re-parsing the whole rule.
  updateConstraint: (id, data) => put(`/constraints/${id}`, data),
  deleteConstraint: (id) => del(`/constraints/${id}`),

  // Timetables — generation runs as a background job (see
  // backend/app/routers/timetables.py). generateTimetable() kicks the job
  // off and returns immediately with status="generating"; getTimetable()
  // polls for the job's current state (TimetableTab.jsx polls this on an
  // interval until status is no longer "generating").
  generateTimetable: (schoolId) => post(`/timetables/generate?school_id=${schoolId}`),
  getTimetable: (id) => get(`/timetables/${id}`),
  listTimetables: (schoolId) => get(`/timetables?school_id=${schoolId}`),
  // Manual editing of one already-generated slot — lock/unlock it (kept in
  // place on the next regenerate) and/or drag it to a free period.
  // See PATCH /api/timetables/entries/{id} in backend/app/routers/timetables.py.
  updateTimetableEntry: (entryId, data) => patch(`/timetables/entries/${entryId}`, data),
  // Dragging a slot onto another *filled* slot swaps them (moving just one
  // would look like a double-booking until the other moves out of the
  // way too) — see POST .../entries/{id}/swap-with/{id} in the same router.
  swapTimetableEntries: (entryId, otherEntryId) =>
    post(`/timetables/entries/${entryId}/swap-with/${otherEntryId}`),
  // Conversational editing — plain-English text resolved server-side
  // (via Claude, grounded against this timetable's actual entries and
  // the school's actual periods) into a lock/move/swap, applied through
  // the same conflict-checked logic as the two calls above. No non-LLM
  // fallback for this one — see backend/app/services/edit_command_parser.py's
  // docstring for why; a 503 here means "not configured", not a bug.
  editTimetableByCommand: (timetableId, text) => post(`/timetables/${timetableId}/edit-command`, { text }),
  // Triggers a browser download of the exported file — see downloadFile
  // above for why this can't just be a plain <a href> anymore.
  downloadTimetableExport: (id, format) =>
    downloadFile(`/timetables/${id}/export?format=${format}`, `timetable_${id}.${format}`),

  // Bulk import — upload a CSV/.xlsx of subjects, rooms, teachers, or
  // class groups instead of adding them one at a time. See
  // backend/app/services/bulk_import.py and the /bulk-import routes on
  // each resource's router. `resource` is one of "subjects", "rooms",
  // "teachers", "class-groups" (matches the router prefix).
  bulkImport: (resource, schoolId, file) => uploadFile(`/${resource}/bulk-import`, schoolId, file),
  bulkImportTemplateUrl: (resource) => `/api/${resource}/bulk-import/template`,

  // Setup-from-document extraction — upload an arbitrary spreadsheet
  // (not in bulk-import's expected column format) and let Claude propose
  // teachers/subjects/class groups from it. extractSetup() is read-only
  // (nothing created yet); commitSetupExtraction() actually creates the
  // admin-reviewed subset. See backend/app/services/setup_extractor.py
  // and app/routers/setup_extraction.py.
  extractSetup: (schoolId, file) => uploadFileOnly(`/schools/${schoolId}/setup-extraction`, file),
  commitSetupExtraction: (schoolId, payload) => post(`/schools/${schoolId}/setup-extraction/commit`, payload),

  // Members & invites — see backend/app/core/access.py for the role model
  // (admin/viewer, owner is always an implicit admin) and
  // backend/app/routers/schools.py + invites.py for these endpoints.
  listMembers: (schoolId) => get(`/schools/${schoolId}/members`),
  updateMemberRole: (schoolId, userId, role) => patch(`/schools/${schoolId}/members/${userId}`, { role }),
  removeMember: (schoolId, userId) => del(`/schools/${schoolId}/members/${userId}`),
  listInvites: (schoolId) => get(`/schools/${schoolId}/invites`),
  createInvite: (schoolId, email, role) => post(`/schools/${schoolId}/invites`, { email, role }),
  revokeInvite: (schoolId, inviteId) => del(`/schools/${schoolId}/invites/${inviteId}`),
  // Public — no auth required, since whoever clicked the invite link
  // likely isn't logged in yet.
  previewInvite: (token) => get(`/invites/${token}`),
  acceptInvite: (token, data) => post(`/invites/${token}/accept`, data),

  // Substitutions
  listSubstitutionLogs: (schoolId) => get(`/schools/${schoolId}/substitutions`),
  saveSubstitutionLog: (schoolId, data) => post(`/schools/${schoolId}/substitutions`, data),
};
