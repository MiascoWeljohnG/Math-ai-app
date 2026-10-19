const ICON_CHECK = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
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

const subjectList = document.getElementById("subjectList");
const lessonListContainer = document.getElementById("lessonListContainer");
const lessonContent = document.getElementById("lessonContent");
const subjectProgress = document.getElementById("subjectProgress");
const subjectProgressFill = document.getElementById("subjectProgressFill");
const subjectProgressLessons = document.getElementById("subjectProgressLessons");
const subjectProgressPct = document.getElementById("subjectProgressPct");

// Modal Elements
const lessonModal = document.getElementById("lessonModal");
document.getElementById("closeLessonModal").addEventListener("click", () => lessonModal.close());

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
        } else subjectList.textContent = "No subjects are available yet.";
    } catch (error) {
        subjectList.textContent = error.message;
    }
}

function renderSubjects() {
    const buttons = subjects.map(subject => {
        const button = document.createElement("button");
        button.type = "button";
        
        const isActive = subject.id === activeSubjectId;
        button.className = `subject-btn ${isActive ? "active" : ""}`;
        
        // Add the (...) to the active subject
        button.textContent = `${subject.name}${subject.is_personal ? " (personal)" : ""}${isActive ? " (...)" : ""}`;
        
        // Single click selects the subject (and opens modal if already active)
        button.addEventListener("click", () => {
            if (!isActive) selectSubject(subject.id);
            else if (!lessonModal.open) lessonModal.showModal();
        });
        
        // Double click pops up the modal safely
        button.addEventListener("dblclick", () => {
            if (!lessonModal.open) lessonModal.showModal();
        });
        
        return button;
    });
    subjectList.replaceChildren(...buttons);
}

async function selectSubject(subjectId, { openList = true } = {}) {
    activeSubjectId = subjectId;
    generateBox.hidden = !subjects.find(subject => subject.id === subjectId)?.is_personal;
    activeLessonId = null;
    activeLessons = [];
    subjectProgress.hidden = true;
    renderSubjects();
    lessonListContainer.textContent = "Loading lessons…";
    lessonContent.replaceChildren();
    
    const placeholder = document.createElement("p");
    placeholder.className = "lesson-empty";
    placeholder.textContent = "Subject selected. Double-click the subject button above to pick a lesson.";
    lessonContent.appendChild(placeholder);

    try {
        const response = await fetch(`${API}/subjects/${subjectId}/lessons`, { headers: lessonAuthHeaders() });
        if (!response.ok) throw new Error("Couldn't load lessons.");
        const lessons = await response.json();
        if (activeSubjectId !== subjectId) return;
        activeLessons = lessons;
        renderLessonList(activeLessons);
        updateSubjectProgress();
        
        // Automatically pop up the modal when a new subject is selected
        if (openList && !lessonModal.open) lessonModal.showModal();
    } catch (error) {
        if (activeSubjectId === subjectId) lessonListContainer.textContent = error.message;
    }
}

function updateSubjectProgress() {
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

function renderLessonList(lessons) {
    if (lessons.length === 0) {
        lessonListContainer.textContent = "No lessons here yet.";
        return;
    }
    const buttons = lessons.map(lesson => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = lesson.id === activeLessonId ? "active" : "";
        button.setAttribute("aria-label", lesson.completed ? `${lesson.title} (completed)` : lesson.title);
        const check = document.createElement("span");
        check.className = "lesson-check";
        check.setAttribute("aria-hidden", "true");
        check.innerHTML = lesson.completed ? ICON_CHECK : "";
        const title = document.createElement("span");
        title.textContent = lesson.title;
        button.append(check, title);
        
        button.addEventListener("click", () => selectLesson(lesson.id));
        return button;
    });
    lessonListContainer.replaceChildren(...buttons);
    typesetMath(lessonListContainer);
}

