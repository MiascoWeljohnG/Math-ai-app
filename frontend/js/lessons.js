const ICON_CHECK = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
const ICON_LOCK = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
function lessonAuthHeaders() {
    return { Authorization: `Bearer ${localStorage.getItem("token")}` };
}

// Ensure markdown doesn't break math brackets
function protectMath(text) {
    if (!text) return "";
    return text
        .replace(/\\\[/g, '\\\\[')         .replace(/\\\]/g, '\\\\]')
        .replace(/\\\(/g, '\\\\(')         .replace(/\\\)/g, '\\\\)');
}

// MathJax loads asynchronously; if it isn't ready yet it typesets the whole page when it starts.
function typesetMath(...elements) {
    if (window.MathJax && MathJax.typesetPromise) MathJax.typesetPromise(elements).catch(err => console.log(err));
}

const subjectSelect = document.getElementById("subjectSelect");
const openLessons = document.getElementById("openLessons");
const openLessonsTitle = document.getElementById("openLessonsTitle");
const openLessonsSub = document.getElementById("openLessonsSub");
const pickerError = document.getElementById("pickerError");
const lessonListContainer = document.getElementById("lessonListContainer");
const lockHint = document.getElementById("lockHint");
const lessonContent = document.getElementById("lessonContent");
const subjectProgress = document.getElementById("subjectProgress");
const subjectProgressFill = document.getElementById("subjectProgressFill");
const subjectProgressLessons = document.getElementById("subjectProgressLessons");
const subjectProgressPct = document.getElementById("subjectProgressPct");

// Modal Elements
const lessonModal = document.getElementById("lessonModal");
document.getElementById("closeLessonModal").addEventListener("click", () => lessonModal.close());
openLessons.addEventListener("click", () => { if (!lessonModal.open) lessonModal.showModal(); });

const generateBox = document.getElementById("generateBox");
const generateTopic = document.getElementById("generateTopic");
const generateBtn = document.getElementById("generateBtn");
const generateStatus = document.getElementById("generateStatus");
const generateFile = document.getElementById("generateFile");
const mismatchModal = document.getElementById("mismatchModal");

let subjects = [];
let activeSubjectId = null;
let activeLessonId = null;
let activeLessons = [];

function showPickerError(message) {
    pickerError.textContent = message;
    pickerError.hidden = !message;
}

async function loadSubjects() {
    try {
        const response = await fetch(`${API}/subjects`, { headers: lessonAuthHeaders() });
        if (!response.ok) throw new Error("Couldn't load subjects.");
        subjects = await response.json();
        renderSubjects();

        const requested = new URLSearchParams(window.location.search).get("subject");
        const requestedSubject = subjects.find(subject => String(subject.id) === requested);
        const initialSubject = requestedSubject || subjects[0];
        const requestedLesson = Number(new URLSearchParams(window.location.search).get("lesson"));
        if (initialSubject) {
            await selectSubject(initialSubject.id, { openList: !requestedLesson });
            if (requestedLesson && activeLessons.some(lesson => lesson.id === requestedLesson)) await selectLesson(requestedLesson);
            else if (requestedLesson && !lessonModal.open) lessonModal.showModal();
        }
    } catch (error) {
        showPickerError(error.message);
        subjectSelect.replaceChildren(new Option("Couldn't load subjects", ""));
    }
}

function renderSubjects() {
    if (subjects.length === 0) {
        subjectSelect.replaceChildren(new Option("No subjects are available yet", ""));
        subjectSelect.disabled = true;
        return;
    }
    subjectSelect.replaceChildren(...subjects.map(subject =>
        new Option(`${subject.name}${subject.is_personal ? " (personal)" : ""}`, String(subject.id), false, subject.id === activeSubjectId)));
    subjectSelect.disabled = false;
}

subjectSelect.addEventListener("change", () => {
    const id = Number(subjectSelect.value);
    if (id && id !== activeSubjectId) selectSubject(id);
});

// The lesson button doubles as a status line: current lesson (or a prompt) plus how far through the subject you are.
function updateLessonButton() {
    const total = activeLessons.length;
    const completed = activeLessons.filter(lesson => lesson.completed).length;
    const current = activeLessons.find(lesson => lesson.id === activeLessonId);
    openLessonsTitle.textContent = current ? current.title : (total ? "Choose a lesson" : "No lessons yet");
    openLessonsSub.textContent = total ? `${completed} of ${total} complete` : "";
    openLessons.disabled = activeSubjectId === null;
}

function showPlaceholder(text) {
    const placeholder = document.createElement("p");
    placeholder.className = "lesson-empty";
    placeholder.textContent = text;
    lessonContent.replaceChildren(placeholder);
}

