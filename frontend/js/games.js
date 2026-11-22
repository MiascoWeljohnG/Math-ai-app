// Games page controller: the hub (progress, lesson picker, game cards), the player, and the result screen.
// Needs games-core.js and games-modes.js loaded first.

const $g = (id) => document.getElementById(id);
const STAR = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/></svg>';
const starRow = (count, cls = "") => h("span", { class: `gm-stars ${cls}`, "aria-label": `${count} of 3 stars` },
    [0, 1, 2].map(i => { const s = h("span", { class: i < count ? "is-on" : "" }); s.innerHTML = STAR; return s; }));

// A lesson names its game "sorting", "word-search", "matching", "fill-blanks" or "equations"; the cards on this page call them
// "sort", "wordsearch", "match" and "blanks". Without this the Play link on a lesson found no game and showed the hub.
const LESSON_GAME_TO_CARD = { hangman: "hangman", "word-search": "wordsearch", matching: "match", sorting: "sort", "fill-blanks": "blanks", equations: "solve" };
const PACK_WAIT_MS = 25000;   // how long a direct launch waits for the lesson's game content before using the words in the lesson text

let currentPack = BUILTIN_PACK;
let currentLabel = "General math words";
let cleanup = null;
let playing = null;       // the game being played
let packToken = 0;        // so a slow AI reply for an old lesson never replaces the pack of a newer pick

// ---------- hub: progress ----------
function paintProgress() {
    const data = GameStore.load();
    const level = GameStore.level(data.xp), into = data.xp % XP_PER_LEVEL;
    $g("gmLevel").textContent = `Level ${level}`;
    $g("gmXpText").textContent = `${into} / ${XP_PER_LEVEL} XP`;
    $g("gmXpFill").style.width = `${into}%`;
    $g("gmXpBar").setAttribute("aria-valuenow", String(into));
    const streak = GameStore.liveStreak(data);
    $g("gmStreak").textContent = streak === 1 ? "1 day" : `${streak} days`;
    $g("gmPlayed").textContent = String(data.played);
}

// ---------- hub: game cards ----------
function paintCards() {
    const best = GameStore.load().best;
    $g("gmGrid").replaceChildren(...GAMES.map(game => {
        const icon = h("span", { class: "gm-card-icon" }); icon.innerHTML = game.icon;
        return h("button", { class: "gm-game", type: "button", onclick: () => play(game) },
            icon, h("span", { class: "gm-game-name" }, game.name), h("span", { class: "gm-game-blurb" }, game.blurb), starRow(best[game.id] || 0, "small"));
    }));
}

// ---------- hub: lesson picker ----------
function setStatus(text, kind = "") { const el = $g("gmPackStatus"); el.textContent = text; el.className = `gm-note ${kind}`; }
function setError(text) { const el = $g("gmPickerError"); el.textContent = text || ""; el.hidden = !text; }

const lessonOptions = (lessons) => [new Option("General math words", ""), ...lessons.map(l => {
    const option = new Option(l.locked ? `${l.title} (locked)` : l.title, l.id);
    option.disabled = !!l.locked;
    return option;
})];

// A link from a lesson (?subject=&lesson=&game=) goes straight into that game: the hub never shows while it loads.
function directLaunchFromUrl() {
    const query = new URLSearchParams(location.search);
    const asked = query.get("game");
    const card = LESSON_GAME_TO_CARD[asked] || asked;               // also accepts this page's own ids
    const game = GAMES.find(item => item.id === card);
    const subject = query.get("subject"), lesson = query.get("lesson");
    return game && subject && lesson ? { game, subject, lesson } : null;
}

function showGameLoading(game) {
    $g("gmHub").hidden = true; $g("gmPlayer").hidden = false;
    $g("gmPlayerTitle").textContent = game.name;
    $g("gmPlayerLesson").textContent = "";
    $g("gmStageHost").replaceChildren(h("p", { class: "gm-note busy", role: "status" }, "Getting your game ready…"));
}

