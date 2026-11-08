// Teacher overview: the four tiles at the top of teacher.html (styles: css/overview.css, helpers: overview.js).
// The numbers come from GET /teacher/overview. Files are only this teacher's own; lessons and students are the school's.
//   1. Files you uploaded - total, with a bar chart of PDF vs DOCX
//   2. Lessons to approve - AI drafts waiting for a teacher to approve them
//   3. Lessons live       - published lessons (ring = share of all lessons that are published)
//   4. Active students    - students who can sign in (ring = share who were seen in the last 7 days)
let teacherOverviewShown = false;   // the first paint animates; later refreshes only update the numbers
let teacherOverviewTimer = null;

function ovPlural(n, word) { return `${n} ${word}${n === 1 ? "" : "s"}`; }
function ovPercent(part, whole) { return whole ? Math.round(part * 100 / whole) : 0; }
function ovJoin(parts) { return parts.join("\u00A0· "); }   // the dot sticks to the word before it
function ovAgo(iso) {
    const seconds = Math.max(0, (Date.now() - new Date(iso)) / 1000);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
    return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function ovValue(id, value) {
    const el = document.getElementById(id);
    if (!teacherOverviewShown) countUp(el, value, n => String(n));
    else el.textContent = String(value);
}

function ovGauge(id, percent, hint) {
    const gauge = document.getElementById(id);
    if (hint) gauge.title = hint;
    if (!teacherOverviewShown) { setGauge(id, percent); return; }
    const pct = Math.max(0, Math.min(100, percent));
    gauge.setAttribute("aria-label", `${pct} percent`);
    gauge.querySelector(".g-fill").style.strokeDashoffset = String(100 - pct);
    gauge.querySelector(".g-pct").textContent = `${pct}%`;
}

// Bars are scaled to the taller of the two, so an empty tile shows two short stubs instead of nothing.
const OV_BAR_MAX_PX = 44;
function ovBars(pdf, docx) {
    const tallest = Math.max(pdf, docx, 1);
    for (const [bar, count, n] of [["ovPdfBar", "ovPdfCount", pdf], ["ovDocxBar", "ovDocxCount", docx]]) {
        const height = n ? Math.max(8, Math.round(n * OV_BAR_MAX_PX / tallest)) : 4;
        const fill = document.getElementById(bar);
        if (!teacherOverviewShown) requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.height = `${height}px`; }));
        else fill.style.height = `${height}px`;
        document.getElementById(count).textContent = String(n);
    }
    document.getElementById("ovFilesBars").setAttribute("aria-label", `${ovPlural(pdf, "PDF")}, ${ovPlural(docx, "DOCX file")}`);
}

function paintTeacherOverview(o) {
    const set = (id, text) => { document.getElementById(id).textContent = text; };
    const { files, lessons, students } = o;

    ovValue("ovFiles", files.total);
    ovBars(files.pdf, files.docx);
    if (!files.total) set("ovFilesSub", "You haven't uploaded any files yet");
    else {
        const parts = [`${files.this_week} added this week`];
        if (files.other) parts.push(`${files.other} other type${files.other === 1 ? "" : "s"}`);
        if (files.latest) parts.push(`latest ${ovAgo(files.latest)}`);
        set("ovFilesSub", ovJoin(parts));
    }

    ovValue("ovDrafts", lessons.drafts);
    if (!lessons.drafts) set("ovDraftsSub", "Nothing is waiting. You're all caught up.");
    else {
        const parts = [`${lessons.my_drafts} written by you`];
        if (lessons.oldest_draft_days >= 1) parts.push(`oldest waiting ${ovPlural(lessons.oldest_draft_days, "day")}`);
        set("ovDraftsSub", ovJoin(parts));
    }

    const allLessons = lessons.published + lessons.drafts;
    ovValue("ovLive", lessons.published);
    ovGauge("ovLiveGauge", ovPercent(lessons.published, allLessons),
        `${lessons.published} of ${ovPlural(allLessons, "lesson")} are published; the rest are drafts`);
    set("ovLiveSub", ovJoin([ovPlural(lessons.subjects, "subject"), `${lessons.my_published} written by you`]));

    ovValue("ovStudents", students.active);
    ovGauge("ovStudentsGauge", ovPercent(students.week, students.active),
        `${students.week} of ${ovPlural(students.active, "student")} were active in the last 7 days`);
    set("ovStudentsSub", students.active
        ? ovJoin([`${students.online} online now`, `${students.today} seen in 24 h`])
        : "No active students yet");

    teacherOverviewShown = true;
}

async function fetchTeacherOverview() {
    try {
        const res = await fetch(`${API}/teacher/overview`, { headers: getHeaders() });
        if (!res.ok) throw new Error("overview failed");
        paintTeacherOverview(await res.json());
    } catch {
        if (!teacherOverviewShown) {   // a bonus panel: the page works without it
            document.getElementById("overviewGrid").hidden = true;
            document.querySelector(".ov-title").hidden = true;
        }                              // after the first success a failed refresh keeps the last numbers
    }
}

// Called by teacher.js after the file list or draft list reloads. A short delay merges bursts into one request.
function loadTeacherOverview() {
    clearTimeout(teacherOverviewTimer);
    teacherOverviewTimer = setTimeout(fetchTeacherOverview, 400);
}

loadTeacherOverview();
setInterval(() => { if (document.visibilityState === "visible") loadTeacherOverview(); }, 60000);
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") loadTeacherOverview(); });