async function selectSubject(subjectId, { openList = true } = {}) {
    activeSubjectId = subjectId;
    subjectSelect.value = String(subjectId);
    showPickerError("");
    generateBox.hidden = !subjects.find(subject => subject.id === subjectId)?.is_personal;
    activeLessonId = null;
    activeLessons = [];
    subjectProgress.hidden = true;
    lockHint.hidden = true;
    lessonListContainer.textContent = "Loading lessons…";
    updateLessonButton();
    showPlaceholder("Subject selected. Pick a lesson to begin.");

    try {
        const response = await fetch(`${API}/subjects/${subjectId}/lessons`, { headers: lessonAuthHeaders() });
        if (!response.ok) throw new Error("Couldn't load lessons.");
        const lessons = await response.json();
        if (activeSubjectId !== subjectId) return;
        activeLessons = lessons;
        renderLessonList(activeLessons);
        updateSubjectProgress();

        // Automatically pop up the lesson list when a new subject is selected
        if (openList && !lessonModal.open) lessonModal.showModal();
    } catch (error) {
        if (activeSubjectId === subjectId) lessonListContainer.textContent = error.message;
    }
}

// Re-read the list from the server: completing (or un-completing) a lesson changes which later ones are locked.
async function refreshLessons() {
    const subjectId = activeSubjectId;
    const response = await fetch(`${API}/subjects/${subjectId}/lessons`, { headers: lessonAuthHeaders() });
    if (!response.ok || activeSubjectId !== subjectId) return;
    activeLessons = await response.json();
    renderLessonList(activeLessons);
    updateSubjectProgress();
}

function updateSubjectProgress() {
    updateLessonButton();
    const total = activeLessons.length;
    if (total === 0) {
        subjectProgress.hidden = true;
        return;
    }
    const completed = activeLessons.filter(lesson => lesson.completed).length;
    const percent = Math.round((completed * 100) / total);
    subjectProgressFill.style.width = `${percent}%`;
    subjectProgressLessons.textContent = `${completed} of ${total} lesson${total === 1 ? "" : "s"}`;
    subjectProgressPct.textContent = `${percent}% complete`;
    subjectProgress.hidden = false;
}

function showLockHint() {
    const blocker = activeLessons.find(lesson => !lesson.completed);
    lockHint.textContent = blocker
        ? `Finish "${blocker.title}" first. Pass its quiz (80% or higher) to unlock the next lesson.`
        : "Finish the previous lesson to unlock this one.";
    lockHint.hidden = false;
}

function renderLessonList(lessons) {
    if (lessons.length === 0) {
        lessonListContainer.textContent = "No lessons here yet.";
        return;
    }
    const upNext = lessons.findIndex(lesson => !lesson.completed && !lesson.locked);
    const rows = lessons.map((lesson, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = ["lesson-row",
            lesson.id === activeLessonId ? "active" : "",
            lesson.completed ? "done" : "",
            lesson.locked ? "locked" : ""].filter(Boolean).join(" ");
        const status = lesson.locked ? "locked" : lesson.completed ? "completed" : "";
        button.setAttribute("aria-label", status ? `${lesson.title} (${status})` : lesson.title);
        if (lesson.locked) button.setAttribute("aria-disabled", "true");

        const badge = document.createElement("span");
        badge.className = "lesson-badge";
        badge.setAttribute("aria-hidden", "true");
        badge.innerHTML = lesson.locked ? ICON_LOCK : lesson.completed ? ICON_CHECK : String(index + 1);
        const title = document.createElement("span");
        title.className = "lesson-title";
        title.textContent = lesson.title;
        button.append(badge, title);

        if (lesson.locked || index === upNext) {
            const state = document.createElement("span");
            state.className = `lesson-state${lesson.locked ? "" : " next"}`;
            if (lesson.locked) {
                state.innerHTML = ICON_LOCK;   // a padlock instead of the word "Locked"
                state.setAttribute("role", "img");
                state.setAttribute("aria-label", "Locked");
                state.title = "Locked";
            } else {
                state.setAttribute("aria-hidden", "true");
                state.textContent = "Up next";
            }
            button.append(state);
        }

        button.addEventListener("click", () => {
            if (lesson.locked) showLockHint();
            else selectLesson(lesson.id);
        });
        return button;
    });
    lessonListContainer.replaceChildren(...rows);
    typesetMath(lessonListContainer);
}

