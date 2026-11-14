// Quiz page: ?subject=<id>&lesson=<id>
// Flow: load quiz (or have the AI write it, with a progress bar) -> start card -> timed quiz with
// tab-switch violations -> the server grades it -> results with a link to the next lesson.
// Answers never reach the browser until the quiz is submitted.

const params = new URLSearchParams(window.location.search);
const subjectId = params.get("subject");
const lessonId = params.get("lesson");
const base = `${API}/subjects/${subjectId}/lessons/${lessonId}/quiz`;
const lessonUrl = (id) => `lessons.html?subject=${subjectId}&lesson=${id}`;
const $ = (id) => document.getElementById(id);

const SCREENS = ["screenLoading", "screenStart", "screenQuiz", "screenResult", "screenLocked", "screenError"];
const show = (name) => SCREENS.forEach(id => { $(id).hidden = id !== name; });
const pad = (n) => String(n).padStart(2, "0");
const clock = (seconds) => `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`;
const describeTime = (s) => (s % 60 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 60)} min`);
// The AI sometimes marks emphasis as **bold**. Show it bold, built from DOM nodes (never innerHTML).
function richText(element, text) {
    const parts = String(text).split("**");
    if (parts.length % 2 === 0) { element.textContent = text; return; }   // unbalanced ** : show as typed
    element.replaceChildren(...parts.map((part, i) => {
        if (i % 2 === 0) return document.createTextNode(part);
        const strong = document.createElement("strong");
        strong.textContent = part;
        return strong;
    }));
}
const typeset = (...elements) => { if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise(elements).catch(() => {}); };

let meta = null;          // what the server sent: names, lesson number, next lesson, quiz
let quiz = null;          // meta.quiz: { questions, difficulty, time_limit, max_violations }
let phase = "idle";       // idle -> quiz -> done
let index = 0;
let answers = {};         // question id -> choice index | true/false | typed text
let violations = 0;
let deadline = 0;
let startedAt = 0;        // when the timer started, to report how long the student took
let elapsed = 0;          // seconds the student took, set when they submit
let timerId = 0;
let warnPending = false;  // a tab switch happened; show the warning when they come back
let pendingKind = "tab";   // what caused the pending violation: "tab" (left/minimized) or "resize"
let resultsById = {};      // question id -> { correct, correct_answer, explanation } from the last submit
let away = false;         // the student is currently away from the quiz (one absence counts once)
let smallWindow = false;  // true while the window is too small, so one shrink counts only once
let retryAction = null;

async function api(path, options = {}) {
    const response = await fetch(base + path, {
        ...options,
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}`, ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) throw new Error("Your session expired. Please log in again.");
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.");
    return body;
}

function fail(message, retry) {
    retryAction = retry;
    $("errorText").textContent = message;
    $("retryBtn").hidden = !retry;
    show("screenError");
}
$("retryBtn").addEventListener("click", () => retryAction && retryAction());

// ---------------------------------------------------------------- generating (progress bar)
// The model answers in one go, so there is no real progress to read. The bar creeps forward in
// random steps, slows down, parks at 92% and only reaches 100% when the quiz actually arrives.
function startProgress() {
    let percent = 0;
    const stages = [[0, "Reading the lesson"], [25, "Writing the questions"], [50, "Mixing the question types"],
                    [70, "Setting the difficulty"], [85, "Checking the answers"]];
    const paint = () => {
        const value = Math.round(percent);
        $("genFill").style.width = `${value}%`;
        $("genPct").textContent = `${value}%`;
        $("genTrack").setAttribute("aria-valuenow", value);
        $("loadingStatus").textContent = stages.filter(([from]) => percent >= from).pop()[1];
    };
    paint();
    const id = setInterval(() => { percent = Math.min(92, percent + Math.random() * (percent < 60 ? 8 : 2.5)); paint(); }, 700);
    return { finish() { clearInterval(id); percent = 100; paint(); }, stop() { clearInterval(id); } };
}

async function generate() {
    show("screenLoading");
    const progress = startProgress();
    try {
        meta = await api("/generate", { method: "POST" });
        quiz = meta.quiz;
        if (meta.lock) { progress.stop(); return showLocked(); }
        progress.finish();
        await new Promise(resolve => setTimeout(resolve, 500));   // let the bar visibly hit 100%
        showStart();
    } catch (error) {
        progress.stop();
        fail(error.message, generate);
    }
}

