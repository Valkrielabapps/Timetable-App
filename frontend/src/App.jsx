import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { api, getToken, setToken } from './api'
import LandingPage from './components/LandingPage'
import AuthPage from './components/AuthPage'
import AcceptInvitePage from './components/AcceptInvitePage'
import ResetPasswordPage from './components/ResetPasswordPage'
import PrivacyPolicyPage from './components/PrivacyPolicyPage'
import TermsOfServicePage from './components/TermsOfServicePage'
import PricingPage from './components/PricingPage'
import SupportPage from './components/SupportPage'
import WhyTimetablzPage from './components/WhyTimetablzPage'
import AboutPage from './components/AboutPage'
import CustomersPage from './components/CustomersPage'
import Sidebar from './components/Sidebar'
import FirstRunWelcome from './components/FirstRunWelcome'
import OverviewTab from './components/OverviewTab'
import DataEntryTab from './components/DataEntryTab'
import ConstraintsTab from './components/ConstraintsTab'
import TimetableTab from './components/TimetableTab'
import TeamTab from './components/TeamTab'
import SetupProgressBar from './components/SetupProgressBar'
import { useSetupProgress } from './hooks/useSetupProgress'

// Substitutions used to be its own tab here, but it's really a sibling
// view of the generated schedule (same data — entries, periods, teachers
// — different lens), not a distinct workflow, so it now lives as a
// Schedule/Substitutions toggle inside TimetableTab.jsx instead of adding
// to this top-level count.
const BASE_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'entry', label: 'Data Entry' },
  { id: 'constraints', label: 'Constraints' },
  { id: 'timetable', label: 'Timetable' },
]

/**
 * Top-level shell. Owns: the logged-in user, which school/section is
 * selected, and which tab is active. Everything else is fetched by the
 * individual tab components so this file doesn't become a god-component.
 */