async function selectLesson(lessonId) {
    activeLessonId = lessonId;
    const subjectId = activeSubjectId;
    renderLessonList(activeLessons);
    
    // Hide the modal once a lesson is picked
    lessonModal.close();
    
    lessonContent.innerHTML = '<p class="lesson-empty">Loading lesson content...</p>';
    
    try {
        const response = await fetch(
            `${API}/subjects/${subjectId}/lessons/${lessonId}`,
            { headers: lessonAuthHeaders() },
        );
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
        
        lessonContent.replaceChildren(heading, meta, body, buildCompleteFooter(subjectId, lesson));
        
        typesetMath(lessonContent);

    } catch (error) {
        if (activeSubjectId === subjectId && activeLessonId === lessonId) {
            lessonContent.textContent = error.message;
        }
    }
}

const quizUrl = (subjectId, lessonId) => `quiz.html?subject=${subjectId}&lesson=${lessonId}`;

// After "Mark as complete": take the quiz now (80% unlocks the next lesson) or come back to it later.
const readyModal = document.getElementById("readyModal");
function askReadyForQuiz(subjectId, lessonId) {
    document.getElementById("readyYes").onclick = () => { window.location.href = quizUrl(subjectId, lessonId); };
    document.getElementById("readyNotYet").onclick = () => readyModal.close();
    readyModal.showModal();
}

function buildCompleteFooter(subjectId, lesson) {
    const footer = document.createElement("div");
    footer.className = "lesson-footer";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "complete-btn";
    const error = document.createElement("span");
    error.className = "complete-error";
    const quizLink = document.createElement("a");
    quizLink.className = "complete-btn";
    quizLink.href = quizUrl(subjectId, lesson.id);
    quizLink.textContent = "Take quiz";
    footer.append(button, quizLink, error);

    const paint = () => {
        button.classList.toggle("done", lesson.completed);
        button.innerHTML = lesson.completed ? `${ICON_CHECK} Completed (click to undo)` : "Mark as complete";
    };
    paint();

    button.addEventListener("click", async () => {
        const next = !lesson.completed;
        button.disabled = true;
        error.textContent = "";
        try {
            const response = await fetch(`${API}/subjects/${subjectId}/lessons/${lesson.id}/completion`, {
                method: "PUT",
                headers: { ...lessonAuthHeaders(), "Content-Type": "application/json" },
                body: JSON.stringify({ completed: next }),
            });
            if (!response.ok) throw new Error("Couldn't save your progress. Please try again.");
            lesson.completed = next;
            paint();
            // Keep the list + bar in step
            if (activeSubjectId === subjectId) {
                const listed = activeLessons.find(item => item.id === lesson.id);
                if (listed) listed.completed = next;
                renderLessonList(activeLessons);
                updateSubjectProgress();
            }
            if (next) askReadyForQuiz(subjectId, lesson.id);
        } catch (err) {
            error.textContent = err.message;
        } finally {
            button.disabled = false;
        }
    });
    return footer;
}

// CRITICAL: This initiates the page load!
loadSubjects();

// Typed topic -> /generate (as before). With a file -> /generate-from-file, which first checks the
// file is about this subject and answers {status: "mismatch"} if not.
async function postGenerate(subjectId, topic, file, force) {
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
            body: JSON.stringify({ topic }),
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
    if (!topic && !file) return;
    const subjectId = activeSubjectId;
    generateBtn.disabled = true;
    generateStatus.textContent = file
        ? "Reading your file and writing the lesson… this can take a minute."
        : "Writing your lesson… this can take a minute.";
    try {
        let result = await postGenerate(subjectId, topic, file, false);
        if (result.status === "mismatch") {
            generateStatus.textContent = "";
            if (!(await askMismatch(result))) {
                generateFile.value = "";   // pick another file
                return;
            }
            generateStatus.textContent = "Writing your lesson… this can take a minute.";
            result = await postGenerate(subjectId, topic, file, true);
        }
        generateTopic.value = "";
        generateFile.value = "";
        generateStatus.textContent = "";
        if (activeSubjectId === subjectId) {
            await selectSubject(subjectId);
            await selectLesson(result.id);
        }
    } catch (error) {
        generateStatus.textContent = error.message;
    } finally {
        generateBtn.disabled = false;
    }
});
