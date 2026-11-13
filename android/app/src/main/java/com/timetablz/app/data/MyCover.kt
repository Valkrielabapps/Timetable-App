package com.timetablz.app.data

/** One lesson the signed-in teacher has been given as cover. */
data class MyCoverItem(
    val key: String,
    val date: String,
    val periodId: Int,
    val periodLabel: String,
    val order: Int,
    val classGroup: String,
    val subject: String,
    val forTeacher: String,
)

object MyCover {
    /** The teacher this account is: the one chosen in Settings, else the one with the same email. */
    fun whoAmI(teachers: List<Teacher>, email: String?, chosen: Int?): Teacher? =
        teachers.firstOrNull { it.id == chosen }
            ?: email?.let { e -> teachers.firstOrNull { it.email?.trim().equals(e.trim(), ignoreCase = true) } }

    /** Every lesson [me] covers, from the school's saved cover, soonest first. */
    fun of(
        me: Int,
        covers: List<SavedCover>,
        periods: List<Period>,
        entries: List<Entry>,
        teachers: List<Teacher>,
        subjectNames: Map<Int, String>,
    ): List<MyCoverItem> {
        val period = periods.associateBy { it.id }
        val section = entries.associate { it.classGroupId to it.classGroupName }
        val teacher = teachers.associate { it.id to it.name }
        return covers.flatMap { cover ->
            val date = cover.date ?: return@flatMap emptyList()
            cover.changes.filter { it.substituteId == me }.map { c ->
                val p = period[c.periodId]
                MyCoverItem(
                    key = "$date:${c.periodId}:${c.classGroupId}",
                    date = date,
                    periodId = c.periodId,
                    periodLabel = p?.short ?: "",
                    order = p?.order ?: 0,
                    classGroup = section[c.classGroupId] ?: "A section",
                    subject = c.subjectId?.let { subjectNames[it] } ?: "",
                    forTeacher = teacher[c.absentTeacherId] ?: "",
                )
            }
        }.distinctBy { it.key }.sortedWith(compareBy({ it.date }, { it.order }))
    }

    /** "9:00-9:45" or "1.30 pm to 2.15 pm" in a period's label -> start and end (h, m). Same rules as the backend's. */
    private val time = Regex("(\\d{1,2})[:.](\\d{2})\\s*(am|pm)?\\s*(?:-|–|—|to)\\s*(\\d{1,2})[:.](\\d{2})\\s*(am|pm)?", RegexOption.IGNORE_CASE)

    fun times(label: String?): Pair<Pair<Int, Int>, Pair<Int, Int>>? {
        val m = time.find(label ?: "") ?: return null
        fun hm(h: String, mi: String, ap: String?, other: String?): Pair<Int, Int> {
            var hour = h.toInt()
            val a = (ap?.takeIf { it.isNotEmpty() } ?: other ?: "").lowercase()
            if (a == "pm" && hour < 12) hour += 12
            if (a == "am" && hour == 12) hour = 0
            if (a.isEmpty() && hour in 1..6) hour += 12
            return hour to mi.toInt()
        }
        val g = m.groupValues
        val start = hm(g[1], g[2], g[3], g[6])
        val end = hm(g[4], g[5], g[6], g[3])
        if (start.first !in 0..23 || end.first !in 0..23 || compareValues(start.first * 60 + start.second, end.first * 60 + end.second) >= 0) return null
        return start to end
    }
}
