"""Timetablz homepage ad: an 18-second product run-through, drawn frame by
frame with cairo and encoded with ffmpeg. All school data is made up."""
import math
import subprocess
import sys

import cairocffi as cairo

W, H, FPS, DUR = 1920, 1080, 30, 18.0
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/ad/out.mp4"
ONLY = [float(x) for x in sys.argv[2:]]  # times to dump as PNG instead

# ---------------------------------------------------------------- helpers

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def seg(t, a, b):
    return clamp((t - a) / (b - a)) if b > a else float(t >= a)

def ease(x):  # cubic in-out
    x = clamp(x)
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2

def out(x):  # cubic out
    x = clamp(x)
    return 1 - (1 - x) ** 3

def back(x):  # overshoot
    x = clamp(x)
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

def lerp(a, b, x):
    return a + (b - a) * x

def hexc(h, a=1.0):
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)

INK = "#171717"
SLATE5 = "#64748b"
SLATE4 = "#94a3b8"
SLATE2 = "#e2e8f0"
SLATE1 = "#f1f5f9"
SLATE05 = "#f8fafc"
GREEN_BG, GREEN_RING = "#d1fae5", "#34d399"
AMBER_BG, AMBER_RING = "#fef3c7", "#fbbf24"
RED_BG, RED_RING = "#fee2e2", "#f87171"
EMER50 = "#ecfdf5"

HV = "TeX Gyre Heros"   # Helvetica-style: clean and neutral, in and out of the app
FONTS = {"r": (HV, 0), "m": (HV, 0), "b": (HV, 1), "h": (HV, 1), "pm": (HV, 0), "pb": (HV, 1)}

