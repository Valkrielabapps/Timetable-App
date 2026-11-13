package com.timetablz.app.data

/** "Grade 2 A" before "Grade 10 A": numbers compared as numbers, the rest ignoring case. */
object Natural : Comparator<String> {
    private val parts = Regex("\\d+|\\D+")

    override fun compare(a: String, b: String): Int {
        val x = parts.findAll(a.lowercase()).map { it.value }.toList()
        val y = parts.findAll(b.lowercase()).map { it.value }.toList()
        for (i in 0 until minOf(x.size, y.size)) {
            val p = x[i]
            val q = y[i]
            val c = if (p[0].isDigit() && q[0].isDigit()) {
                p.trimStart('0').length.compareTo(q.trimStart('0').length).takeIf { it != 0 } ?: p.trimStart('0').compareTo(q.trimStart('0'))
            } else p.compareTo(q)
            if (c != 0) return c
        }
        return x.size.compareTo(y.size)
    }
}