async function selectLesson(lessonId) {
    const listed = activeLessons.find(lesson => lesson.id === lessonId);
    if (listed && listed.locked) {   // e.g. a stale ?lesson= link
        showLockHint();
        if (!lessonModal.open) lessonModal.showModal();
        return;
    }
    activeLessonId = lessonId;
    const subjectId = activeSubjectId;
    lockHint.hidden = true;
    renderLessonList(activeLessons);
    updateLessonButton();

    // Hide the modal once a lesson is picked
    lessonModal.close();

    lessonContent.innerHTML = '<p class="lesson-empty">Loading lesson content...</p>';

    try {
        const response = await fetch(
            `${API}/subjects/${subjectId}/lessons/${lessonId}`,
            { headers: lessonAuthHeaders() },
        );
        if (response.status === 403) {   // locked on the server: our list was out of date
            activeLessonId = null;
            await refreshLessons();
            showPlaceholder("This lesson is locked. Finish the one before it to unlock it.");
            showLockHint();
            if (!lessonModal.open) lessonModal.showModal();
            return;
        }
        if (!response.ok) throw new Error("Couldn't load this lesson.");
        const lesson = await response.json();
        if (activeSubjectId !== subjectId || activeLessonId !== lessonId) return;

        const heading = document.createElement("h1");
        heading.textContent = lesson.title;
        const meta = document.createElement("p");
        meta.className = "lesson-meta";
        meta.textContent = `By ${lesson.created_by}`;
        const body = document.createElement("div");

        // Protect the math brackets before rendering
        renderFinalMessage(body, protectMath(lesson.content));

        const gamePanel = buildLessonGamePanel(subjectId, lesson);
        lessonContent.replaceChildren(heading, meta, body, ...(gamePanel ? [gamePanel] : []), buildCompleteFooter(subjectId, lesson));

        typesetMath(lessonContent);

    } catch (error) {
        if (activeSubjectId === subjectId && activeLessonId === lessonId) {
            lessonContent.textContent = error.message;
        }
    }
}