async function initPicker() {
    const subjectSelect = $g("gmSubject"), lessonSelect = $g("gmLesson");
    const direct = directLaunchFromUrl();
    if (direct) showGameLoading(direct.game);
    let subjects = [];   // declared out here: the deep link below needs it after the try block has ended
    try {
        subjects = await gameSubjects();
        subjectSelect.replaceChildren(new Option("Choose a subject", ""), ...subjects.map(s => new Option(s.name, s.id)));
    } catch (error) { setError(error.message); }

    subjectSelect.addEventListener("change", async () => {
        setError(""); lessonSelect.replaceChildren(new Option("General math words", ""));
        useGeneral();
        if (!subjectSelect.value) return;
        try {
            lessonSelect.replaceChildren(...lessonOptions(await gameLessons(subjectSelect.value)));
        } catch (error) { setError(error.message); }
    });

    lessonSelect.addEventListener("change", async () => {
        setError("");
        const token = ++packToken;
        if (!lessonSelect.value) return useGeneral();
        setStatus("Loading the lesson…");
        try {
            const loaded = await loadPack(subjectSelect.value, lessonSelect.value);
            if (token !== packToken) return;
            currentPack = loaded.pack; currentLabel = loaded.title;
            setStatus(`Games from “${loaded.title}”. Making smarter questions with AI…`, "busy");
            loaded.upgrade.then(better => {
                if (token !== packToken) return;
                if (better) { currentPack = better; setStatus(`Games from “${loaded.title}”. AI-made questions are ready.`, "ok"); }
                else setStatus(Object.keys(loaded.fromText).length
                    ? `Games from “${loaded.title}”, using words found in the lesson.`
                    : `Games for “${loaded.title}” use general math words for now (the AI could not write them).`);
            });
        } catch (error) {
            if (token !== packToken) return;
            setError(error.message); useGeneral();
        }
    });

    const query = new URLSearchParams(location.search);
    const requestedSubject = query.get("subject"), requestedLesson = query.get("lesson");
    let launched = false;
    if (requestedSubject && subjects.some(s => String(s.id) === requestedSubject)) {
        subjectSelect.value = requestedSubject;
        try {
            const lessons = await gameLessons(requestedSubject);
            lessonSelect.replaceChildren(...lessonOptions(lessons));
            if (requestedLesson && lessons.some(l => String(l.id) === requestedLesson && !l.locked)) {
                lessonSelect.value = requestedLesson;
                const loaded = await loadPack(requestedSubject, requestedLesson);
                currentPack = loaded.pack; currentLabel = loaded.title;
                if (direct) {
                    // Start the game as soon as its content is here (a version the teacher generated comes back at once). If the AI is
                    // slow we start with the lesson's own words instead.
                    const better = await Promise.race([loaded.upgrade, new Promise(resolve => setTimeout(() => resolve(null), PACK_WAIT_MS))]);
                    if (better) currentPack = better;
                    else loaded.upgrade.then(late => { if (late) currentPack = late; });   // used by "Play again"
                    play(direct.game);
                    launched = true;
                } else {
                    loaded.upgrade.then(better => { if (better) currentPack = better; });
                }
            }
        } catch (error) { setError(error.message); }
    }
    if (direct && !launched) showHub();   // the lesson could not be opened: show the games with the reason above
}
function useGeneral() { packToken++; currentPack = BUILTIN_PACK; currentLabel = "General math words"; setStatus("Playing with general math words. Pick a lesson to play with its words."); }

// ---------- player ----------
function showHub() {
    if (cleanup) { cleanup(); cleanup = null; }
    playing = null;
    $g("gmPlayer").hidden = true; $g("gmHub").hidden = false;
    paintProgress(); paintCards();
    window.scrollTo({ top: 0 });
}

function play(game) {
    if (cleanup) { cleanup(); cleanup = null; }
    playing = game;
    $g("gmHub").hidden = true; $g("gmPlayer").hidden = false;
    $g("gmPlayerTitle").textContent = game.name;
    $g("gmPlayerLesson").textContent = currentLabel;
    const stage = h("div", { class: "gm-stage" });
    $g("gmStageHost").replaceChildren(stage);
    try {
        cleanup = game.mount(stage, currentPack, (stars, summary) => finish(game, stars, summary)) || null;
    } catch (error) {
        console.error(error);
        stage.replaceChildren(h("p", { class: "gm-note bad" }, "This game could not start. Go back and try another one."));
    }
    window.scrollTo({ top: 0 });
}

const MESSAGES = ["Not this time. Try again!", "Good start. You can beat it!", "Nice work!", "Perfect round!"];

function finish(game, stars, summary) {
    if (cleanup) { cleanup(); cleanup = null; }
    const result = GameStore.record(game.id, stars);
    const streak = GameStore.liveStreak(result.data);
    $g("gmStageHost").replaceChildren(h("div", { class: "gm-result" },
        starRow(stars, "big"),
        h("h2", {}, MESSAGES[stars]),
        summary ? h("p", { class: "gm-note" }, summary) : null,
        h("p", { class: "gm-gain" }, `+${result.gained} XP`),
        result.levelUp ? h("p", { class: "gm-levelup" }, `Level up! You are now level ${result.level}.`) : null,
        h("p", { class: "gm-note" }, streak > 1 ? `${streak}-day streak. Come back tomorrow to keep it going.` : "Play again tomorrow to start a streak."),
        h("div", { class: "gm-actions" },
            h("button", { class: "gm-btn primary", type: "button", onclick: () => play(game) }, "Play again"),
            h("button", { class: "gm-btn", type: "button", onclick: showHub }, "All games")),
    ));
}

$g("gmBack").addEventListener("click", showHub);
useGeneral();
paintProgress();
paintCards();
initPicker();