def font(c, w, size):
    fam, bold = FONTS[w]
    c.select_font_face(fam, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    c.set_font_size(size)

def text(c, s, x, y, size=16, w="r", color=INK, alpha=1.0, align="l"):
    font(c, w, size)
    ext = c.text_extents(s)
    if align == "c":
        x -= ext[4] / 2
    elif align == "r":
        x -= ext[4]
    col = hexc(color) if isinstance(color, str) else color
    c.set_source_rgba(col[0], col[1], col[2], col[3] * alpha)
    c.move_to(x, y)
    c.show_text(s)
    # show_text leaves a current point; without this the next arc or shape
    # starts with a line drawn from the end of the text.
    c.new_path()
    return ext[4]

def tw(c, s, size, w="r"):
    font(c, w, size)
    return c.text_extents(s)[4]

def rrect(c, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    c.new_sub_path()
    c.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    c.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    c.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    c.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    c.close_path()

def fill(c, color, alpha=1.0):
    col = hexc(color) if isinstance(color, str) else color
    c.set_source_rgba(col[0], col[1], col[2], col[3] * alpha)
    c.fill()

def box(c, x, y, w, h, r, bg=None, border=None, alpha=1.0, lw=1.5):
    if bg:
        rrect(c, x, y, w, h, r)
        fill(c, bg, alpha)
    if border:
        rrect(c, x + lw / 2, y + lw / 2, w - lw, h - lw, r)
        col = hexc(border)
        c.set_source_rgba(col[0], col[1], col[2], alpha)
        c.set_line_width(lw)
        c.stroke()

def shadow(c, x, y, w, h, r, strength=1.0, spread=28, dy=18):
    for i in range(spread, 0, -2):
        rrect(c, x - i * 0.6, y - i * 0.6 + dy * (i / spread), w + i * 1.2, h + i * 1.2, r + i)
        c.set_source_rgba(0.06, 0.09, 0.16, 0.010 * strength)
        c.fill()

def check(c, x, y, s, color="#ffffff", lw=2.4):
    col = hexc(color)
    c.set_source_rgba(*col)
    c.set_line_width(lw)
    c.set_line_cap(cairo.LINE_CAP_ROUND)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.move_to(x, y + s * 0.5)
    c.line_to(x + s * 0.38, y + s * 0.86)
    c.line_to(x + s, y + s * 0.12)
    c.stroke()

def cursor(c, x, y, press=0.0):
    c.save()
    c.translate(x, y)
    sc = 1 - 0.12 * press
    c.scale(1.35 * sc, 1.35 * sc)
    pts = [(0, 0), (0, 22), (6, 16.5), (10.5, 26), (14, 24.4), (9.6, 15.2), (17.5, 15.2)]
    for k in range(6, 0, -1):  # soft shadow
        c.move_to(pts[0][0] + 1.5, pts[0][1] + 2.5)
        for p in pts[1:]:
            c.line_to(p[0] + 1.5, p[1] + 2.5)
        c.close_path()
        c.set_source_rgba(0, 0, 0, 0.035)
        c.set_line_width(k * 1.6)
        c.stroke_preserve()
        c.new_path()
    c.move_to(*pts[0])
    for p in pts[1:]:
        c.line_to(*p)
    c.close_path()
    c.set_source_rgb(0.07, 0.07, 0.07)
    c.fill_preserve()
    c.set_source_rgb(1, 1, 1)
    c.set_line_width(1.6)
    c.set_line_join(cairo.LINE_JOIN_ROUND)
    c.stroke()
    c.restore()
    if press > 0:
        c.set_source_rgba(0.09, 0.09, 0.09, 0.18 * press)
        c.arc(x + 2, y + 2, 26 * press + 8, 0, 2 * math.pi)
        c.fill()

def path_at(t, keys):
    """keys: [(time, x, y)] - eased movement between them."""
    if t <= keys[0][0]:
        return keys[0][1], keys[0][2]
    for (t0, x0, y0), (t1, x1, y1) in zip(keys, keys[1:]):
        if t <= t1:
            k = ease(seg(t, t0, t1))
            return lerp(x0, x1, k), lerp(y0, y1, k)
    return keys[-1][1], keys[-1][2]

# ---------------------------------------------------------------- data

SCHOOL = "Riverside Public School"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
T = {"Eng": ("English", "Ms. Fernandes"), "Mat": ("Maths", "Mr. Khan"), "Phy": ("Physics", "Mrs. Iyer"),
     "Che": ("Chemistry", "Mr. Rao"), "Bio": ("Biology", "Ms. Menon"), "Hin": ("Hindi", "Mrs. Sharma"),
     "Soc": ("Social Science", "Ms. Gupta"), "Com": ("Computer", "Mr. Das"), "PE": ("PE", "Mr. Singh"),
     "Art": ("Art", "Ms. Pillai"), "Lab": ("Physics Lab", "Mrs. Iyer")}
GRID = [  # rows = periods 1..6, columns = days
    ["Eng", "Mat", "Phy", "Bio", "Che"],
    ["Mat", "Che", "Eng", "Mat", "Lab"],
    ["Phy", "Eng", "Che", "Hin", "Lab"],
    ["Hin", "Soc", "Mat", "Eng", "Mat"],
    ["Com", "Bio", "Soc", "Com", "Eng"],
    ["PE", "Art", "Hin", "Soc", "PE"],
]
# The drag: Wed P3 Chemistry -> Thu P5 Computer (green), swapping.
SRC = (2, 2)      # row, col
DST = (4, 3)
HOVER_RED = (3, 1)  # Tue P4
STATUS = {}
for r in range(6):
    for d in range(5):
        STATUS[(r, d)] = "ok"
for k in [(0, 2), (3, 1), (1, 4), (5, 0)]:
    STATUS[k] = "blocked"
for k in [(0, 4), (5, 3)]:
    STATUS[k] = "warn"
STATUS[SRC] = "src"

# ---------------------------------------------------------------- app frame

WX, WY, WW, WH = 150, 60, 1620, 900   # window in screen space
SIDE = 252
TOP = 46      # browser bar
NAVH = 62     # app header

def app_chrome(c, active_step, done_steps, a=1.0):
    # window
    box(c, 0, 0, WW, WH, 18, bg="#ffffff")
    # browser bar
    c.save()
    rrect(c, 0, 0, WW, WH, 18)
    c.clip()
    c.rectangle(0, 0, WW, TOP)
    fill(c, "#f4f4f5")
    for i, col in enumerate(["#d4d4d8", "#d4d4d8", "#d4d4d8"]):
        c.arc(24 + i * 22, TOP / 2, 6.5, 0, 2 * math.pi)
        fill(c, col)
    box(c, 560, 9, 500, 28, 14, bg="#ffffff")
    text(c, "timetablz.com", 810, 28, 15, "m", SLATE5, align="c")
    c.rectangle(0, TOP - 1, WW, 1)
    fill(c, SLATE2)
    # sidebar
    c.rectangle(0, TOP, SIDE, WH - TOP)
    fill(c, "#fbfbfc")
    c.rectangle(SIDE - 1, TOP, 1, WH - TOP)
    fill(c, SLATE2)
    box(c, 16, TOP + 16, SIDE - 32, 44, 10, bg="#ffffff", border=SLATE2)
    c.arc(40, TOP + 38, 10, 0, 2 * math.pi)
    fill(c, INK)
    text(c, "R", 40, TOP + 43, 13, "b", "#ffffff", align="c")
    text(c, "Riverside Public…", 58, TOP + 43, 15, "m")
    y = TOP + 92
    for name in ["Dashboard", "Calendar", "Settings"]:
        text(c, name, 30, y, 15, "m", "#334155")
        y += 34
    text(c, "GRADES & SECTIONS", 30, y + 18, 11.5, "b", SLATE4)
    y += 50
    for g in [6, 7, 8, 9, 10]:
        text(c, f"Grade {g}", 30, y, 15, "m", "#334155")
        y += 28
        for s in "AB":
            sel = g == 9 and s == "A" and active_step == 4
            if sel:
                box(c, 22, y - 19, SIDE - 44, 28, 7, bg=SLATE1)
            text(c, f"Section {s}", 48, y, 14, "m" if sel else "r", INK if sel else SLATE5)
            y += 28
        y += 4
    # header
    c.rectangle(SIDE, TOP + NAVH - 1, WW - SIDE, 1)
    fill(c, SLATE2)
    text(c, SCHOOL, SIDE + 30, TOP + 39, 17, "b")
    steps = ["Setup", "Subjects", "Teachers", "Constraints", "Timetable"]
    x = WW - 30
    widths = [tw(c, s, 15, "m") + 58 for s in steps]
    x -= sum(widths) + 8 * (len(steps) - 1)
    for i, (s, wdt) in enumerate(zip(steps, widths)):
        act = i == active_step
        if act:
            box(c, x, TOP + 14, wdt, 34, 17, bg=INK)
        cx, cy = x + 20, TOP + 31
        if i in done_steps and not act:
            c.arc(cx, cy, 10, 0, 2 * math.pi)
            fill(c, INK)
            check(c, cx - 5, cy - 4.5, 10, lw=2)
        else:
            c.arc(cx, cy, 10, 0, 2 * math.pi)
            col = hexc("#ffffff" if act else SLATE4)
            c.set_source_rgba(*col)
            c.set_line_width(1.6)
            c.stroke()
            text(c, str(i + 1), cx, cy + 4.5, 12, "b", "#ffffff" if act else SLATE5, align="c")
        text(c, s, x + 36, TOP + 36, 15, "m", "#ffffff" if act else "#334155")
        x += wdt + 8
    c.restore()

CX0 = SIDE + 40          # content origin, window space
CY0 = TOP + NAVH + 34

# ---- scene A: setup / dashboard ---------------------------------------

def scene_setup(c, t):
    k = seg(t, 2.3, 4.6)
    text(c, "Good morning", CX0, CY0 + 30, 32, "b")
    text(c, f"{SCHOOL} · Term 2 timetable", CX0, CY0 + 62, 17, "r", SLATE5)
    stats = [("Sections", 18), ("Teachers", 32), ("Subjects", 14), ("Rules", 9), ("Periods a week", 40)]
    cw, gap = 236, 18
    for i, (lab, n) in enumerate(stats):
        a = out(seg(t, 2.25 + i * 0.12, 2.75 + i * 0.12))
        x = CX0 + i * (cw + gap)
        y = CY0 + 96 + (1 - a) * 18
        box(c, x, y, cw, 104, 14, bg="#ffffff", border=SLATE2, alpha=a)
        text(c, lab, x + 20, y + 34, 15, "m", SLATE5, alpha=a)
        val = int(round(n * out(seg(t, 2.5 + i * 0.12, 3.9 + i * 0.12))))
        text(c, str(val), x + 20, y + 82, 40, "b", INK, alpha=a)
    # sections being planned
    y0 = CY0 + 240
    a = out(seg(t, 2.9, 3.4))
    box(c, CX0, y0, 1290, 470, 16, bg="#ffffff", border=SLATE2, alpha=a)
    text(c, "Sections", CX0 + 26, y0 + 42, 19, "b", alpha=a)
    text(c, "periods planned", CX0 + 1264, y0 + 42, 14, "r", SLATE4, alpha=a, align="r")
    rows = [("Grade 6", "A"), ("Grade 6", "B"), ("Grade 7", "A"), ("Grade 7", "B"), ("Grade 8", "A"),
            ("Grade 8", "B"), ("Grade 9", "A"), ("Grade 9", "B"), ("Grade 10", "A")]
    for i, (g, s) in enumerate(rows):
        ry = y0 + 82 + i * 42
        ra = out(seg(t, 3.0 + i * 0.07, 3.4 + i * 0.07))
        text(c, f"{g} – Section {s}", CX0 + 26, ry + 6, 16, "m", "#334155", alpha=ra)
        bx, bw = CX0 + 260, 840
        box(c, bx, ry - 4, bw, 10, 5, bg=SLATE1, alpha=ra)
        p = out(seg(t, 3.2 + i * 0.09, 4.4 + i * 0.09))
        if p > 0.01:
            box(c, bx, ry - 4, bw * p, 10, 5, bg=INK, alpha=ra)
        n = int(round(40 * p))
        done = n == 40
        text(c, f"{n}/40", CX0 + 1170, ry + 6, 15, "b" if done else "r", INK if done else SLATE5, alpha=ra, align="r")
        if done:
            c.arc(CX0 + 1220, ry + 1, 10, 0, 2 * math.pi)
            fill(c, INK, ra)
            check(c, CX0 + 1215, ry - 3.5, 10, lw=2)

# ---- scene B: plain-English rules -------------------------------------

RULE = "Physics Lab needs two periods back to back"

def scene_rules(c, t):
    text(c, "Constraints", CX0, CY0 + 30, 32, "b")
    text(c, "Describe scheduling rules in plain English.", CX0, CY0 + 62, 17, "r", SLATE5)
    # standard rules ticks
    ys = CY0 + 100
    box(c, CX0, ys, 1290, 150, 16, bg="#ffffff", border=SLATE2)
    text(c, "Standard rules", CX0 + 26, ys + 40, 18, "b")
    for i, s in enumerate(["No teacher has more than 32 periods a week",
                           "Spread each teacher's periods across the day and the week"]):
        yy = ys + 78 + i * 36
        box(c, CX0 + 26, yy - 16, 20, 20, 5, bg=INK)
        check(c, CX0 + 30, yy - 11.5, 12, lw=2)
        text(c, s, CX0 + 58, yy, 16, "r", "#334155")
    # input
    yi = ys + 180
    box(c, CX0, yi, 1150, 60, 12, bg="#ffffff", border="#cbd5e1" if t < 6.2 else INK, lw=2)
    n = int(len(RULE) * seg(t, 6.2, 7.5))
    typed = RULE[:n]
    text(c, typed if typed else "e.g. Maths can't immediately follow PE", CX0 + 22, yi + 38, 19, "r",
         INK if typed else SLATE4)
    if typed and (int(t * 3) % 2 == 0 or t < 7.6):
        cx = CX0 + 22 + tw(c, typed, 19) + 3
        c.rectangle(cx, yi + 17, 2, 26)
        fill(c, INK)
    pressed = seg(t, 7.65, 7.8)
    box(c, CX0 + 1166, yi, 124, 60, 12, bg=INK)
    text(c, "Add", CX0 + 1228, yi + 38, 18, "b", "#ffffff", align="c")
    # understood card
    a = back(seg(t, 7.85, 8.25))
    if a > 0:
        yc = yi + 90 + (1 - a) * 20
        c.save()
        box(c, CX0, yc, 1290, 190, 16, bg=SLATE05, border="#cbd5e1", alpha=clamp(a))
        text(c, "YOU TYPED", CX0 + 28, yc + 38, 12, "b", SLATE4, alpha=clamp(a))
        text(c, RULE, CX0 + 28, yc + 64, 17, "r", SLATE5, alpha=clamp(a))
        text(c, "THIS IS WHAT WE UNDERSTOOD", CX0 + 28, yc + 102, 12, "b", INK, alpha=clamp(a))
        text(c, "For every class, Physics Lab is always taught as a double period.", CX0 + 28, yc + 132, 21, "b",
             alpha=clamp(a))
        ok = seg(t, 8.55, 8.7)
        box(c, CX0 + 28, yc + 148, 168, 34, 9, bg="#404040" if ok > 0 else INK, alpha=clamp(a))
        text(c, "Saved" if ok > 0 else "Yes, that's right", CX0 + 112, yc + 170, 14.5, "b", "#ffffff",
             alpha=clamp(a), align="c")
        c.restore()

# ---- scene C/D: the timetable -------------------------------------------

GX = CX0
GY = CY0 + 138
COLW0, COLW, ROWH, BRK, HDR = 120, 232, 74, 34, 46

def cell_rect(r, d):
    x = GX + COLW0 + d * COLW
    y = GY + HDR + r * ROWH + (BRK if r >= 3 else 0)
    return x, y, COLW, ROWH

def scene_timetable(c, t):
    text(c, "Timetable", CX0, CY0 + 30, 32, "b")
    text(c, "Grade 9 – Section A", CX0, CY0 + 62, 17, "r", SLATE5)
    # generate button
    gen0, gen1 = 9.05, 9.95
    p_click = seg(t, 8.95, 9.05) * (1 - seg(t, 9.05, 9.2))
    bw = 250
    bx, by = CX0 + 1290 - bw, CY0
    generating = gen0 <= t < gen1
    c.save()
    s = 1 - 0.05 * p_click
    c.translate(bx + bw / 2, by + 26)
    c.scale(s, s)
    box(c, -bw / 2, -26, bw, 52, 12, bg=INK)
    label = "Generating…" if generating else ("Generated" if t >= gen1 else "Generate timetable")
    text(c, label, 0, 7, 18, "b", "#ffffff", align="c")
    c.restore()
    if generating or (gen1 <= t < gen1 + 0.4):
        pa = 1 - seg(t, gen1 + 0.1, gen1 + 0.4)
        p = ease(seg(t, gen0, gen1))
        box(c, CX0, CY0 + 88, 1290, 8, 4, bg=SLATE1, alpha=pa)
        box(c, CX0, CY0 + 88, 1290 * p, 8, 4, bg=INK, alpha=pa)
        text(c, f"Solving all 18 sections together… {int(p * 100)}%", CX0, CY0 + 122, 15, "m", SLATE5, alpha=pa)
    # grid frame
    gw = COLW0 + 5 * COLW
    gh = HDR + 6 * ROWH + BRK
    box(c, GX, GY, gw, gh, 14, bg="#ffffff", border=SLATE2)
    c.save()
    rrect(c, GX, GY, gw, gh, 14)
    c.clip()
    c.rectangle(GX, GY, gw, HDR)
    fill(c, SLATE05)
    for d, name in enumerate(DAYS):
        text(c, name, GX + COLW0 + d * COLW + 18, GY + 30, 16, "b", "#334155")
    text(c, "Period", GX + 18, GY + 30, 16, "b", "#334155")
    for r in range(6):
        y = GY + HDR + r * ROWH + (BRK if r >= 3 else 0)
        text(c, f"Period {r + 1}", GX + 18, y + 44, 15, "m", SLATE5)
    yb = GY + HDR + 3 * ROWH
    c.rectangle(GX, yb, gw, BRK)
    fill(c, SLATE05)
    text(c, "Break", GX + 18, yb + 23, 14, "m", SLATE4)
    for d in range(5):
        text(c, "Break", GX + COLW0 + d * COLW + 18, yb + 23, 14, "r", SLATE4)

    drag0, drop = 12.75, 14.85
    dragging = drag0 <= t < drop
    swap_k = ease(seg(t, drop, drop + 0.45))
    swapped = t >= drop

    def status_tint(r, d):
        if not dragging:
            return None
        a = out(seg(t, drag0 + 0.05, drag0 + 0.35))
        st = STATUS[(r, d)]
        return st, a

    for r in range(6):
        for d in range(5):
            x, y, w, h = cell_rect(r, d)
            # reveal order: diagonal sweep
            delay = gen1 + 0.06 + (d * 0.11 + r * 0.075)
            ra = out(seg(t, delay, delay + 0.35))
            if ra <= 0:
                continue
            key = GRID[r][d]
            if swapped and (r, d) == SRC:
                key = GRID[DST[0]][DST[1]]
            elif swapped and (r, d) == DST:
                key = GRID[SRC[0]][SRC[1]]
            subj, teacher = T[key]
            tint = status_tint(r, d)
            bg = EMER50
            ring = None
            alpha_txt = 1.0
            if tint:
                st, a = tint
                if st == "src":
                    alpha_txt = 1 - 0.65 * a
                    bg = SLATE1
                else:
                    bg = {"ok": GREEN_BG, "warn": AMBER_BG, "blocked": RED_BG}[st]
                    ring = {"ok": GREEN_RING, "warn": AMBER_RING, "blocked": RED_RING}[st]
            sc = lerp(0.86, 1.0, back(seg(t, delay, delay + 0.35)))
            cx, cy = x + w / 2, y + h / 2
            c.save()
            c.translate(cx, cy)
            c.scale(sc, sc)
            c.translate(-cx, -cy)
            box(c, x + 5, y + 5, w - 10, h - 10, 9, bg=bg, alpha=ra)
            if ring:
                box(c, x + 5, y + 5, w - 10, h - 10, 9, border=ring, alpha=ra * tint[1], lw=2.5)
            # landed lesson pulses
            if swapped and (r, d) in (SRC, DST):
                pulse = 1 - seg(t, drop + 0.2, drop + 1.1)
                box(c, x + 5, y + 5, w - 10, h - 10, 9, border="#10b981", alpha=pulse, lw=3)
                if (r, d) == DST and swap_k < 1:
                    # flying in from the drop: start offset
                    pass
            text(c, subj, x + 20, y + 35, 17, "b", INK, alpha=ra * alpha_txt)
            text(c, teacher, x + 20, y + 57, 14, "r", SLATE5, alpha=ra * alpha_txt)
            c.restore()
    # grid lines
    for d in range(6):
        x = GX + COLW0 + d * COLW
        c.rectangle(x, GY, 1, gh)
        fill(c, SLATE2)
    c.restore()

    # red cell explanation while hovered
    hover_on = 13.45 <= t < 14.25 and dragging
    if hover_on:
        a = out(seg(t, 13.45, 13.6)) * (1 - seg(t, 14.1, 14.25))
        x, y, w, h = cell_rect(*HOVER_RED)
        msg = "Mr. Rao teaches 10 B then"
        bw2 = tw(c, msg, 17, "b") + 40
        bx2, by2 = x + w / 2 - bw2 / 2, y - 52 - (1 - a) * 6
        shadow(c, bx2, by2, bw2, 42, 10, strength=a, spread=12, dy=6)
        box(c, bx2, by2, bw2, 42, 10, bg="#dc2626", alpha=a)
        c.move_to(x + w / 2 - 9, by2 + 42)
        c.line_to(x + w / 2 + 9, by2 + 42)
        c.line_to(x + w / 2, by2 + 52)
        c.close_path()
        fill(c, "#dc2626", a)
        text(c, msg, x + w / 2, by2 + 27, 17, "b", "#ffffff", alpha=a, align="c")

    # drag ghost follows the cursor
    if dragging:
        mx, my = drag_cursor(t)
        lift = out(seg(t, drag0, drag0 + 0.2))
        subj, teacher = T[GRID[SRC[0]][SRC[1]]]
        gx, gy = mx - 70, my - 30
        shadow(c, gx, gy, COLW - 14, ROWH - 12, 10, strength=1.4 * lift, spread=18, dy=12)
        c.save()
        c.translate(gx + 100, gy + 30)
        c.rotate(-0.035 * lift)
        c.translate(-(gx + 100), -(gy + 30))
        box(c, gx, gy, COLW - 14, ROWH - 12, 10, bg="#ffffff", border=INK, lw=2)
        text(c, subj, gx + 16, gy + 30, 17, "b")
        text(c, teacher, gx + 16, gy + 51, 14, "r", SLATE5)
        c.restore()
    # toast after generating
    ta = out(seg(t, 11.55, 11.8)) * (1 - seg(t, 12.5, 12.75))
    if ta > 0:
        tx, ty = CX0 + 1290 - 420, CY0 + 82 + (1 - ta) * 10
        shadow(c, tx, ty, 420, 54, 12, strength=0.8 * ta, spread=14, dy=8)
        box(c, tx, ty, 420, 54, 12, bg=INK, alpha=ta)
        c.arc(tx + 30, ty + 27, 11, 0, 2 * math.pi)
        fill(c, "#10b981", ta)
        check(c, tx + 24.5, ty + 22, 11, lw=2.2)
        text(c, "18 sections · 32 teachers · 0 clashes", tx + 54, ty + 33, 16, "b", "#ffffff", alpha=ta)

def cell_center(r, d):
    x, y, w, h = cell_rect(r, d)
    return x + w / 2, y + h / 2

def drag_cursor(t):
    sx, sy = cell_center(*SRC)
    hx, hy = cell_center(*HOVER_RED)
    dx, dy = cell_center(*DST)
    return path_at(t, [(12.1, sx + 260, sy + 230), (12.65, sx - 20, sy + 4), (12.75, sx - 20, sy + 4),
                       (13.4, hx - 10, hy - 4), (14.2, hx - 10, hy - 4), (14.8, dx - 20, dy + 2),
                       (15.6, dx + 120, dy + 160)])

# ---------------------------------------------------------------- captions

CAPTIONS = [
    (2.3, 5.4, "1", "Add your sections, subjects and teachers once"),
    (5.6, 8.8, "2", "Write rules in plain English"),
    (8.9, 12.5, "3", "Generate the whole school, clash-free"),
    (12.6, 15.7, "4", "Drag to adjust. It shows what fits."),
]

def caption(c, t):
    for t0, t1, n, s in CAPTIONS:
        a = out(seg(t, t0, t0 + 0.35)) * (1 - seg(t, t1 - 0.3, t1))
        if a <= 0:
            continue
        y = H - 52 + (1 - a) * 14
        text(c, s, W / 2, y, 38, "pm", "#ffffff", alpha=a, align="c")

def bottom_fade(c, alpha):
    """The app fades into the black at the bottom, so captions sit on black."""
    if alpha <= 0:
        return
    g = cairo.LinearGradient(0, H - 190, 0, H - 105)
    g.add_color_stop_rgba(0, 0.035, 0.035, 0.035, 0.0)
    g.add_color_stop_rgba(1, 0.035, 0.035, 0.035, alpha)
    c.rectangle(0, H - 190, W, 85)
    c.set_source(g)
    c.fill()
    c.rectangle(0, H - 105, W, 105)
    c.set_source_rgba(0.035, 0.035, 0.035, alpha)
    c.fill()

# ---------------------------------------------------------------- frame

def background(c, t):
    c.set_source_rgb(0.035, 0.035, 0.035)
    c.paint()
    # faint drifting light, white only
    for (bx, by, r, ph) in [(320, 220, 700, 0.0), (1620, 880, 760, 1.7)]:
        ox = bx + 40 * math.sin(t * 0.35 + ph)
        oy = by + 30 * math.cos(t * 0.3 + ph)
        rg = cairo.RadialGradient(ox, oy, 0, ox, oy, r)
        rg.add_color_stop_rgba(0, 1, 1, 1, 0.055)
        rg.add_color_stop_rgba(1, 1, 1, 1, 0.0)
        c.set_source(rg)
        c.paint()

def intro(c, t):
    a = out(seg(t, 0.15, 0.7)) * (1 - seg(t, 1.9, 2.3))
    if a <= 0:
        return
    up = (1 - out(seg(t, 0.15, 0.8))) * 26
    text(c, "Timetablz", W / 2, 360 + up, 34, "pb", "#ffffff", alpha=a, align="c")
    l1 = "Your whole school's timetable."
    l2 = "Built in seconds. Zero clashes."
    a2 = out(seg(t, 0.4, 1.0)) * (1 - seg(t, 1.9, 2.3))
    text(c, l1, W / 2, 490 + up, 76, "pb", "#ffffff", alpha=a2, align="c")
    a3 = out(seg(t, 0.75, 1.3)) * (1 - seg(t, 1.9, 2.3))
    text(c, l2, W / 2, 590 + up * 1.2, 76, "pb", "#a3a3a3", alpha=a3, align="c")

def outro(c, t):
    a = out(seg(t, 16.0, 16.6))
    if a <= 0:
        return
    up = (1 - a) * 30
    text(c, "Timetablz", W / 2, 400 + up, 40, "pb", "#ffffff", alpha=a, align="c")
    text(c, "Clash-free timetables for", W / 2, 510 + up, 70, "pb", "#ffffff", alpha=a, align="c")
    text(c, "every school.", W / 2, 600 + up, 70, "pb", "#ffffff", alpha=a, align="c")
    b = back(seg(t, 16.45, 16.95))
    if b > 0:
        s = "Start free at timetablz.com"
        w = tw(c, s, 30, "pm") + 90
        x, y = (W - w) / 2, 680
        c.save()
        c.translate(W / 2, y + 38)
        sc = lerp(0.8, 1.0, b)
        c.scale(sc, sc)
        c.translate(-W / 2, -(y + 38))
        box(c, x, y, w, 76, 38, bg="#ffffff", alpha=clamp(b))
        text(c, s, W / 2, y + 49, 30, "pm", INK, alpha=clamp(b), align="c")
        c.restore()
        text(c, "14 days free · No card needed", W / 2, 810, 24, "m", "#a3a3a3", alpha=clamp(b), align="c")

CAMERA = [  # (time, zoom, focus x, focus y) - focus as a fraction of the window
    (2.0, 1.00, 0.50, 0.50), (2.9, 1.08, 0.58, 0.47), (5.3, 1.10, 0.58, 0.50),
    (5.8, 1.18, 0.56, 0.47), (8.6, 1.20, 0.56, 0.50),
    (9.1, 1.10, 0.57, 0.50), (10.3, 1.14, 0.57, 0.60), (15.1, 1.16, 0.57, 0.62), (15.6, 1.0, 0.5, 0.5),
]

def camera(t):
    if t <= CAMERA[0][0]:
        return CAMERA[0][1:]
    for a, b in zip(CAMERA, CAMERA[1:]):
        if t <= b[0]:
            k = ease(seg(t, a[0], b[0]))
            return tuple(lerp(x, y, k) for x, y in zip(a[1:], b[1:]))
    return CAMERA[-1][1:]

def window_pose(t):
    """Window entrance, a camera that frames what each scene is about, exit."""
    enter = out(seg(t, 1.95, 2.7))
    leave = ease(seg(t, 15.6, 16.2))
    s = lerp(0.9, 1.0, enter) * lerp(1.0, 0.86, leave)
    y_off = (1 - enter) * 120 + leave * 60
    alpha = enter * (1 - leave)
    zoom, fx, fy = camera(t)
    return s * zoom, y_off, alpha, fx, fy

def scene_index(t):
    if t < 5.5:
        return "setup"
    if t < 8.85:
        return "rules"
    return "timetable"

def frame(c, t):
    background(c, t)
    intro(c, t)
    s, y_off, alpha, fx, fy = window_pose(t)
    if alpha > 0.001:
        c.save()
        cx, cy = WX + WW * fx, WY + WH * fy
        c.translate(W / 2, (H - 60) / 2 + y_off)
        c.scale(s, s)
        c.translate(-cx, -cy)
        c.translate(WX, WY)
        rrect(c, -1.5, -1.5, WW + 3, WH + 3, 19.5)
        c.set_source_rgba(1, 1, 1, 0.18 * alpha)
        c.fill()
        c.push_group()
        sc = scene_index(t)
        step = {"setup": 0, "rules": 3, "timetable": 4}[sc]
        done = {"setup": {0, 1, 2} if t > 4.2 else ({0, 1} if t > 3.6 else ({0} if t > 3.0 else set())),
                "rules": {0, 1, 2}, "timetable": {0, 1, 2, 3}}[sc]
        app_chrome(c, step, done)
        # cross-fade content between scenes
        c.save()
        c.rectangle(SIDE, TOP + NAVH, WW - SIDE, WH - TOP - NAVH)
        c.clip()
        for name, fn, t0, t1 in [("setup", scene_setup, 0, 5.5), ("rules", scene_rules, 5.5, 8.85),
                                 ("timetable", scene_timetable, 8.85, 99)]:
            fa = seg(t, t0 - 0.01, t0 + 0.3) if t0 > 0 else 1.0
            fb = 1 - seg(t, t1 - 0.3, t1)
            k = clamp(min(fa, fb))
            if k <= 0:
                continue
            c.push_group()
            c.translate(0, (1 - k) * 14)
            fn(c, t)
            c.pop_group_to_source()
            c.paint_with_alpha(k)
        c.restore()
        c.pop_group_to_source()
        c.paint_with_alpha(alpha)
        # cursor (window space)
        cur = cursor_pos(t)
        if cur:
            cursor(c, cur[0], cur[1], cur[2])
        c.restore()
    bottom_fade(c, alpha)
    caption(c, t)
    outro(c, t)

def cursor_pos(t):
    if t < 6.0 or t > 15.6:
        return None
    if t < 8.85:
        # to Add, then to "Yes, that's right"
        x, y = path_at(t, [(6.0, CX0 + 900, CY0 + 600), (6.2, CX0 + 760, CY0 + 330), (7.45, CX0 + 760, CY0 + 330),
                           (7.65, CX0 + 1230, CY0 + 315), (8.25, CX0 + 1230, CY0 + 315),
                           (8.5, CX0 + 120, CY0 + 600), (8.85, CX0 + 120, CY0 + 600)])
        press = max(seg(t, 7.62, 7.72) * (1 - seg(t, 7.72, 7.9)), seg(t, 8.5, 8.58) * (1 - seg(t, 8.58, 8.75)))
        return x, y, press
    if t < 12.1:
        bx, by = CX0 + 1290 - 125, CY0 + 30
        x, y = path_at(t, [(8.85, CX0 + 700, CY0 + 560), (8.95, bx, by), (9.4, bx, by),
                           (10.0, bx - 380, by + 560), (12.1, bx - 380, by + 560)])
        press = seg(t, 8.95, 9.03) * (1 - seg(t, 9.03, 9.2))
        return x, y, press
    mx, my = drag_cursor(t)
    press = 1.0 if 12.75 <= t < 14.85 else seg(t, 12.65, 12.75) * 0
    return mx, my, 0.6 * press

# ---------------------------------------------------------------- render

def render_png(t, path):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    c = cairo.Context(s)
    c.set_antialias(cairo.ANTIALIAS_BEST)
    frame(c, t)
    s.write_to_png(path)

if ONLY:
    for t in ONLY:
        render_png(t, f"{OUT}_{t:05.2f}.png")
    sys.exit()

ff = subprocess.Popen([
    "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS),
    "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
    "-movflags", "+faststart", "-profile:v", "high", OUT,
], stdin=subprocess.PIPE)
surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
for i in range(int(DUR * FPS)):
    c = cairo.Context(surf)
    c.set_antialias(cairo.ANTIALIAS_BEST)
    c.set_operator(cairo.OPERATOR_SOURCE)
    c.set_source_rgb(1, 1, 1)
    c.paint()
    c.set_operator(cairo.OPERATOR_OVER)
    frame(c, i / FPS)
    surf.flush()
    ff.stdin.write(bytes(surf.get_data()))
ff.stdin.close()
ff.wait()
print("done", OUT)