// ---------------------------------------------------------------- start card
function showStart() {
    $("startTitle").textContent = `Quiz #${meta.lesson_number}`;
    $("startSubtitle").textContent = `${meta.subject}: ${meta.lesson_title}`;
    typeset($("startSubtitle"));
    $("factCount").textContent = `${quiz.questions.length} questions`;
    $("factDifficulty").textContent = `Level ${quiz.difficulty} of 5, set by the AI for this topic`;
    $("factTime").textContent = describeTime(quiz.time_limit);
    $("factPass").textContent = `${quiz.pass_percent}% or higher to move on to the next lesson`;
    $("factViolations").textContent =
        `Switching tabs or windows, minimizing the browser or shrinking the window counts as a violation. At ${quiz.max_violations}, the quiz is terminated and submitted.`;
    $("prepMaxViolations").textContent = quiz.max_violations;
    $("bannerMaxViolations").textContent = quiz.max_violations;
    $("regenBtn").hidden = !meta.can_regenerate;
    $("retakeNote").hidden = !meta.retake_approved;
    show("screenStart");
}
$("startBtn").addEventListener("click", startQuiz);
$("regenBtn").addEventListener("click", async () => {
    if (await uiConfirm("Replace this lesson's quiz with a newly written one?", { title: "Regenerate quiz", okText: "Replace" })) generate();
});

// ---------------------------------------------------------------- the quiz
function startQuiz() {
    if (isWindowTooSmall()) {
        uiAlert("Your browser window is too small. Please maximize it (use the full screen) and press Start again.", { title: "Maximize your window" });
        return;
    }
    smallWindow = false;
    away = false;
    phase = "quiz";
    index = 0;
    answers = {};
    violations = 0;
    warnPending = false;
    startedAt = Date.now();
    deadline = Date.now() + quiz.time_limit * 1000;
    $("panelTitle").textContent = `QUIZ #${meta.lesson_number}`;
    $("panelSubject").textContent = meta.subject;
    $("panelSubject").title = meta.subject;
    $("panelDifficulty").textContent = `Difficulty level ${quiz.difficulty}`;
    renderViolations();
    renderQuestion();
    tick();
    timerId = setInterval(tick, 250);
    show("screenQuiz");
}

// Counts down to a fixed deadline instead of subtracting 1 per tick: browsers slow timers in
// background tabs, and this way the clock stays right when the student comes back.
function tick() {
    const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    $("timeLeft").textContent = clock(left);
    $("timeLeft").classList.toggle("low", left <= 30);
    if (left === 0) submit("time");
}

const renderViolations = () => { $("violationCount").textContent = `${violations} / ${quiz.max_violations}`; };

const LABELS = { mcq: "Choose the best answer:", tf: "True or false:", id: "Identification:", num: "Type the exact number:" };

function renderQuestion() {
    const q = quiz.questions[index];
    const total = quiz.questions.length;
    $("qLabel").textContent = LABELS[q.type] || "";
    richText($("qText"), q.question);
    $("qAnswer").replaceChildren(buildAnswer(q));
    $("panelProgressText").textContent = `Question ${index + 1} / ${total}`;
    $("panelProgressFill").style.width = `${((index + 1) * 100) / total}%`;
    document.querySelectorAll(".js-back").forEach(button => { button.disabled = index === 0; });
    document.querySelectorAll(".js-next").forEach(button => { button.textContent = index === total - 1 ? "Submit" : "Next"; });
    typeset($("qText"), $("qAnswer"));
}

