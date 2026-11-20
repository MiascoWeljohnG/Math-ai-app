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
const PACE_LABEL = { current: "● This week", behind: "! Behind", done: "✓ Completed", closed: "🔒 Not open yet" };
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
                el("span", { className: "num" }, lesson.pace === "done" ? "✓" : closed ? "🔒" : String(i + 1)),
                el("span", { className: "lesson-main" },
                    closed ? el("span", { className: "closed" }, lesson.title)
                        : el("a", { href: `lessons.html?subject=${subject.subject_id}&lesson=${lesson.id}` }, lesson.title),
                    el("span", { className: "lesson-sub" }, paceNote(lesson))),
                el("span", { className: `pace-pill pace-${lesson.pace}` }, PACE_LABEL[lesson.pace]),
                closed ? "" : levelChip, closed ? "" : practice,
            );
        }
        return el("li", { className: `lesson ${lesson.status}` },
            el("span", { className: "num" }, lesson.status === "done" ? "✓" : String(i + 1)),
            el("a", { href: `lessons.html?subject=${subject.subject_id}&lesson=${lesson.id}` }, lesson.title),
            chip, levelChip, practice,
        );
    });
    const plan = subject.study_plan.map(item => el("div", { className: "plan-lesson" },
        el("strong", {}, `${item.title} · about ${item.minutes} min`
            + (item.fast_track ? " · fast track" : item.level === "struggling" || item.level === "developing" ? " · adjusted for you" : "")),
        el("ul", {}, ...item.steps.map(step => el("li", {},
            step.href ? el("a", { href: step.href }, step.text) : step.text, ` (~${step.minutes} min)`))),
    ));
    return el("section", { className: "card" },
        el("h2", {}, subject.branch + (subject.is_personal ? " (personal)" : "")),
        el("p", { className: "muted" }, `${subject.completed} of ${subject.total} lessons done · ${subject.percent}%`),
        el("div", { className: "bar" }, percent),
        subject.total ? el("h3", {}, subject.weekly ? `Weekly plan${subject.current_week ? ` · your school is on week ${subject.current_week}` : " · not started yet"}` : "Lessons in order") : el("p", { className: "muted" }, "No lessons yet."),
        subject.weekly && subject.total ? paceLegend() : "",
        el("ol", { className: "plain" }, ...lessons),
        plan.length ? el("h3", {}, "Your study plan") : "",
        ...plan,
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
