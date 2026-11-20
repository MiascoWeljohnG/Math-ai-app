// School admin page: Weekly schedule (weekly-schedule.html). The admin puts each lesson of a subject in a week and decides how the
// school's "current week" moves; students see the result as blue / red / green / gray lesson cards (lessons.js, weekly.css).
// Needs school-admin-common.js (getHeaders, esc) and the markup of that page. The server reads the school from the account.
const wkSubject = document.getElementById("weeklySubject");
const wkBody = document.getElementById("weeklyBody");
const wkStatus = document.getElementById("weeklyStatus");
let wkState = null;   // what the server last said about the chosen subject
const wkPending = {}; // lesson id -> the week picked in its dropdown but not saved yet (null = "Not in the plan")

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
    const shown = lesson.id in wkPending ? wkPending[lesson.id] : lesson.week_number;
    const options = ['<option value="">Not in the plan</option>']
        .concat(Array.from({ length: topWeek }, (_, i) => `<option value="${i + 1}"${shown === i + 1 ? " selected" : ""}>Week ${i + 1}</option>`));
    row.innerHTML = `
        <span class="plan-title">${esc(lesson.title)}<small>${lesson.week_number ? `Week ${lesson.week_number}${esc(dates)}` : "Gray for students"}</small></span>
        <span class="plan-stat">${lesson.completed} of ${wkState.students} students finished</span>
        ${lesson.behind ? `<span class="plan-stat bad">${lesson.behind} behind</span>` : ""}
        <select class="branch-select" aria-label="Week for ${esc(lesson.title)}" data-lesson="${lesson.id}">${options.join("")}</select>
        <div class="plan-actions" hidden>
            <span class="plan-pending"></span>
            <button class="btn btn-secondary btn-sm" type="button" data-act="cancel" data-lesson="${lesson.id}">Cancel</button>
            <button class="btn btn-primary btn-sm" type="button" data-act="save" data-lesson="${lesson.id}">Save</button>
        </div>`;
    wkShowPending(row, lesson);
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

const wkWeekText = (week) => (week ? `Week ${week}` : "Not in the plan");

// Show or hide the Save / Cancel bar under a row, depending on whether its dropdown differs from what is saved.
function wkShowPending(row, lesson) {
    const changed = lesson.id in wkPending;
    row.classList.toggle("changed", changed);
    const bar = row.querySelector(".plan-actions");
    bar.hidden = !changed;
    if (changed) bar.querySelector(".plan-pending").textContent = `${wkWeekText(lesson.week_number)} → ${wkWeekText(wkPending[lesson.id])}`;
}

// What the students will see once the change is saved, in plain words (for the confirmation).
function wkEffect(week) {
    const sc = wkState.schedule;
    if (!week) return "Students will see it as gray and won't be able to open it.";
    if (!sc || !sc.enabled) return "Weekly pacing is off for this subject, so it won't affect students until you turn it on.";
    const now = sc.current_week || 0;
    if (week === now) return "It becomes this week's task: blue for students who haven't finished it.";
    if (week < now) return "That week has already passed: students who haven't finished it will see it as red (behind).";
    return "That week hasn't started: it stays gray for students until then.";
}

document.getElementById("wkPlanList").addEventListener("change", (event) => {
    const select = event.target.closest("select[data-lesson]");
    if (!select) return;
    const lesson = wkState.lessons.find(item => String(item.id) === select.dataset.lesson);
    const week = select.value ? Number(select.value) : null;
    if (week === lesson.week_number) delete wkPending[lesson.id];   // picked the saved value again: nothing to save
    else wkPending[lesson.id] = week;
    wkShowPending(select.closest(".plan-row"), lesson);
    wkSay("");
});

document.getElementById("wkPlanList").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-act]");
    if (!button) return;
    const lesson = wkState.lessons.find(item => String(item.id) === button.dataset.lesson);
    if (!lesson || !(lesson.id in wkPending)) return;
    const week = wkPending[lesson.id];

    if (button.dataset.act === "cancel") {
        const discard = await uiConfirm(
            `Discard the change to "${lesson.title}"?\n\nIt stays as it is now: ${wkWeekText(lesson.week_number)}.`,
            { title: "Discard change?", okText: "Discard", cancelText: "Keep editing", danger: true });
        if (!discard) return;
        delete wkPending[lesson.id];
        wkRender();   // draws the dropdown back at the saved week
        wkSay("Change discarded.");
        return;
    }

    const confirmed = await uiConfirm(
        `${week ? `Set "${lesson.title}" as the task for week ${week}?` : `Take "${lesson.title}" out of the weekly plan?`}\n\n${wkEffect(week)}`,
        { title: "Save this change?", okText: "Save", cancelText: "Cancel" });
    if (!confirmed) return;
    wkRun(button, async () => {
        const state = await wkCall("PUT", `/${wkId()}/lessons/${lesson.id}`, { week_number: week });
        delete wkPending[lesson.id];
        return state;
    }, week ? `"${lesson.title}" is now the task for week ${week}.` : `"${lesson.title}" was taken out of the weekly plan.`);
});

wkSubject.addEventListener("change", () => {
    for (const id of Object.keys(wkPending)) delete wkPending[id];
    wkSay("");
    wkLoadSubject(wkSubject.value);
});
wkLoadSubjects();