function buildAnswer(q) {
    if (q.type === "id" || q.type === "num") {
        const wrap = document.createElement("div");
        wrap.className = "answer-wrap";
        const input = document.createElement("input");
        input.type = "text";
        input.maxLength = 60;
        input.autocomplete = "off";
        input.spellcheck = false;
        input.value = answers[q.id] ?? "";
        input.placeholder = q.type === "num" ? "Type the exact number" : "Type your answer";
        input.setAttribute("aria-label", input.placeholder);
        input.addEventListener("input", () => {
            const text = input.value.trim();
            if (text) answers[q.id] = text; else delete answers[q.id];
        });
        input.addEventListener("keydown", (event) => { if (event.key === "Enter") go(1); });
        const hint = document.createElement("small");
        hint.textContent = q.type === "num"
            ? "Exact value only, for example 12, -3.5 or 3/4."
            : "Capital letters and spacing don't matter.";
        wrap.append(input, hint);
        return wrap;
    }

    const choices = q.type === "tf" ? [["True", true], ["False", false]] : q.choices.map((text, i) => [text, i]);
    const grid = document.createElement("div");
    grid.className = "options";
    const labels = choices.map(([text, value], i) => {
        const label = document.createElement("label");
        label.className = "opt";
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = `q${q.id}`;
        radio.checked = answers[q.id] === value;
        radio.addEventListener("change", () => {
            answers[q.id] = value;
            labels.forEach(item => item.classList.toggle("selected", item === label));
        });
        const dot = document.createElement("span");
        dot.className = "dot";
        const words = document.createElement("span");
        richText(words, q.type === "mcq" ? `${"ABCD"[i]}. ${text}` : text);
        label.classList.toggle("selected", radio.checked);
        label.append(radio, dot, words);
        return label;
    });
    grid.append(...labels);
    return grid;
}

function go(step) {
    if (phase !== "quiz") return;
    const last = quiz.questions.length - 1;
    if (step > 0 && index === last) return confirmSubmit();
    index = Math.min(last, Math.max(0, index + step));
    renderQuestion();
}
document.querySelectorAll(".js-back").forEach(button => button.addEventListener("click", () => go(-1)));
document.querySelectorAll(".js-next").forEach(button => button.addEventListener("click", () => go(1)));

// ---------------------------------------------------------------- violations
// Three things count: leaving the tab, minimizing the browser, or shrinking the window.
const WARN_TEXT = {
    tab: "Leaving this tab or minimizing the browser during the quiz is not allowed.",
    window: "Switching to another window or app during the quiz is not allowed.",
    resize: "Shrinking or resizing the browser window during the quiz is not allowed. Please maximize it again.",
};

function showWarning(kind) {
    const left = quiz.max_violations - violations;
    $("warnCount").textContent = `${violations} / ${quiz.max_violations}`;
    $("warnText").textContent = `${WARN_TEXT[kind]} ${left} more and the quiz will be terminated and submitted automatically.`;
    if (!$("warnModal").open) $("warnModal").showModal();
}

// Leaving the quiz: another tab, minimizing, or another window/app taking focus (even one that only
// covers part of the quiz, which the browser does not report as "hidden"). One absence counts once.
function leave(kind) {
    if (phase !== "quiz" || away) return;
    away = true;
    violations++;
    pendingKind = kind;
    warnPending = true;        // the popup can only be seen once they are back
    renderViolations();
    if (violations >= quiz.max_violations) submit("violations");   // no need to wait for them to return
}
function comeBack() {
    if (!away) return;
    away = false;
    if (phase !== "quiz" || !warnPending) return;
    warnPending = false;
    showWarning(pendingKind);
}

document.addEventListener("visibilitychange", () => {
    if (document.hidden) leave("tab");
    else if (document.hasFocus()) comeBack();
});
// Short delay so a quick focus flicker (or a tab switch, already reported above) is not double counted.
window.addEventListener("blur", () => {
    setTimeout(() => { if (!document.hasFocus()) leave(document.hidden ? "tab" : "window"); }, 250);
});
window.addEventListener("focus", comeBack);

// Small window: compared with the screen, so a half-screen, split-screen or restored (un-maximized) window is caught.
// On phones/tablets only the width is checked, because the on-screen keyboard changes the height.
function isWindowTooSmall() {
    const touch = window.matchMedia("(pointer: coarse)").matches;
    const availW = screen.availWidth || screen.width, availH = screen.availHeight || screen.height;
    const w = window.outerWidth || window.innerWidth, h = window.outerHeight || window.innerHeight;
    if (w < availW * 0.8) return true;
    return !touch && h < availH * 0.8;
}

let resizeTimer = 0;
window.addEventListener("resize", () => {
    if (phase !== "quiz") return;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
        if (phase !== "quiz" || document.hidden) return;   // minimizing is already counted above
        if (!isWindowTooSmall()) { smallWindow = false; return; }
        if (smallWindow) return;                           // still the same shrink, do not count it twice
        smallWindow = true;
        violations++;
        renderViolations();
        if (violations >= quiz.max_violations) return submit("violations");
        showWarning("resize");
    }, 400);
});
$("warnOk").addEventListener("click", () => $("warnModal").close());