function App() {
  const [user, setUser] = useState(null)
  const [checkingSession, setCheckingSession] = useState(true)

  const [schools, setSchools] = useState([])
  const [selectedSchoolId, setSelectedSchoolId] = useState(null)
  const [classGroups, setClassGroups] = useState([])
  const [selectedClassGroupId, setSelectedClassGroupId] = useState(null)
  const [teachers, setTeachers] = useState([])
  // Subjects/periods/rooms — lifted up here (alongside classGroups/
  // teachers, which already lived here) rather than kept local to
  // DataEntryTab, because DataEntryTab gets unmounted every time the
  // admin switches to another top-level tab (`{tab === 'entry' && (...)}`
  // in the render below) — any state kept inside it is destroyed on
  // every tab switch and has to be re-fetched from scratch on the way
  // back, which is exactly why switching to Constraints and back used to
  // cost a fresh multi-request reload of data that was on screen seconds
  // earlier. App.jsx never unmounts, so state kept here survives tab
  // switches for free.
  const [subjects, setSubjects] = useState([])
  const [periods, setPeriods] = useState([])
  // Constraints — same reasoning as subjects/periods/rooms above: lifted
  // here instead of fetched independently by ConstraintsTab (which
  // unmounts on every tab switch) and *again* by useSetupProgress (for
  // the header bar/OverviewTab), which together used to mean opening
  // Constraints cost two redundant round trips (constraints + a second,
  // already-answered fetch of classGroups) before anything on the page
  // could render.
  const [constraints, setConstraints] = useState([])
  // Team membership/invites — same reasoning as constraints above:
  // TeamTab used to fetch these itself on every mount, and since it fully
  // remounts on every tab switch (App.jsx's `key={tab}`), the "Owner"
  // badge and member list took a visible several seconds to appear on
  // every single visit to Team, even though nothing about who has access
  // to a school changes from one tab switch to the next.
  const [members, setMembers] = useState([])
  const [invites, setInvites] = useState([])
  // Every SubjectRequirement across every section in the school (periods/
  // week + preferred/assistant teacher per subject per section), fetched
  // once as a flat list — same "lift it so a tab switch can't throw it
  // away" reasoning as subjects/periods/rooms above, but school-wide
  // rather than per-section-and-lazy the way this used to be cached.
  // Needed in full, always, now that TeachersSection.jsx sums each
  // teacher's committed periods/week *across every section* for the live
  // workload total — a lazy per-visited-section cache would silently
  // undercount any section the admin hasn't happened to open yet, which
  // defeats the point of a workload warning.
  const [allRequirements, setAllRequirements] = useState([])
  // The timetable is no longer lifted here. It used to be, because
  // TimetableTab unmounts on every tab switch and state kept inside it was
  // lost each time; React Query's cache survives the unmount instead, so
  // the tab can own its own data again (see useTimetable in
  // hooks/useSchoolData.js, which also replaces the polling that lived
  // here).
  const [tab, setTab] = useState('overview')
  // Which of Data Entry's three sub-pages (subjects/teachers/plan) is
  // active — lifted up here rather than kept local to DataEntryTab so
  // the header progress bar and OverviewTab's step cards can jump
  // straight to e.g. "Teachers" instead of just landing on Data Entry
  // and making the admin find the right sub-page themselves.
  const [dataEntrySubView, setDataEntrySubView] = useState('subjects')
  // Whether loadSchools()/loadSchoolData() have resolved at least once
  // for the current user/school — distinct from schools.length === 0 /
  // classGroups.length === 0, which is also true *while the fetch is
  // still in flight* right after login. Without this, the "Create your
  // school" prompt and FirstRunWelcome (both genuine "you truly have
  // none of these yet" screens) briefly flash on every sign-in, since
  // their trigger condition is indistinguishable from "still loading"
  // by array length alone. Gate rendering on these instead of on the
  // arrays themselves, and show a spinner for that brief window.
  const [schoolsReady, setSchoolsReady] = useState(false)
  const [schoolDataReady, setSchoolDataReady] = useState(false)
  const [error, setError] = useState(null)
  // Add-school is a small modal rather than window.prompt() — a native
  // browser dialog looked jarring next to an otherwise fully custom UI,
  // and couldn't show a "please wait" state or a proper error.
  const [addSchoolOpen, setAddSchoolOpen] = useState(false)
  const [newSchoolName, setNewSchoolName] = useState('')
  const [newInstitutionType, setNewInstitutionType] = useState('school') // 'school' | 'college'
  const [creatingSchool, setCreatingSchool] = useState(false)
  // Unauthenticated visitors see LandingPage.jsx first (marketing page,
  // "Get started"/"Sign in" CTAs), not straight-to-login — this flips to
  // true once one of those is clicked, revealing AuthPage. Reset to false
  // on logout so signing out lands back on the marketing page, not a bare
  // login form.
  //
  // Also seeded from `?start=auth` on initial load — PricingPage's CTAs
  // are a real navigation (full page reload, no client router — see
  // legalPage below), not a same-page state flip, so a "Get started"
  // click there has to encode the intent in the URL it navigates to
  // rather than just calling setShowAuth(true) directly.
  const [showAuth, setShowAuth] = useState(
    () => new URLSearchParams(window.location.search).get('start') === 'auth'
  )

  // Drop `?start=auth` once read above — same reasoning as
  // handleInviteAccepted/handlePasswordReset below (replaceState, not a
  // real navigation, so it doesn't re-trigger on a later refresh/back).
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('start') === 'auth') {
      window.history.replaceState(null, '', window.location.pathname)
    }
  }, [])

  // This app has no client-side router (see AcceptInvitePage.jsx's
  // docstring) — an invite link is just `?invite=<token>` on the same
  // URL, checked once on load. Kept in state (not re-read from the URL
  // on every render) so it doesn't reappear if the user navigates within
  // the app after accepting/dismissing it.
  const [inviteToken] = useState(() => new URLSearchParams(window.location.search).get('invite'))
  const [inviteHandled, setInviteHandled] = useState(false)

  // Same reasoning as inviteToken above — a password-reset link is
  // `?reset=<token>` on the same URL, checked once on load.
  const [resetToken] = useState(() => new URLSearchParams(window.location.search).get('reset'))
  const [resetHandled, setResetHandled] = useState(false)

  // Same "no client-side router, so read it once from the URL" pattern as
  // inviteToken/resetToken above — LandingPage.jsx's footer links to
  // `?page=privacy` / `?page=terms` with a plain <a>, which triggers a
  // real navigation (full reload) rather than a route change, so this
  // only needs to be read on initial mount, not watched afterwards.
  const [legalPage] = useState(() => new URLSearchParams(window.location.search).get('page'))

  // On load, if a token is already stored, validate it via /auth/me instead
  // of bouncing straight to the login screen.
  useEffect(() => {
    async function checkSession() {
      if (!getToken()) {
        setCheckingSession(false)
        return
      }
      try {
        setUser(await api.me())
      } catch {
        setToken(null)
      } finally {
        setCheckingSession(false)
      }
    }
    checkSession()
  }, [])

  useEffect(() => {
    if (!user) return
    loadSchools()
  }, [user])

  useEffect(() => {
    if (!selectedSchoolId) return
    setSchoolDataReady(false)
    loadSchoolData(selectedSchoolId)
  }, [selectedSchoolId])

  async function loadSchools() {
    try {
      const list = await api.listSchools()
      setSchools(list)
      setError(null)
      if (list.length > 0) setSelectedSchoolId((prev) => prev ?? list[0].id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSchoolsReady(true)
    }
  }

  async function loadSchoolData(schoolId) {
    try {
      // Members/invites are admin-only endpoints (GET .../members and
      // .../invites both 403 a viewer) — skipped entirely for a non-admin
      // rather than let that 403 reject this whole Promise.all and leave
      // every other tab (Subjects, Teachers, Timetable, ...) with no data
      // at all just because Team isn't something a viewer can see anyway
      // (App.jsx only adds the Team tab for `role === 'admin'`).
      const isAdmin = schools.find((s) => s.id === schoolId)?.role === 'admin'
      const [cg, t, s, p, c, mem, inv, reqs] = await Promise.all([
        api.listClassGroups(schoolId),
        api.listTeachers(schoolId),
        api.listSubjects(schoolId),
        api.listPeriods(schoolId),
        api.listConstraints(schoolId),
        isAdmin ? api.listMembers(schoolId) : Promise.resolve([]),
        isAdmin ? api.listInvites(schoolId) : Promise.resolve([]),
        api.listAllRequirements(schoolId),
      ])
      setClassGroups(cg)
      setTeachers(t)
      setSubjects(s)
      setPeriods(p)
      setConstraints(c)
      setMembers(mem)
      setInvites(inv)
      setAllRequirements(reqs)
      setError(null)
      setSelectedClassGroupId((prev) =>
        cg.some((c) => c.id === prev) ? prev : cg[0]?.id ?? null
      )
    } catch (err) {
      setError(err.message)
    } finally {
      setSchoolDataReady(true)
    }
  }

  // Narrower than loadSchoolData (which also re-fetches classGroups/
  // teachers/subjects/periods/rooms/timetables) — a constraint add/edit/
  // delete/scope-change can't affect any of those, but a full re-fetch of
  // *constraints* specifically is still needed after one (rather than
  // patching the changed row locally) because each card's `conflicts` is
  // computed server-side against every other constraint, so adding or
  // editing one can change what a completely different card should show.
  async function reloadConstraints() {
    try {
      setConstraints(await api.listConstraints(selectedSchoolId))
    } catch (err) {
      setError(err.message)
    }
  }

  // Narrower than loadSchoolData, same reasoning as reloadConstraints
  // above — an invite/role-change/remove/revoke only ever affects the
  // member/invite lists, not any of the school's other data.
  async function reloadTeam() {
    try {
      const [mem, inv] = await Promise.all([api.listMembers(selectedSchoolId), api.listInvites(selectedSchoolId)])
      setMembers(mem)
      setInvites(inv)
    } catch (err) {
      setError(err.message)
    }
  }

  async function submitAddSchool(e) {
    e.preventDefault()
    if (!newSchoolName.trim() || creatingSchool) return
    setCreatingSchool(true)
    try {
      const school = await api.createSchool({
        name: newSchoolName.trim(),
        institution_type: newInstitutionType,
      })
      setError(null)
      await loadSchools()
      setSelectedSchoolId(school.id)
      setAddSchoolOpen(false)
      setNewSchoolName('')
      setNewInstitutionType('school')
    } catch (err) {
      setError(err.message)
    } finally {
      setCreatingSchool(false)
    }
  }

  async function handleAddClassGroup(grade, name) {
    try {
      await api.createClassGroup({ school_id: selectedSchoolId, grade, name })
      setError(null)
      await loadSchoolData(selectedSchoolId)
    } catch (err) {
      setError(err.message)
    }
  }

  // Bulk sibling of handleAddClassGroup — used by BulkAddClassGroups.jsx's
  // range form (e.g. "Grade 1-12" x "Sections A-C" = 36 in one go).
  // Fires every create in parallel and reloads once at the end, rather
  // than calling handleAddClassGroup in a loop (which would reload school
  // data after every single one — wasteful for dozens of creates, and the
  // repeated re-renders would fight with the form's own submitting state).
  async function handleAddClassGroups(pairs) {
    try {
      await Promise.all(
        pairs.map(({ grade, name }) => api.createClassGroup({ school_id: selectedSchoolId, grade, name }))
      )
      setError(null)
      await loadSchoolData(selectedSchoolId)
    } catch (err) {
      setError(err.message)
      // Some may have succeeded before one failed — refresh regardless so
      // the sidebar/list reflects whatever did get created rather than
      // looking stale until the next unrelated reload.
      await loadSchoolData(selectedSchoolId)
    }
  }

  async function handleUpdateClassGroup(classGroupId, data) {
    try {
      await api.updateClassGroup(classGroupId, data)
      setError(null)
      await loadSchoolData(selectedSchoolId)
    } catch (err) {
      setError(err.message)
    }
  }

  // Renames a grade heading for every section under it at once — "grade"
  // is just a shared string, not its own row, so fixing a shared typo
  // (or relabeling "Grade 8" to "Grade VIII") shouldn't require editing
  // each section individually. oldGrade is the sidebar's grouping key,
  // which is the literal string "Ungrouped" for sections with no grade.
  async function handleRenameGrade(oldGrade, newGrade) {
    try {
      const targets = classGroups.filter((cg) => (cg.grade || 'Ungrouped') === oldGrade)
      await Promise.all(
        targets.map((cg) => api.updateClassGroup(cg.id, { grade: newGrade.trim() || null }))
      )
      setError(null)
      await loadSchoolData(selectedSchoolId)
    } catch (err) {
      setError(err.message)
      await loadSchoolData(selectedSchoolId)
    }
  }

  // Persists the sidebar's admin-customized grade order — see
  // School.grade_order's docstring on the backend. Updates `schools`
  // locally from the response instead of a full loadSchoolData() reload,
  // since reordering grades can't have changed anything else.
  async function handleReorderGrades(newOrder) {
    try {
      const updated = await api.updateSchoolGradeOrder(selectedSchoolId, newOrder)
      setSchools((prev) => prev.map((s) => (s.id === selectedSchoolId ? updated : s)))
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  // Lets an admin fix a school's school-vs-college label after creation —
  // previously only set once, in the create-school modal, with no way to
  // change it and no indicator anywhere showing which one a school was
  // (see docs/ARCHITECTURE.md's "School vs. college" section). Same
  // local-patch pattern as handleReorderGrades above: this can't have
  // changed anything else, so there's no need for a full reload.
  async function handleUpdateInstitutionType(newType) {
    try {
      const updated = await api.updateSchoolInstitutionType(selectedSchoolId, newType)
      setSchools((prev) => prev.map((s) => (s.id === selectedSchoolId ? updated : s)))
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteClassGroup(classGroup) {
    const label = classGroup.grade ? `${classGroup.grade} - ${classGroup.name}` : classGroup.name
    if (
      !window.confirm(
        `Delete Section ${label}? This also removes its subject requirements and any generated timetable entries for this section. This can't be undone.`
      )
    ) {
      return
    }
    try {
      await api.deleteClassGroup(classGroup.id)
      setError(null)
      // If the deleted section was selected, loadSchoolData's own
      // fallback logic (`cg.some((c) => c.id === prev) ? prev : cg[0]?.id
      // ?? null`) picks another one automatically — nothing extra needed
      // here.
      await loadSchoolData(selectedSchoolId)
    } catch (err) {
      setError(err.message)
    }
  }

  function handleLogout() {
    stopTimetablePolling()
    setToken(null)
    setUser(null)
    setSchools([])
    setSelectedSchoolId(null)
    setClassGroups([])
    setSelectedClassGroupId(null)
    setTeachers([])
    setSubjects([])
    setPeriods([])
    setConstraints([])
    setMembers([])
    setInvites([])
    setAllRequirements([])
    setShowAuth(false)
    setSchoolsReady(false)
    setSchoolDataReady(false)
  }

  function handleInviteAccepted(acceptedUser) {
    setInviteHandled(true)
    // Drop the ?invite=... param so refreshing/navigating later doesn't
    // re-show this screen — replaceState rather than a real navigation
    // since there's no router to do it "properly" with.
    window.history.replaceState(null, '', window.location.pathname)
    setUser(acceptedUser)
  }

  function handlePasswordReset(resetUser) {
    setResetHandled(true)
    window.history.replaceState(null, '', window.location.pathname)
    setUser(resetUser)
  }

  const selectedSchool = schools.find((s) => s.id === selectedSchoolId)
  const selectedClassGroup = classGroups.find((c) => c.id === selectedClassGroupId)

  // Single source of truth for "how close is this section to a
  // generated timetable" — shared by the header's compact bar, the
  // Constraints/Timetable tabs' muted-until-ready styling below, and
  // OverviewTab's detailed step cards (see useSetupProgress.js). Called
  // unconditionally (rules-of-hooks) — before login or without a
  // selected section, schoolId/classGroupId are null and the hook just
  // never fires its fetch.
  const setupProgress = useSetupProgress({
    schoolId: selectedClassGroup ? selectedSchoolId : null,
    classGroupId: selectedClassGroupId,
    classGroupLabel: selectedClassGroup ? `Section ${selectedClassGroup.name}` : null,
    // periods/subjects/teachers/constraints/allRequirements are already
    // loaded and kept live here — handed to the hook instead of it
    // independently re-fetching the same lists on every tab switch (this
    // used to include its own listConstraints/listTimetables calls,
    // redundant with both App.jsx's own load and ConstraintsTab's).
    periods,
    subjects,
    teachers,
    constraints,
    hasTimetable: timetable?.status === 'draft',
    allRequirements,
  })

  // Public, no-auth-required pages — checked before the invite/reset/
  // session logic below since they don't depend on any of it (a signed-
  // out visitor, or someone with an unrelated ?invite=/?reset= link still
  // in their address bar, should see the legal page they clicked through
  // to, not get routed into an unrelated flow first).
  if (legalPage === 'privacy') {
    return <PrivacyPolicyPage onBack={() => window.location.assign(window.location.pathname)} />
  }
  if (legalPage === 'terms') {
    return <TermsOfServicePage onBack={() => window.location.assign(window.location.pathname)} />
  }
  if (legalPage === 'pricing') {
    return (
      <PricingPage
        onBack={() => window.location.assign(window.location.pathname)}
        onGetStarted={() => window.location.assign(`${window.location.pathname}?start=auth`)}
      />
    )
  }
  if (legalPage === 'support') {
    return (
      <SupportPage
        onBack={() => window.location.assign(window.location.pathname)}
        onGetStarted={() => window.location.assign(`${window.location.pathname}?start=auth`)}
      />
    )
  }
  if (legalPage === 'why') {
    return (
      <WhyTimetablzPage
        onBack={() => window.location.assign(window.location.pathname)}
        onGetStarted={() => window.location.assign(`${window.location.pathname}?start=auth`)}
      />
    )
  }
  if (legalPage === 'about') {
    return (
      <AboutPage
        onBack={() => window.location.assign(window.location.pathname)}
        onGetStarted={() => window.location.assign(`${window.location.pathname}?start=auth`)}
      />
    )
  }
  if (legalPage === 'customers') {
    return (
      <CustomersPage
        onBack={() => window.location.assign(window.location.pathname)}
        onGetStarted={() => window.location.assign(`${window.location.pathname}?start=auth`)}
      />
    )
  }

  if (inviteToken && !inviteHandled) {
    return <AcceptInvitePage token={inviteToken} onAccepted={handleInviteAccepted} />
  }

  if (resetToken && !resetHandled) {
    return <ResetPasswordPage token={resetToken} onReset={handlePasswordReset} />
  }

  if (checkingSession) {
    // A blank screen while the session check runs read as a frozen/broken
    // app on a slow connection — a small centered spinner at least signals
    // something is happening.
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-50">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
      </div>
    )
  }

  if (!user) {
    return showAuth ? (
      <AuthPage onAuthenticated={setUser} onBack={() => setShowAuth(false)} />
    ) : (
      <LandingPage onGetStarted={() => setShowAuth(true)} />
    )
  }

  const isViewer = selectedSchool?.role === 'viewer'
  const TABS = selectedSchool?.role === 'admin' ? [...BASE_TABS, { id: 'team', label: 'Team' }] : BASE_TABS

  // Jumps to a tab and, for Data Entry, straight to the right sub-page
  // (subjects/teachers/plan) instead of leaving the admin to find it —
  // used by both the header progress bar and OverviewTab's step cards.
  function handleNavigate(tabId, subView) {
    setTab(tabId)
    if (subView) setDataEntrySubView(subView)
  }

  // Data Entry has two distinct modes: school-wide (Subjects/Teachers/
  // Setup, each reached via its own sidebar item, no section implied) and
  // section-scoped (a section's plan, reached by clicking that section in
  // the sidebar). Whichever mode is active determines whether the sidebar
  // should show a section as selected — showing one while browsing the
  // whole school's teacher list is exactly the "why does the sidebar say
  // Section 8-B while I'm looking at every teacher" confusion this avoids.
  const inSchoolWideDataEntry =
    tab === 'entry' && (dataEntrySubView === 'subjects' || dataEntrySubView === 'teachers' || dataEntrySubView === 'setup')

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      {schools.length > 0 ? (
        <Sidebar
          schoolName={selectedSchool?.name}
          institutionType={selectedSchool?.institution_type}
          onUpdateInstitutionType={handleUpdateInstitutionType}
          schools={schools}
          selectedSchoolId={selectedSchoolId}
          onSelectSchool={setSelectedSchoolId}
          onAddSchool={() => setAddSchoolOpen(true)}
          classGroups={classGroups}
          selectedClassGroupId={inSchoolWideDataEntry ? null : selectedClassGroupId}
          onSelectClassGroup={(id) => {
            setSelectedClassGroupId(id)
            setDataEntrySubView('plan')
          }}
          onAddClassGroup={handleAddClassGroup}
          onAddClassGroups={handleAddClassGroups}
          onDeleteClassGroup={handleDeleteClassGroup}
          onUpdateClassGroup={handleUpdateClassGroup}
          onRenameGrade={handleRenameGrade}
          gradeOrder={selectedSchool?.grade_order}
          onReorderGrades={handleReorderGrades}
          onGoToDataEntry={(subView) => {
            setTab('entry')
            setDataEntrySubView(subView)
          }}
          activeDataEntrySubView={inSchoolWideDataEntry ? dataEntrySubView : null}
          readOnly={isViewer}
        />
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex flex-wrap items-center gap-4 border-b border-slate-200 bg-white px-6 py-3">
          {selectedSchool ? (
            <div className="mr-4 flex items-center gap-1.5 text-sm">
              <span className="font-semibold">{selectedSchool.name}</span>
              {isViewer && (
                <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-500">
                  View only
                </span>
              )}
            </div>
          ) : (
            <span className="mr-4 text-sm text-slate-500">Create a school to get started</span>
          )}

          {selectedSchool && (
            <div className="ml-auto flex items-center gap-3">
              <SetupProgressBar progress={setupProgress} onNavigate={handleNavigate} />
              <nav className="flex gap-1 text-sm">
                {TABS.map((t) => {
                  // Constraints/Timetable can't do anything useful until
                  // the basics exist (no subjects/teachers means an empty
                  // Constraints screen and a Timetable tab that can only
                  // fail) — muted rather than hidden or disabled, so
                  // someone who wants to peek still can.
                  const muted = ['constraints', 'timetable'].includes(t.id) && !setupProgress.allRequiredDone
                  return (
                    <button
                      key={t.id}
                      onClick={() => setTab(t.id)}
                      className={`relative rounded-md px-3 py-1.5 font-medium ${
                        tab === t.id ? 'text-white' : muted ? 'text-slate-300 hover:bg-slate-100 hover:text-slate-500' : 'text-slate-500 hover:bg-slate-100'
                      }`}
                    >
                      {tab === t.id && (
                        <motion.span
                          layoutId="tab-active-pill"
                          transition={{ type: 'spring', stiffness: 500, damping: 40 }}
                          className="absolute inset-0 rounded-md bg-neutral-900"
                        />
                      )}
                      <span className="relative z-10">{t.label}</span>
                    </button>
                  )
                })}
              </nav>
            </div>
          )}

          <button onClick={handleLogout} className="ml-2 text-xs text-slate-400 hover:text-slate-700">
            Sign out
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-10 py-8">
          {!schoolsReady ? (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-500" />
              Loading…
            </div>
          ) : schools.length === 0 ? (
            <button
              onClick={() => setAddSchoolOpen(true)}
              className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
            >
              Create your school
            </button>
          ) : null}

          {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

          {selectedSchool && !schoolDataReady && (
            <div className="flex items-center gap-2 text-sm text-slate-400">
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-500" />
              Loading…
            </div>
          )}

          {selectedSchool && schoolDataReady && (
            // No exit animation (and no AnimatePresence) here on purpose:
            // an in-flight async update on the outgoing tab (e.g. Data
            // Entry's periods/week field saving right as you switch tabs)
            // can re-render it mid-exit, which can prevent Framer
            // Motion's exit-complete callback from ever firing — leaving
            // a zero-opacity but still-laid-out copy of the old tab stuck
            // in the DOM forever, pushing the new content down. Plain
            // key-based remounting has no exit phase to get stuck in, so
            // this can't happen; the enter animation below still plays.
            <motion.div
              key={tab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15, ease: 'easeOut' }}
            >
                {/* Overview is the one tab that still needs a section to
                    do anything (it tracks one section's progress toward a
                    generated timetable), so a school with none yet sees
                    the "add your first section" flow here instead of it
                    blocking every other tab — Subjects/Teachers and even
                    Constraints are school-wide and don't need one. */}
                {tab === 'overview' && (
                  selectedClassGroup ? (
                    <OverviewTab
                      classGroup={selectedClassGroup}
                      onNavigate={handleNavigate}
                      progress={setupProgress}
                    />
                  ) : isViewer ? (
                    <p className="text-sm text-slate-500">
                      {selectedSchool.name} doesn't have any grades/sections set up yet. An admin
                      needs to add one before there's anything here to view.
                    </p>
                  ) : (
                    <FirstRunWelcome
                      schoolName={selectedSchool.name}
                      institutionType={selectedSchool.institution_type}
                      onAddClassGroup={handleAddClassGroup}
                      onAddClassGroups={handleAddClassGroups}
                    />
                  )
                )}
                {tab === 'entry' && (
                  <DataEntryTab
                    schoolId={selectedSchoolId}
                    classGroupId={selectedClassGroupId}
                    institutionType={selectedSchool?.institution_type}
                    subjects={subjects}
                    setSubjects={setSubjects}
                    teachers={teachers}
                    setTeachers={setTeachers}
                    periods={periods}
                    setPeriods={setPeriods}
                    classGroups={classGroups}
                    allRequirements={allRequirements}
                    setAllRequirements={setAllRequirements}
                    onReloadSchoolData={() => loadSchoolData(selectedSchoolId)}
                    readOnly={isViewer}
                    subView={dataEntrySubView}
                    onSubViewChange={setDataEntrySubView}
                  />
                )}
                {tab === 'constraints' && (
                  <ConstraintsTab
                    schoolId={selectedSchoolId}
                    classGroups={classGroups}
                    constraints={constraints}
                    onReload={reloadConstraints}
                    readOnly={isViewer}
                  />
                )}
                {tab === 'timetable' && (
                  selectedClassGroup ? (
                    <TimetableTab
                      schoolId={selectedSchoolId}
                      classGroup={selectedClassGroup}
                      classGroups={classGroups}
                      teachers={teachers}
                      periods={periods}
                      constraints={constraints}
                      readOnly={isViewer}
                    />
                  ) : (
                    <p className="text-sm text-slate-500">
                      No grades/sections yet — the timetable is generated per section, so add one
                      from the sidebar first.
                    </p>
                  )
                )}
                {tab === 'team' && selectedSchool?.role === 'admin' && (
                  <TeamTab
                    schoolId={selectedSchoolId}
                    members={members}
                    invites={invites}
                    onReload={reloadTeam}
                  />
                )}
            </motion.div>
          )}
        </div>
      </div>

      <AnimatePresence>
      {addSchoolOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4"
        >
          <motion.form
            initial={{ opacity: 0, scale: 0.97, y: 6 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 6 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            onSubmit={submitAddSchool}
            className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-lg"
          >
            <h2 className="text-lg font-semibold">New school</h2>

            <span className="mb-1 mt-4 block text-xs font-medium text-slate-500">Type</span>
            <div className="flex gap-2">
              {[
                { value: 'school', label: 'School' },
                { value: 'college', label: 'College' },
              ].map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setNewInstitutionType(opt.value)}
                  className={`flex-1 rounded-md border px-3 py-2 text-sm font-medium ${
                    newInstitutionType === opt.value
                      ? 'border-neutral-900 bg-neutral-900 text-white'
                      : 'border-slate-300 text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <p className="mt-1.5 text-xs text-slate-400">
              Just sets sensible defaults (terminology, which optional fields show up) — you can
              still use anything either way.
            </p>

            <label className="mb-1 mt-4 block text-xs font-medium text-slate-500" htmlFor="new-school-name">
              {newInstitutionType === 'college' ? 'College name' : 'School name'}
            </label>
            <input
              id="new-school-name"
              autoFocus
              value={newSchoolName}
              onChange={(e) => setNewSchoolName(e.target.value)}
              placeholder={newInstitutionType === 'college' ? 'e.g. Riverside College of Engineering' : 'e.g. Riverside Public School'}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-neutral-900 focus:outline-none"
            />
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => {
                  setAddSchoolOpen(false)
                  setNewSchoolName('')
                  setNewInstitutionType('school')
                }}
                className="rounded-md px-3 py-2 text-sm font-medium text-slate-500 hover:bg-slate-100"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={!newSchoolName.trim() || creatingSchool}
                className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700 disabled:opacity-50"
              >
                {creatingSchool ? 'Creating…' : 'Create school'}
              </button>
            </div>
          </motion.form>
        </motion.div>
      )}
      </AnimatePresence>
    </div>
  )
}

export default App
