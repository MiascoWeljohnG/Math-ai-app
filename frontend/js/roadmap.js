// Roadmap page: reminders from teachers, then one card per subject with an ordered lesson list
// and a short study plan for the next lessons. All data comes from /learning (no AI call here).
const $ = (id) => document.getElementById(id);
const headers = { Authorization: `Bearer ${localStorage.getItem("token")}` };

async function get(path) {
    const response = await fetch(API + path, { headers });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) throw new Error("Your session expired. Please log in again.");
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong.");
    return body;
}

// Small DOM helper: el("li", {className: "x"}, "text", childNode) -- text is never parsed as HTML.
function el(tag, props = {}, ...children) {
    const node = Object.assign(document.createElement(tag), props);
    node.append(...children);
    return node;
}

// Student-facing names for the mastery levels (adaptive.py has the rules)
const LEVEL_LABEL = { struggling: "Needs review", developing: "Almost there", proficient: "Passed", mastered: "Mastered" };

// Weekly plan colours (same states as lessons.js): blue = this week's task, red = behind the class, green = completed,
// gray = the school has not opened it yet.
// Inline SVG icons (drawn with currentColor, so they follow each state's colour); trusted constants, never user text.
const svgIcon = (inner) => `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${inner}</svg>`;
const PACE_ICON = {
    current: svgIcon('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
    behind:  svgIcon('<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'),
    done:    svgIcon('<path d="M20 6 9 17l-5-5"/>'),
    closed:  svgIcon('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
};
const PACE_LABEL = { current: "This week", behind: "Behind", done: "Completed", closed: "Not open yet" };
function paceIcon(pace) { const span = el("span", { className: "pace-ico" }); span.innerHTML = PACE_ICON[pace]; return span; }

// Study plan icons (inline SVG, currentColor); trusted constants, never user text.
const ICON_CLOCK = svgIcon('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>');
const ICON_BOLT = svgIcon('<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>');
const ICON_TUNE = svgIcon('<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>');
const ICON_PLAN = svgIcon('<path d="M9 11l3 3 8-8"/><path d="M20 12v6a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h8"/>');
function spIcon(svg, className) { const span = el("span", { className }); span.innerHTML = svg; return span; }
function spTag(kind, text, svg) { const tag = el("span", { className: `sp-tag ${kind}` }); tag.innerHTML = svg; tag.append(text); return tag; }
const dayText = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric" });
function paceNote(lesson) {
    if (lesson.week_number == null) return "Not in your school's weekly plan yet";
    const note = [`Week ${lesson.week_number}`];
    if (lesson.pace === "behind") note.push(lesson.week_end ? `was due ${dayText(lesson.week_end)}` : "you're behind the class");
    else if (lesson.pace === "closed") note.push(lesson.week_start ? `opens ${dayText(lesson.week_start)}` : "opens later");
    else if (lesson.week_start) note.push(`${dayText(lesson.week_start)} – ${dayText(lesson.week_end)}`);
    return note.join(" · ");
}
function paceLegend() {
    return el("div", { className: "pace-legend" },
        ...[["current", "This week"], ["behind", "Behind"], ["done", "Completed"], ["closed", "Not open yet"]].map(([pace, text]) =>
            el("span", { className: `pace-${pace}` }, el("i"), text)));
}

function renderReminders(reminders) {
    $("reminders").hidden = !reminders.length;
    $("reminderList").replaceChildren(...reminders.map(r => el("li", { className: "reminder" + (r.overdue ? " overdue" : "") },
        el("div", {}, r.message),
        el("div", { className: "meta" },
            `From ${r.created_by}` + (r.due_date ? ` · due ${r.due_date}${r.overdue ? " (overdue)" : ""}` : "")),
    )));
}

function renderSubject(subject) {
    const percent = el("span");
    percent.style.width = `${subject.percent}%`;
    const lessons = subject.lessons.map((lesson, i) => {
        const note = lesson.best_percent == null ? "" : `best ${lesson.best_percent}%`;
        const chip = lesson.status === "next" ? el("span", { className: "chip next" }, "Up next")
            : note ? el("span", { className: "chip" }, note) : "";
        // The adaptive part: how this student is doing on the lesson, and the practice set that fits
        const levelChip = LEVEL_LABEL[lesson.level] ? el("span", { className: `chip level-${lesson.level}` }, LEVEL_LABEL[lesson.level]) : "";
        const practice = lesson.practice ? el("a", {
            className: "practice-link", href: `practice.html?subject=${subject.subject_id}&lesson=${lesson.id}`,
        }, lesson.practice === "harder" ? "Challenge set" : "Easy practice") : "";
        if (lesson.pace) {   // a school-scheduled subject: a coloured card instead of a plain row
            const closed = lesson.pace === "closed";
            return el("li", { className: `lesson paced pace-${lesson.pace}` },
                el("span", { className: "num" }, lesson.pace === "done" || closed ? paceIcon(lesson.pace) : String(i + 1)),
                el("span", { className: "lesson-main" },
                    closed ? el("span", { className: "closed" }, lesson.title)
                        : el("a", { href: `lessons.html?subject=${subject.subject_id}&lesson=${lesson.id}` }, lesson.title),
                    el("span", { className: "lesson-sub" }, paceNote(lesson))),
                el("span", { className: `pace-pill pace-${lesson.pace}` }, paceIcon(lesson.pace), PACE_LABEL[lesson.pace]),
                closed ? "" : levelChip, closed ? "" : practice,
            );
        }
        return el("li", { className: `lesson ${lesson.status}` },
            el("span", { className: "num" }, lesson.status === "done" ? "✓" : String(i + 1)),
            el("a", { href: `lessons.html?subject=${subject.subject_id}&lesson=${lesson.id}` }, lesson.title),
            chip, levelChip, practice,
        );
    });
    const plan = subject.study_plan.map((item, n) => {
        const adjusted = !item.fast_track && (item.level === "struggling" || item.level === "developing");
        const tags = el("div", { className: "sp-tags" }, spTag("time", `${item.minutes} min`, ICON_CLOCK));
        if (item.fast_track) tags.append(spTag("fast", "Fast track", ICON_BOLT));
        else if (adjusted) tags.append(spTag("adjusted", "Adjusted for you", ICON_TUNE));
        return el("li", { className: `sp-card${item.fast_track ? " fast" : adjusted ? " adjusted" : ""}` },
            el("div", { className: "sp-card-head" }, el("h4", { className: "sp-title" }, item.title), tags),
            el("ol", { className: "sp-steps" }, ...item.steps.map((step, i) => el("li", { className: "sp-step" },
                el("span", { className: "sp-num" }, String(i + 1)),
                el("div", { className: "sp-body" },
                    step.href ? el("a", { className: "sp-text", href: step.href }, step.text) : el("span", { className: "sp-text" }, step.text),
                    el("span", { className: "sp-min" }, `~${step.minutes} min`))))));
    });
    const planTotal = subject.study_plan.reduce((sum, item) => sum + (item.minutes || 0), 0);
    const planBlock = plan.length ? el("section", { className: "sp" },
        el("div", { className: "sp-head" },
            spIcon(ICON_PLAN, "sp-head-ico"),
            el("div", {}, el("h3", {}, "Your study plan"),
                el("p", {}, `${plan.length} lesson${plan.length === 1 ? "" : "s"} · about ${planTotal} min in total`))),
        el("ol", { className: "sp-list" }, ...plan)) : "";
    return el("section", { className: "card" },
        el("h2", {}, subject.branch + (subject.is_personal ? " (personal)" : "")),
        el("p", { className: "muted" }, `${subject.completed} of ${subject.total} lessons done · ${subject.percent}%`),
        el("div", { className: "bar" }, percent),
        subject.total ? el("h3", {}, subject.weekly ? `Weekly plan${subject.current_week ? ` · your school is on week ${subject.current_week}` : " · not started yet"}` : "Lessons in order") : el("p", { className: "muted" }, "No lessons yet."),
        subject.weekly && subject.total ? paceLegend() : "",
        el("ol", { className: "plain" }, ...lessons),
        planBlock,
        subject.total && !plan.length
            ? el("p", { className: "muted" }, subject.weekly && lessons.some(li => li.classList.contains("pace-closed")) && subject.completed < subject.total
                ? "You're all caught up for now. New lessons appear when your school opens them."
                : "Every lesson here is done. Nice work!") : "",
    );
}

(async function init() {
    try {
        const [{ subjects }, reminders] = await Promise.all([get("/learning/roadmap"), get("/learning/reminders")]);
        renderReminders(reminders);
        $("status").hidden = true;
        $("roadmap").replaceChildren(...subjects.map(renderSubject));
    } catch (error) {
        $("status").className = "muted error";
        $("status").textContent = error.message;
    }
})();