// A refresh or a click on the menu would lose the attempt, so ask first.
window.addEventListener("beforeunload", (event) => {
    if (phase === "quiz") { event.preventDefault(); event.returnValue = ""; }
});

// ---------------------------------------------------------------- submit + results
function confirmSubmit() {
    const blank = quiz.questions.filter(q => !(q.id in answers)).length;
    if (!blank) return submit("manual");
    $("confirmText").textContent = `You left ${blank} question${blank === 1 ? "" : "s"} blank. Submit anyway?`;
    $("confirmModal").showModal();
}
$("confirmCancel").addEventListener("click", () => $("confirmModal").close());
$("confirmOk").addEventListener("click", () => { $("confirmModal").close(); submit("manual"); });

function submit(reason) {
    if (phase !== "quiz") return;
    phase = "done";
    clearInterval(timerId);
    elapsed = Math.round((Date.now() - startedAt) / 1000);
    ["warnModal", "confirmModal"].forEach(id => { if ($(id).open) $(id).close(); });
    sendAnswers(reason);
}

async function sendAnswers(reason) {
    try {
        const result = await api("/submit", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ answers, seconds: elapsed, violations }),
        });
        showResult(result, reason);
    } catch (error) {
        fail(error.message, () => sendAnswers(reason));   // answers are still in memory
    }
}

function givenText(q) {
    if (!(q.id in answers)) return "No answer";
    const given = answers[q.id];
    if (q.type === "mcq") return `${"ABCD"[given]}. ${q.choices[given]}`;
    if (q.type === "tf") return given ? "True" : "False";
    return given;
}

function showResult(result, reason) {
    $("resultScore").textContent = `${result.score} / ${result.total}`;
    $("resultSub").textContent =
        `${Math.round((result.score * 100) / result.total)}% correct · ${meta.subject}: ${meta.lesson_title}`;
    typeset($("resultSub"));
    const notice = $("resultNotice");
    notice.hidden = reason === "manual";
    notice.textContent = reason === "time"
        ? "Time ran out, so your answers were submitted automatically."
        : `You reached ${quiz.max_violations} violations, so the quiz ended and your answers were submitted automatically.`
          + (result.lock ? " Your teacher has been told." : "");
    if (result.lock) renderLock($("resultLockBox"), result.lock);
    else $("resultLockBox").hidden = true;

    // Passing (80%+) unlocks the next lesson. Below that, the student goes back to the lesson and retries.
    const banner = $("resultBanner");
    banner.className = `banner ${result.passed ? "pass" : "fail"}`;
    banner.textContent = result.passed
        ? `Passed! You scored ${result.pass_percent}% or higher.`
        : result.lock
            ? `You need ${result.pass_percent}% or higher to move on. Review the lesson while you wait for your teacher.`
            : `You need ${result.pass_percent}% or higher to move on. Review the lesson, then take the quiz again.`;
    $("nextLessonBtn").hidden = !(result.passed && meta.next_lesson_id);
    $("backToLessonBtn").textContent = result.passed ? "Back to the lesson" : "Review the lesson";
    $("backToLessonBtn").classList.toggle("primary", !result.passed);

    const byId = Object.fromEntries(result.results.map(item => [item.id, item]));
    resultsById = byId;
    $("review").replaceChildren(...quiz.questions.map((q, i) => {
        const outcome = byId[q.id];
        const item = document.createElement("div");
        item.className = `review-item ${outcome.correct ? "ok" : "bad"}`;
        const lines = [`${i + 1}. ${q.question}`, `Your answer: ${givenText(q)}`];
        if (!outcome.correct) lines.push(`Correct answer: ${outcome.correct_answer}`);
        if (outcome.explanation) lines.push(outcome.explanation);
        item.append(...lines.map((text, n) => {
            const line = document.createElement("p");
            richText(line, text);
            if (n === 0) line.style.fontWeight = "700";
            if (n === lines.length - 1 && outcome.explanation) line.className = "why";
            return line;
        }));
        return item;
    }));
    $("resultTime").hidden = false;
    $("resultTime").textContent = `Time taken: ${clock(elapsed)}`;
    show("screenResult");
    window.scrollTo(0, 0);
    typeset($("review"));
    loadPracticeLink(result.recorded);
    $("breakdown").hidden = true;
    $("review").hidden = false;   // shown again on every result; hidden only once the step-by-step cards replace it
    if (result.recorded && !result.passed) loadBreakdown();   // a failed attempt gets the steps re-taught
}