const LESSON_GAMES = [
    ["hangman", "Math Hangman"], ["word-search", "Word Search"], ["matching", "Matching"],
    ["sorting", "Sorting Challenge"], ["fill-blanks", "Fill in the Blanks"],
];
function buildLessonGamePanel(subjectId, lesson) {
    const teacher = ["teacher", "school_admin"].includes(localStorage.getItem("role"));
    if (!teacher && !lesson.preferred_game) return null;
    const panel = document.createElement("section");
    panel.className = "lesson-game-panel";
    const title = document.createElement("h2"); title.textContent = "Lesson game"; panel.append(title);
    const select = document.createElement("select"); select.setAttribute("aria-label", "Choose a game for this lesson");
    select.add(new Option("Choose a game", ""));
    LESSON_GAMES.forEach(([id, label]) => select.add(new Option(label, id)));
    select.value = lesson.preferred_game || "";
    const status = document.createElement("p"); status.className = "lesson-meta";
    status.setAttribute("role", "status");
    if (teacher) {
        const save = document.createElement("button"); save.type = "button"; save.textContent = "Save game";
        save.addEventListener("click", async () => {
            if (!select.value) { status.textContent = "Choose a game first."; return; }
            save.disabled = true;
            try {
                const response = await fetch(`${API}/subjects/${subjectId}/lessons/${lesson.id}/preferred-game`, {
                    method: "PUT", headers: { ...lessonAuthHeaders(), "Content-Type": "application/json" },
                    body: JSON.stringify({ game_id: select.value }),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || "Couldn't save the game.");
                lesson.preferred_game = data.preferred_game; status.textContent = "Game saved for this lesson."; drawPlayLink();
            } catch (error) { status.textContent = error.message; }
            finally { save.disabled = false; }
        });
        panel.append(select, save);
    }
    function drawPlayLink() {
        const old = panel.querySelector("a"); if (old) old.remove();
        if (!lesson.preferred_game) return;
        const link = document.createElement("a");
        link.href = `games.html?subject=${encodeURIComponent(subjectId)}&lesson=${encodeURIComponent(lesson.id)}&game=${encodeURIComponent(lesson.preferred_game)}`;
        link.textContent = `Play ${LESSON_GAMES.find(([id]) => id === lesson.preferred_game)?.[1] || "lesson game"}`;
        panel.append(link);
    }
    drawPlayLink(); panel.append(status); return panel;
}

const quizUrl = (subjectId, lessonId) => `quiz.html?subject=${subjectId}&lesson=${lessonId}`;

// ">" on a lesson that is not finished yet: a lesson only counts as complete once its quiz is passed.
const readyModal = document.getElementById("readyModal");
function askReadyForQuiz(subjectId, lessonId, onLater) {
    document.getElementById("readyYes").onclick = () => { window.location.href = quizUrl(subjectId, lessonId); };
    document.getElementById("readyNotYet").onclick = () => { readyModal.close(); if (onLater) onLater(); };
    readyModal.showModal();
}

// One ">" button: on a finished lesson it moves on to the next one; otherwise it offers the quiz.
// Nothing is marked complete here. Passing the quiz is what completes a lesson and unlocks the next one.
function buildCompleteFooter(subjectId, lesson) {
    const footer = document.createElement("div");
    footer.className = "lesson-footer";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "complete-btn continue-btn";
    button.textContent = ">";
    button.title = lesson.completed ? "Continue to the next lesson" : "Take the quiz to finish this lesson";
    button.setAttribute("aria-label", button.title);
    const error = document.createElement("span");
    error.className = "complete-error";
    footer.append(button, error);

    const followingLesson = () => {
        const index = activeLessons.findIndex(item => item.id === lesson.id);
        const following = index >= 0 ? activeLessons[index + 1] : null;
        return following && !following.locked ? following : null;
    };

    button.addEventListener("click", async () => {
        error.textContent = "";
        // Already done: just go on to the next lesson (the last lesson offers the quiz again instead).
        if (lesson.completed) {
            const following = followingLesson();
            if (following) selectLesson(following.id);
            else askReadyForQuiz(subjectId, lesson.id);
            return;
        }
        askReadyForQuiz(subjectId, lesson.id);   // not completed yet: the quiz is the only way to finish the lesson
    });
    return footer;
}

// CRITICAL: This initiates the page load!
loadSubjects();

// Typed topic -> /generate (as before). With a file -> /generate-from-file, which first checks the
// file is about this subject and answers {status: "mismatch"} if not.
async function postGenerate(subjectId, topic, file, force, preferredGame) {
    let response;
    if (file) {
        const data = new FormData();
        data.append("file", file);
        data.append("topic", topic);
        data.append("force", force);
        response = await fetch(`${API}/subjects/${subjectId}/lessons/generate-from-file`, {
            method: "POST", headers: lessonAuthHeaders(), body: data,
        });
    } else {
        response = await fetch(`${API}/subjects/${subjectId}/lessons/generate`, {
            method: "POST",
            headers: { ...lessonAuthHeaders(), "Content-Type": "application/json" },
            body: JSON.stringify({ topic, preferred_game: preferredGame || null }),
        });
    }
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Couldn't generate the lesson.");
    return result;
}

// Resolves true if the student wants to continue anyway, false to pick another file.
function askMismatch(result) {
    document.getElementById("mismatchText").textContent = result.detected_topic
        ? `This file looks like it is about "${result.detected_topic}", which may not belong to "${result.subject}". Do you want to build the lesson from it anyway?`
        : `We couldn't confirm that this file belongs to "${result.subject}". Do you want to build the lesson from it anyway?`;
    return new Promise(resolve => {
        const finish = (answer) => { mismatchModal.close(); resolve(answer); };
        document.getElementById("mismatchContinue").onclick = () => finish(true);
        document.getElementById("mismatchCancel").onclick = () => finish(false);
        mismatchModal.oncancel = () => resolve(false);   // Esc
        mismatchModal.showModal();
    });
}

generateBtn.addEventListener("click", async () => {
    const topic = generateTopic.value.trim();
    const file = generateFile.files[0];
    const preferredGame = document.getElementById("generatePreferredGame")?.value || "";
    if (!topic && !file) return;
    const subjectId = activeSubjectId;

    generateStatus.textContent = file
        ? "Reading your file and writing the lesson… this can take a minute."
        : "Writing your lesson… this can take a minute.";

    await withButtonLoading(generateBtn, async () => {
        let result = await postGenerate(subjectId, topic, file, false, preferredGame);
        if (result.status === "mismatch") {
            generateStatus.textContent = "";
            if (!(await askMismatch(result))) {
                generateFile.value = "";   // pick another file
                return;
            }
            generateStatus.textContent = "Writing your lesson… this can take a minute.";
            result = await postGenerate(subjectId, topic, file, true, preferredGame);
        }
        if (file && preferredGame && result.id) {
            const assigned = await fetch(`${API}/subjects/${subjectId}/lessons/${result.id}/preferred-game`, {
                method: "PUT", headers: { ...lessonAuthHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ game_id: preferredGame }),
            });
            if (!assigned.ok) throw new Error("Lesson generated, but its game could not be saved.");
        }
        document.getElementById("generatePreferredGame").value = "";
        generateTopic.value = "";
        generateFile.value = "";
        generateStatus.textContent = "";
        if (activeSubjectId === subjectId) {
            await selectSubject(subjectId);
            await selectLesson(result.id);
        }
    }).catch(error => {
        generateStatus.textContent = error.message;
    });
});
