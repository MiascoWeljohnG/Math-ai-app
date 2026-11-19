// Games page: shared pieces. Progress (XP, level, streak), small helpers, the content a game is built from, and how that
// content is loaded for a lesson.
//
// Game content ("a pack") looks like this. Every part is optional; whatever is missing is filled in from something simpler:
//   { terms: [{word, clue}], sort: {left, right, items: [{text, side}]}, blanks: [{sentence, answer}], match: [{a, b}] }
//
//   1. The AI pack from the backend (POST /subjects/:id/lessons/:id/games), best quality.
//   2. Words found in the lesson text itself (bold terms and their sentences), so games work with no model at all.
//   3. A built-in set of general math words, so a game can always start.
//
// Games are ungraded. XP and streaks stay in this browser (localStorage), they do not touch the leaderboard.

const GAME_XP_PER_STAR = [5, 20, 35, 50];   // 0, 1, 2, 3 stars
const XP_PER_LEVEL = 100;

// ---------- small helpers ----------
function shuffle(list) {
    const a = [...list];
    for (let i = a.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [a[i], a[j]] = [a[j], a[i]];
    }
    return a;
}
const randInt = (lo, hi) => lo + Math.floor(Math.random() * (hi - lo + 1));
const pickOne = (list) => list[Math.floor(Math.random() * list.length)];

// Tiny DOM builder. Text is always set as text, never parsed as HTML, so lesson content cannot inject markup.
const SVG_TAGS = new Set(["svg", "path", "circle", "polyline", "rect", "line", "g"]);
function h(tag, props = {}, ...children) {
    const isSvg = SVG_TAGS.has(tag);
    const el = isSvg ? document.createElementNS("http://www.w3.org/2000/svg", tag) : document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
        if (value === undefined || value === null || value === false) continue;
        if (key === "dataset") Object.assign(el.dataset, value);
        else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
        else if (isSvg || key.includes("-") || key === "list") el.setAttribute(key, value);
        else if (key === "class") el.className = value;
        else if (key in el) el[key] = value;
        else el.setAttribute(key, value);
    }
    for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        el.append(child.nodeType ? child : document.createTextNode(String(child)));
    }
    return el;
}

// Stars from how many tries a round needed: first try 3, second 2, third 1, otherwise 0.
const starsFromAttempts = (attemptsUsed, won) => (!won ? 0 : Math.max(1, 4 - attemptsUsed));

