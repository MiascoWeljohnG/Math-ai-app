// School admin page: Weekly schedule (weekly-schedule.html). The admin puts each lesson of a subject in a week and decides how the
// school's "current week" moves; students see the result as blue / red / green / gray lesson cards (lessons.js, weekly.css).
// Needs school-admin-common.js (getHeaders, esc) and the markup of that page. The server reads the school from the account.
const wkSubject = document.getElementById("weeklySubject");
const wkBody = document.getElementById("weeklyBody");
const wkStatus = document.getElementById("weeklyStatus");
let wkState = null;   // what the server last said about the chosen subject

function wkSay(message, kind = "success") {
    wkStatus.textContent = message;
    wkStatus.className = message ? `status ${kind}` : "status";
}

async function wkCall(method, path, body) {
    const response = await fetch(`${API}/school-admin/weekly${path}`, {
        method,
        headers: { ...getHeaders(), ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
        body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detailText(data, "Something went wrong. Try again."));
    return data;
}

const wkDay = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });

async function wkLoadSubjects(keep) {
    try {
        const subjects = await wkCall("GET", "");
        document.getElementById("weeklyNoSubjects").hidden = subjects.length > 0;
        wkSubject.replaceChildren(...subjects.map(s => new Option(
            `${s.name}${s.enabled ? ` (week ${s.current_week})` : ""}`, String(s.id), false, String(s.id) === String(keep))));
        wkSubject.disabled = subjects.length === 0;
        if (subjects.length) await wkLoadSubject(wkSubject.value);
        else wkBody.hidden = true;
    } catch (error) {
        wkSay(error.message, "error");
    }
}

async function wkLoadSubject(id) {
    try {
        wkState = await wkCall("GET", `/${id}`);
        wkRender();
    } catch (error) {
        wkSay(error.message, "error");
    }
}

function wkRender() {
    const { schedule, lessons } = wkState;
    wkBody.hidden = false;

    // --- how the week moves
    const on = !!(schedule && schedule.enabled);
    document.getElementById("wkEnabled").checked = on;
    document.getElementById("wkNow").hidden = !schedule;
    const mode = schedule ? schedule.mode : "auto";
    document.getElementById(mode === "manual" ? "wkModeManual" : "wkModeAuto").checked = true;
    document.getElementById("wkStartDate").value = (schedule && schedule.start_date) || wkState.today;
    document.getElementById("wkManualWeek").value = schedule ? (schedule.current_week ?? schedule.manual_week) : 1;
    if (schedule) {
        const week = schedule.current_week;
        document.getElementById("wkNowNum").textContent = week ? `Week ${week}` : "Not started";
        document.getElementById("wkNowSub").textContent = !on ? "Paused: students unlock lessons one by one."
            : schedule.mode === "manual" ? "Staying here until you advance it."
            : week ? "Moves on by itself every 7 days." : `Starts on ${wkDay(schedule.start_date)}.`;
    }
    document.getElementById("wkPrev").disabled = !schedule || (schedule.current_week || 0) <= 0;

    // --- lessons & weeks
    document.getElementById("wkNoLessons").hidden = lessons.length > 0;
    const now = schedule && on ? schedule.current_week : null;
    const topWeek = Math.min(60, Math.max(12, (now || 0) + 2, ...lessons.map(l => (l.week_number || 0) + 2)));
    document.getElementById("wkPlanList").replaceChildren(...lessons.map(lesson => wkRow(lesson, now, topWeek)));
}

// The colour is what students see for this lesson, as far as the school can tell (green = every student finished it).
function wkPace(lesson, now) {
    if (now === null || lesson.week_number === null || lesson.week_number > now) return "closed";
    if (lesson.week_number === now) return "current";
    return lesson.behind === 0 && lesson.completed > 0 ? "done" : "behind";
}

