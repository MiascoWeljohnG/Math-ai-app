// Practice page: ?subject=<id>&lesson=<id>. An easier set after a weak quiz, a harder one after a strong quiz.
// Practice is ungraded: it never touches the leaderboard or the student's level (see practice_routes.py).
const params = new URLSearchParams(window.location.search);
const subjectId = params.get("subject");
const lessonId = params.get("lesson");
const base = `${API}/subjects/${subjectId}/lessons/${lessonId}/practice`;
const $ = (id) => document.getElementById(id);
const typeset = (...elements) => { if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise(elements).catch(() => {}); };

const BLURB = {
    easier: "An easier set on the ideas you missed, to build up before you retake the quiz.",
    harder: "A harder challenge set, because you mastered this lesson. Test how far you can go.",
};
const NOTE = " It is only practice: it does not change your score, your level or the leaderboard.";

let questions = [];
let retryAction = null;
let tries = 0, maxTries = null;   // maxTries is null when there is no limit (a student's own subject)

async function api(path = "", options = {}) {
    const response = await fetch(base + path, {
        ...options,
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json", ...(options.headers || {}) },
    });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) throw new Error("Your session expired. Please log in again.");
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.");
    return body;
}

// Small DOM helper: the model's text is only ever set as text, never parsed as HTML.
function node(tag, props = {}, ...children) {
    const element = Object.assign(document.createElement(tag), props);
    element.append(...children);
    return element;
}

function fail(message, retry) {
    retryAction = retry;
    $("status").className = "muted error";
    $("status").textContent = message;
    $("retryBtn").hidden = !retry;
    $("tryAgainBtn").disabled = false;
}
function working(message) {   // clears an earlier error and shows progress
    $("status").className = "muted";
    $("status").textContent = message;
    $("retryBtn").hidden = true;
}
// "Try again" after an error repeats exactly what failed (loading the page, or writing a new set).
$("retryBtn").addEventListener("click", () => { const again = retryAction; retryAction = null; if (again) again(); });

const THE_LIMIT = (n) => `You have used all ${n} of your tries. You can only retake the exam if your teacher approves it. Your teacher has been notified. Open the quiz page to send them a message.`;

function showTries() {
    $("triesNote").hidden = maxTries === null;
    if (maxTries !== null) $("triesNote").textContent = `Try ${Math.min(tries, maxTries)} of ${maxTries}`;
}

// The notice shown when every try is used: the quiz needs the teacher's approval.
function showLimit() {
    const box = $("limitNote");
    box.replaceChildren(node("p", {}, THE_LIMIT(maxTries || 3)));
    box.hidden = false;
    $("tryAgainBtn").hidden = true;
    $("checkBtn").hidden = true;
    $("result").hidden = false;
}

// A brand new set of questions on the same ideas. Each one uses one of the tries.
async function tryAgain() {
    $("tryAgainBtn").disabled = true;
    working("The AI is writing a new set for you… this can take a minute.");
    try {
        render(await api("/generate?fresh=true", { method: "POST" }));
    } catch (error) {
        $("tryAgainBtn").disabled = false;
        if (/only retake the exam if your teacher approves/i.test(error.message)) {
            $("status").textContent = "";
            return showLimit();
        }
        fail(error.message, tryAgain);
    }
}
$("tryAgainBtn").addEventListener("click", tryAgain);

function buildQuestion(q, i) {
    const box = node("div", { className: "q", id: `q${q.id}` }, node("p", { className: "q-text" }, `${i + 1}. ${q.question}`));
    const radio = (value, label) => node("label", { className: "choice" },
        Object.assign(document.createElement("input"), { type: "radio", name: `q${q.id}`, value }), ` ${label}`);
    if (q.type === "mcq") q.choices.forEach((choice, n) => box.append(radio(String(n), `${String.fromCharCode(65 + n)}. ${choice}`)));
    else if (q.type === "tf") box.append(radio("true", "True"), radio("false", "False"));
    else box.append(Object.assign(document.createElement("input"), { type: "text", name: `q${q.id}`, placeholder: "Your answer", autocomplete: "off" }));
    return box;
}