// The adaptive part: a failed attempt is offered an easier practice set, a mastered one a harder challenge set.
// Like the leaderboard it is a bonus: if it fails, the result still shows.
async function loadPracticeLink(recorded) {
    $("practiceBtn").hidden = true;
    if (!recorded) return;   // a teacher previewing the quiz has no history to adapt to
    try {
        const response = await fetch(`${API}/subjects/${subjectId}/lessons/${lessonId}/practice`, {
            headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        });
        const info = await response.json();
        if (!response.ok || !info.kind) return;
        $("practiceBtn").textContent = info.kind === "harder" ? "Try a challenge set" : "Try an easier practice set";
        $("practiceBtn").href = `practice.html?subject=${subjectId}&lesson=${lessonId}`;
        $("practiceBtn").hidden = false;
    } catch (_) { /* no practice link this time */ }
}

// Below the pass mark the AI explains each missed question step by step (the server saves it, so a retry is cheap).
async function loadBreakdown() {
    $("breakdown").hidden = false;
    $("breakdownRetry").hidden = true;
    $("breakdownBody").replaceChildren();
    $("breakdownStatus").textContent = "Preparing a step-by-step explanation of the questions you missed…";
    try {
        const { breakdown } = await api("/breakdown", { method: "POST" });
        $("breakdownStatus").textContent = "";
        renderBreakdown(breakdown);
        typeset($("breakdownBody"));
    } catch (error) {
        $("breakdownStatus").textContent = error.message;
        $("breakdownRetry").hidden = false;
    }
}
$("breakdownRetry").addEventListener("click", loadBreakdown);