// ---------- progress ----------
const GameStore = {
    key() { return `games_progress:${localStorage.getItem("username") || "guest"}`; },
    load() {
        try {
            const data = JSON.parse(localStorage.getItem(this.key()) || "{}");
            return { xp: 0, streak: 0, lastDay: "", played: 0, best: {}, earned: {}, ...data };
        } catch { return { xp: 0, streak: 0, lastDay: "", played: 0, best: {}, earned: {} }; }
    },
    save(data) { try { localStorage.setItem(this.key(), JSON.stringify(data)); } catch { /* storage full or blocked: skip */ } },
    level(xp) { return Math.floor(xp / XP_PER_LEVEL) + 1; },
    day(date = new Date()) {   // local calendar day as YYYY-MM-DD
        const p = (n) => String(n).padStart(2, "0");
        return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())}`;
    },
    // Record a finished round. Returns what the result screen shows.
    // XP is paid once per lesson + game: a replay only earns the XP for stars not earned before there, so spamming one
    // game from one lesson stops paying (the most a pair can ever give is the 3-star amount).
    record(gameId, stars, lessonId = "") {
        const data = this.load();
        const before = this.level(data.xp);
        const tier = Math.max(0, Math.min(3, stars));
        const pairKey = `${lessonId || "general"}:${gameId}`;
        const alreadyEarned = data.earned[pairKey] || 0;   // XP already paid for this lesson + game
        const gained = Math.max(0, GAME_XP_PER_STAR[tier] - alreadyEarned);
        data.earned[pairKey] = alreadyEarned + gained;
        data.xp += gained;
        data.played += 1;
        data.best[gameId] = Math.max(data.best[gameId] || 0, stars);
        const today = this.day(), yesterday = this.day(new Date(Date.now() - 86400000));
        if (data.lastDay !== today) {
            data.streak = data.lastDay === yesterday ? data.streak + 1 : 1;
            data.lastDay = today;
        }
        this.save(data);
        return { gained, repeat: gained === 0, data, levelUp: this.level(data.xp) > before, level: this.level(data.xp) };
    },
    // A streak only counts while it is still alive (played today or yesterday).
    liveStreak(data) {
        return data.lastDay === this.day() || data.lastDay === this.day(new Date(Date.now() - 86400000)) ? data.streak : 0;
    },
};

// ---------- content ----------
const BUILTIN_PACK = {
    terms: [
        { word: "FRACTION", clue: "A part of a whole, written with a top and a bottom number" },
        { word: "VARIABLE", clue: "A letter that stands for a number we do not know yet" },
        { word: "EQUATION", clue: "A statement that two expressions are equal" },
        { word: "PRODUCT", clue: "The answer when you multiply" },
        { word: "QUOTIENT", clue: "The answer when you divide" },
        { word: "DIAMETER", clue: "A line across a circle through its center" },
        { word: "PERIMETER", clue: "The distance around a shape" },
        { word: "INTEGER", clue: "A whole number that can be negative, zero or positive" },
        { word: "PERCENT", clue: "A number out of one hundred" },
        { word: "AVERAGE", clue: "The sum of values divided by how many there are" },
    ],
    sort: {
        left: "Even numbers", right: "Odd numbers",
        items: [
            { text: "12", side: "left" }, { text: "48", side: "left" }, { text: "106", side: "left" }, { text: "30", side: "left" }, { text: "74", side: "left" },
            { text: "7", side: "right" }, { text: "25", side: "right" }, { text: "93", side: "right" }, { text: "41", side: "right" }, { text: "59", side: "right" },
        ],
    },
    blanks: [
        { sentence: "The answer to a multiplication problem is called the ___.", answer: "product" },
        { sentence: "A ___ is a letter that stands for an unknown number.", answer: "variable" },
        { sentence: "The distance around a shape is its ___.", answer: "perimeter" },
        { sentence: "A ___ compares a number to one hundred.", answer: "percent" },
    ],
    match: [
        { a: "Sum", b: "The answer to an addition" },
        { a: "Difference", b: "The answer to a subtraction" },
        { a: "Product", b: "The answer to a multiplication" },
        { a: "Quotient", b: "The answer to a division" },
        { a: "Radius", b: "Center of a circle to its edge" },
    ],
};

const STOP_WORDS = new Set(["THE", "AND", "THAT", "THIS", "WITH", "FROM", "THEY", "WILL", "EACH", "ARE", "FOR"]);

// Find vocabulary in the lesson's own text: **bold terms** (and headings) with the sentence that explains them.
function localPack(markdown) {
    const text = String(markdown || "").replace(/\r/g, "");
    const plain = text.replace(/\$\$[\s\S]*?\$\$/g, " ").replace(/\$[^$\n]*\$/g, " ");
    const sentences = plain.split(/(?<=[.!?])\s+|\n+/).map(s => s.replace(/[*_#>`-]+/g, " ").replace(/\s+/g, " ").trim()).filter(s => s.length > 25 && s.length < 240);

    const candidates = new Map();   // WORD -> sentence that uses it
    const add = (raw) => {
        for (const piece of String(raw).split(/[\s/,-]+/)) {
            const word = piece.replace(/[^A-Za-z]/g, "").toUpperCase();
            if (word.length < 4 || word.length > 10 || STOP_WORDS.has(word) || candidates.has(word)) continue;
            const sentence = sentences.find(s => new RegExp(`\\b${word}\\b`, "i").test(s));
            if (sentence) candidates.set(word, sentence);
        }
    };
    for (const m of plain.matchAll(/\*\*([^*\n]{3,40})\*\*/g)) add(m[1]);
    for (const m of plain.matchAll(/^#{1,4}\s+(.{3,40})$/gm)) add(m[1]);

    const terms = [], blanks = [];
    for (const [word, sentence] of candidates) {
        const masked = sentence.replace(new RegExp(`\\b${word}\\b`, "i"), "___");
        if (masked.split("___").length !== 2) continue;   // the word must appear exactly once for a clean blank
        terms.push({ word, clue: masked.replace("___", "_____") });
        blanks.push({ sentence: masked, answer: word.toLowerCase() });
    }
    const pack = {};
    if (terms.length >= 4) pack.terms = terms.slice(0, 10);
    if (blanks.length >= 3) pack.blanks = blanks.slice(0, 5);
    return pack;
}

// Missing or too-small parts come from the next simpler source.
function mergePacks(...packs) {
    const out = {};
    const usable = {
        terms: (v) => Array.isArray(v) && v.length >= 4,
        sort: (v) => v && Array.isArray(v.items) && v.items.length >= 4,
        blanks: (v) => Array.isArray(v) && v.length >= 3,
        match: (v) => Array.isArray(v) && v.length >= 4,
    };
    for (const part of Object.keys(usable)) {
        const source = packs.find(p => p && usable[part](p[part]));
        out[part] = (source || BUILTIN_PACK)[part];
    }
    return out;
}

// ---------- loading ----------
function gameHeaders() { return { Authorization: `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json" }; }

async function gameApi(path, options = {}) {
    const response = await fetch(`${API}${path}`, { ...options, headers: { ...gameHeaders(), ...(options.headers || {}) } });
    const body = await response.json().catch(() => ({}));
    if (response.status === 401) throw new Error("Your session expired. Please log in again.");
    if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : "Something went wrong. Please try again.");
    return body;
}

// Lesson list for a subject (locked lessons are marked, and the backend refuses their content).
const gameSubjects = () => gameApi("/subjects");
const gameLessons = (subjectId) => gameApi(`/subjects/${subjectId}/lessons`);

// Returns { pack, source } right away from the lesson text; `upgrade` resolves later with the AI pack, or null on any error.
async function loadPack(subjectId, lessonId) {
    const lesson = await gameApi(`/subjects/${subjectId}/lessons/${lessonId}`);
    const fromText = localPack(lesson.content);
    const cacheKey = `gamepack:${lessonId}:${(lesson.content || "").length}`;
    let cached = null;
    try { cached = JSON.parse(sessionStorage.getItem(cacheKey) || "null"); } catch { /* ignore */ }
    const upgrade = cached ? Promise.resolve(cached) : gameApi(`/subjects/${subjectId}/lessons/${lessonId}/games`, { method: "POST" })
        .then((ai) => { try { sessionStorage.setItem(cacheKey, JSON.stringify(ai)); } catch { /* ignore */ } return ai; })
        .catch(() => null);
    return {
        title: lesson.title,
        fromText,
        pack: mergePacks(cached, fromText),
        upgrade: upgrade.then(ai => (ai ? mergePacks(ai, fromText) : null)),
    };
}