function wkRow(lesson, now, topWeek) {
    const row = document.createElement("div");
    row.className = `plan-row pace-${wkPace(lesson, now)}`;
    const dates = lesson.week_start ? ` · ${wkDay(lesson.week_start)} – ${wkDay(lesson.week_end)}` : "";
    const options = ['<option value="">Not in the plan</option>']
        .concat(Array.from({ length: topWeek }, (_, i) => `<option value="${i + 1}"${lesson.week_number === i + 1 ? " selected" : ""}>Week ${i + 1}</option>`));
    row.innerHTML = `
        <span class="plan-title">${esc(lesson.title)}<small>${lesson.week_number ? `Week ${lesson.week_number}${esc(dates)}` : "Gray for students"}</small></span>
        <span class="plan-stat">${lesson.completed} of ${wkState.students} students finished</span>
        ${lesson.behind ? `<span class="plan-stat bad">${lesson.behind} behind</span>` : ""}
        <select class="branch-select" aria-label="Week for ${esc(lesson.title)}" data-lesson="${lesson.id}">${options.join("")}</select>`;
    return row;
}

// ---- actions (each answers with the subject's new state, which is simply drawn again)
async function wkRun(button, work, okMessage) {
    wkSay("");
    try {
        await withButtonLoading(button, async () => {
            wkState = await work();
            wkRender();
        });
        wkSay(okMessage);
        wkRefreshSubjectNames();
    } catch (error) {
        wkSay(error.message, "error");
    }
}

// the dropdown shows "(week N)" next to a subject that runs on a schedule; keep it in step with changes
async function wkRefreshSubjectNames() {
    try {
        const subjects = await wkCall("GET", "");
        for (const s of subjects) {
            const option = [...wkSubject.options].find(o => o.value === String(s.id));
            if (option) option.textContent = `${s.name}${s.enabled ? ` (week ${s.current_week})` : ""}`;
        }
    } catch { /* the names are only a convenience */ }
}

const wkId = () => wkState.subject.id;

document.getElementById("wkSave").addEventListener("click", (event) => {
    const mode = document.querySelector('input[name="wkMode"]:checked').value;
    const body = { enabled: document.getElementById("wkEnabled").checked, mode };
    if (mode === "auto") body.start_date = document.getElementById("wkStartDate").value || null;
    else body.manual_week = Number(document.getElementById("wkManualWeek").value || 0);
    wkRun(event.currentTarget, () => wkCall("PUT", `/${wkId()}/schedule`, body), "Saved. Students see the change right away.");
});

document.getElementById("wkNext").addEventListener("click", (event) =>
    wkRun(event.currentTarget, () => wkCall("POST", `/${wkId()}/week`, { action: "next" }), "Moved to the next week."));
document.getElementById("wkPrev").addEventListener("click", (event) =>
    wkRun(event.currentTarget, () => wkCall("POST", `/${wkId()}/week`, { action: "previous" }), "Moved back one week."));

document.getElementById("wkAuto").addEventListener("click", async (event) => {
    const overwrite = document.getElementById("wkOverwrite").checked;
    if (overwrite && !(await uiConfirm("This replaces the week of every lesson in this subject, including ones you set by hand. Continue?", { title: "Replace all weeks?" }))) return;
    const body = {
        per_week: Number(document.getElementById("wkPerWeek").value || 1),
        start_week: Number(document.getElementById("wkStartWeek").value || 1),
        overwrite,
    };
    wkRun(event.currentTarget, () => wkCall("POST", `/${wkId()}/auto-assign`, body), "Weeks assigned in course order.");
});

document.getElementById("wkPlanList").addEventListener("change", (event) => {
    const select = event.target.closest("select[data-lesson]");
    if (!select) return;
    const week = select.value ? Number(select.value) : null;
    wkRun(select, () => wkCall("PUT", `/${wkId()}/lessons/${select.dataset.lesson}`, { week_number: week }),
        week ? `Lesson set for week ${week}.` : "Lesson taken out of the weekly plan.");
});

wkSubject.addEventListener("change", () => { wkSay(""); wkLoadSubject(wkSubject.value); });
wkLoadSubjects();