// One card per question, in the order the student saw them: a Correct / Wrong mark, the answer they
// submitted, the right answer when they missed it, and the AI's steps for the missed ones.
// The AI labels each explanation "### Q<id>" and the study tip "### TIP". A breakdown saved before that
// (no labels) is shown as one block, as it always was.
function renderBreakdown(text) {
    const body = $("breakdownBody");
    const pieces = String(text).split(/^###\s*(Q\d+|TIP)\s*$/mi);   // [intro, label, text, label, text, ...]
    const steps = {};
    let tip = "";
    for (let i = 1; i < pieces.length; i += 2) {
        const label = pieces[i].toUpperCase();
        if (label === "TIP") tip = pieces[i + 1].trim();
        else steps[label.slice(1)] = pieces[i + 1].trim();
    }
    if (!Object.keys(steps).length) return renderFinalMessage(body, text);

    const cards = quiz.questions.map((q, i) => {
        const outcome = resultsById[q.id] || { correct: false, correct_answer: "" };
        const card = document.createElement("div");
        card.className = `step-card ${outcome.correct ? "ok" : "bad"}`;

        const title = document.createElement("h3");
        richText(title, `${i + 1}. ${q.question}`);
        card.append(title);

        const given = document.createElement("p");
        given.className = "answer-line";
        const mark = document.createElement("span");
        mark.className = `mark ${outcome.correct ? "ok" : "bad"}`;
        mark.textContent = outcome.correct ? "\u2713 Correct" : "\u2717 Wrong";
        const givenLabel = document.createElement("span");
        richText(givenLabel, `Your answer: ${givenText(q)}`);
        given.append(mark, givenLabel);
        card.append(given);

        // The correct answer is shown on every card, right or wrong; the steps only for missed questions.
        const right = document.createElement("p");
        right.className = "answer-line";
        richText(right, `Correct answer: ${outcome.correct_answer}`);
        card.append(right);
        if (!outcome.correct && steps[q.id]) {
            const stepBody = document.createElement("div");
            stepBody.className = "step-body";
            renderFinalMessage(stepBody, steps[q.id]);
            card.append(stepBody);
        }
        return card;
    });
    body.replaceChildren(...cards);
    $("review").hidden = true;   // the cards above already show right/wrong, your answer, the correct answer and the steps
    if (tip) {
        const tipCard = document.createElement("div");
        tipCard.className = "tip-card";
        const label = document.createElement("strong");
        label.textContent = "Study tip";
        const tipBody = document.createElement("div");
        renderFinalMessage(tipBody, tip);
        tipCard.append(label, tipBody);
        body.append(tipCard);
    }
}

// ---------------------------------------------------------------- go
async function init() {
    if (!subjectId || !lessonId) return fail("This quiz link is missing its lesson.", null);
    $("startSkip").href = lessonUrl(lessonId);
    $("backToLessonBtn").href = lessonUrl(lessonId);
    $("errorBack").href = lessonUrl(lessonId);
    try {
        meta = await api("");
    } catch (error) {
        return fail(error.message, init);
    }
    quiz = meta.quiz;
    if (meta.next_lesson_id) $("nextLessonBtn").href = lessonUrl(meta.next_lesson_id);
    $("lockBack").href = lessonUrl(lessonId);
    if (meta.lock) showLocked();
    else if (quiz) showStart();
    else generate();
}

// ---------------------------------------------------------------- locked after violations
// A quiz ended for violations stays locked until a teacher approves a retake. The server enforces it (no questions are
// sent and submitting is refused); this only shows where the student stands and lets them send their feedback.
function showLocked() {
    $("lockSubtitle").textContent = `${meta.subject}: ${meta.lesson_title}`;
    typeset($("lockSubtitle"));
    renderLock($("lockBox"), meta.lock);
    show("screenLocked");
}

function lockLine(text, className) {
    const p = document.createElement("p");
    if (className) p.className = className;
    p.textContent = text;
    return p;
}

// Builds the lock card into `container` (the lock screen, or under the result when the quiz has just ended).
function renderLock(container, lock) {
    container.hidden = false;
    container.className = "lock-box";
    const parts = [];
    const heading = document.createElement("h2");
    heading.textContent = lock.status === "pending" ? "Waiting for your teacher"
        : lock.status === "rejected" ? "Your teacher did not approve a retake yet" : "You can't retake this quiz yet";
    parts.push(heading);

    if (lock.status === "locked") {
        parts.push(lockLine(`Your quiz was ended after ${lock.violations} violations (leaving the quiz page). Your teacher has to approve a retake. Tell them what happened, then press Send.`));
    } else if (lock.status === "pending") {
        parts.push(lockLine("Your request was sent. You can retake the quiz once your teacher approves it."));
        parts.push(lockLine(lock.feedback, "quote"));
    } else {
        if (lock.teacher_note) { parts.push(lockLine("Your teacher wrote:")); parts.push(lockLine(lock.teacher_note, "quote")); }
        parts.push(lockLine("Review the lesson, then you can send a new request."));
    }

    const status = lockLine("", "lock-status");
    status.setAttribute("role", "status");
    if (lock.can_request) {
        const box = document.createElement("textarea");
        box.maxLength = 600;
        box.placeholder = "What happened? For example: my internet dropped, or I opened another tab by mistake.";
        box.setAttribute("aria-label", "Your feedback for your teacher");
        const send = document.createElement("button");
        send.type = "button";
        send.className = "btn primary";
        send.textContent = "Send request to my teacher";
        send.addEventListener("click", async () => {
            const feedback = box.value.trim();
            if (feedback.length < 10) { status.className = "lock-status bad"; status.textContent = "Please write at least 10 characters so your teacher understands."; return; }
            send.disabled = true;
            try {
                const { lock: next } = await api("/retake-request", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ feedback }),
                });
                meta.lock = next;
                renderLock(container, next);
            } catch (error) {
                send.disabled = false;
                status.className = "lock-status bad";
                status.textContent = error.message;
            }
        });
        parts.push(box, send);
    }
    if (lock.status === "pending") {
        const check = document.createElement("button");
        check.type = "button";
        check.className = "btn";
        check.textContent = "Check for an answer";
        check.addEventListener("click", async () => {
            check.disabled = true;
            try {
                meta = await api("");
                quiz = meta.quiz;
                if (meta.next_lesson_id) $("nextLessonBtn").href = lessonUrl(meta.next_lesson_id);
                if (!meta.lock) return quiz ? showStart() : generate();   // approved: the quiz is open again
                renderLock(container, meta.lock);   // rebuilds the card, so look the status line up again
                container.querySelector(".lock-status").textContent = meta.lock.status === "pending"
                    ? "Still waiting for your teacher." : "Your teacher answered. See above.";
            } catch (error) {
                status.className = "lock-status bad";
                status.textContent = error.message;
                check.disabled = false;
            }
        });
        parts.push(check);
    }
    parts.push(status);
    container.replaceChildren(...parts);
}
init();