function collect() {
    const answers = {};
    for (const q of questions) {
        const fields = [...document.getElementsByName(`q${q.id}`)];
        if (q.type === "id" || q.type === "num") answers[q.id] = fields[0].value.trim() || null;
        else {
            const picked = fields.find(field => field.checked);
            answers[q.id] = !picked ? null : q.type === "mcq" ? Number(picked.value) : picked.value === "true";
        }
    }
    return answers;
}

function render(data) {
    $("title").textContent = data.kind === "harder" ? "Challenge set" : "Practice set";
    $("subtitle").textContent = `${data.subject}: ${data.lesson_title}`;
    $("blurb").textContent = BLURB[data.kind] + NOTE;
    $("status").className = "muted";
    $("status").textContent = "";
    tries = data.tries || 0;
    maxTries = data.max_tries ?? null;
    questions = data.questions;
    $("questions").replaceChildren(...questions.map(buildQuestion));
    $("checkBtn").hidden = false;
    $("checkBtn").disabled = false;
    $("result").hidden = true;
    $("limitNote").hidden = true;
    $("tryAgainBtn").hidden = true;
    $("tryAgainBtn").disabled = false;
    showTries();
    typeset($("subtitle"), $("questions"));
}

$("checkBtn").addEventListener("click", async () => {
    $("checkBtn").disabled = true;
    try {
        const result = await api("/submit", { method: "POST", body: JSON.stringify({ answers: collect() }) });
        const byId = Object.fromEntries(result.results.map(item => [item.id, item]));
        for (const q of questions) {
            const outcome = byId[q.id], box = $(`q${q.id}`);
            box.className = `q ${outcome.correct ? "ok" : "bad"}`;
            box.querySelectorAll("input").forEach(input => { input.disabled = true; });
            box.append(node("p", { className: "why" }, outcome.correct ? "Correct." : `Correct answer: ${outcome.correct_answer}`));
            if (outcome.explanation) box.append(node("p", { className: "why" }, outcome.explanation));
        }
        $("score").textContent = `You got ${result.score} of ${result.total} right.`;
        $("result").hidden = false;
        $("checkBtn").hidden = true;
        tries = result.tries ?? tries;
        maxTries = result.max_tries ?? null;
        showTries();
        if (result.exhausted) showLimit();   // that was the last try
        else {
            $("tryAgainBtn").hidden = false;
            const left = maxTries === null ? null : maxTries - tries;
            $("tryAgainBtn").textContent = left === null ? "Try again with new questions"
                : `Try again with new questions (${left} ${left === 1 ? "try" : "tries"} left)`;
        }
        typeset($("questions"), $("score"));
    } catch (error) {
        $("checkBtn").disabled = false;
        fail(error.message, null);
    }
});

async function init() {
    if (!subjectId || !lessonId) return fail("This practice link is missing its lesson.", null);
    $("quizLink").href = `quiz.html?subject=${subjectId}&lesson=${lessonId}`;
    $("lessonLink").href = `lessons.html?subject=${subjectId}&lesson=${lessonId}`;
    try {
        let data = await api();
        if (!data.kind) {   // nothing to practice at this level
            $("subtitle").textContent = `${data.subject}: ${data.lesson_title}`;
            $("status").textContent = data.level === "new"
                ? "Take this lesson's quiz first, then come back for a practice set made for you."
                : "You passed this lesson, so there is no extra practice set to do. Nice work!";
            $("result").hidden = false;
            $("score").textContent = "";
            return;
        }
        tries = data.tries || 0;
        maxTries = data.max_tries ?? null;
        if (data.exhausted && !data.questions) {   // all tries used and no set to show: the teacher has to approve
            $("subtitle").textContent = `${data.subject}: ${data.lesson_title}`;
            $("status").textContent = "";
            showTries();
            return showLimit();
        }
        if (!data.questions) {
            working("The AI is writing a set for you… this can take a minute.");
            data = await api("/generate", { method: "POST" });
        }
        render(data);
    } catch (error) {
        if (/only retake the exam if your teacher approves/i.test(error.message)) {
            $("status").textContent = "";
            return showLimit();
        }
        fail(error.message, init);
    }
}
init();
