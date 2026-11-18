// The seven games. Each one is { id, name, blurb, icon, mount(stage, pack, finish) }.
//   stage  - an empty element the game builds itself into
//   pack   - the lesson's game content (see games-core.js)
//   finish - call once when the round is over: finish(stars 0-3, "short summary")
// mount() may return a cleanup function (timers, keyboard listeners); the page calls it when the round ends or is left.
//
// Everything works with a mouse, a finger or the keyboard where that makes sense: pieces can be dragged OR tapped
// (tap a piece, then tap where it goes), because HTML5 drag and drop does not work on phones.

const gameIcon = (paths) => `<svg viewBox="0 0 24 24" aria-hidden="true">${paths}</svg>`;

// ---------- shared: tap-or-drag placement ----------
function createPlacer(onPlace) {
    let held = null;
    const release = () => { if (held) held.classList.remove("is-held"); held = null; };
    const zoneOf = (el) => el.closest("[data-zone]");
    return {
        chip(el) {
            el.draggable = true;
            el.tabIndex = 0;
            el.setAttribute("role", "button");
            el.addEventListener("dragstart", (e) => {
                if (el.dataset.locked) { e.preventDefault(); return; }
                held = el; el.classList.add("is-held");
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", el.textContent);
            });
            el.addEventListener("dragend", release);
            el.addEventListener("click", (e) => {
                e.stopPropagation();
                if (el.dataset.locked) return;
                if (held && held !== el && zoneOf(el)) { const chip = held; release(); onPlace(chip, zoneOf(el)); return; }   // drop onto a taken spot
                if (held === el) release(); else { release(); held = el; el.classList.add("is-held"); }
            });
            el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); el.click(); } });
        },
        zone(el) {
            el.dataset.zone = "1";
            el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("is-over"); });
            el.addEventListener("dragleave", () => el.classList.remove("is-over"));
            el.addEventListener("drop", (e) => { e.preventDefault(); el.classList.remove("is-over"); if (held) { const chip = held; release(); onPlace(chip, el); } });
            el.addEventListener("click", () => { if (held) { const chip = held; release(); onPlace(chip, el); } });
        },
    };
}

// Shared "Check" logic for the three placement games. Three tries; fewer tries means more stars.
function makeChecker({ max = 3, button, evaluate, sendBack, reveal, onTry, finish }) {
    let attempts = 0, busy = false;
    onTry(attempts);
    button.addEventListener("click", () => {
        if (button.disabled || busy) return;
        busy = true;
        attempts += 1;
        const results = evaluate();   // [{ chip, ok }]
        for (const { chip, ok } of results) {
            chip.classList.toggle("is-right", ok);
            chip.classList.toggle("is-wrong", !ok);
            if (ok) chip.dataset.locked = "1";
        }
        onTry(attempts);
        button.disabled = true;
        if (results.every(r => r.ok)) return void setTimeout(() => finish(starsFromAttempts(attempts, true), `Solved on try ${attempts}`), 800);
        if (attempts >= max) {
            return void setTimeout(() => { reveal(); setTimeout(() => finish(0, "Out of tries. The answers are shown."), 1600); }, 900);
        }
        setTimeout(() => { results.filter(r => !r.ok).forEach(({ chip }) => { chip.classList.remove("is-wrong"); sendBack(chip); }); busy = false; }, 1000);
    });
}

// Show the answers: put the right chip in every slot. chipKey / slotKey are the data-* names that must match.
function revealInto(stage, pool, slots, chipKey, slotKey) {
    const sitsRight = (chip) => chip.parentElement && chip.parentElement.dataset[slotKey] === chip.dataset[chipKey];
    for (const slot of slots) {
        if (slot.firstChild && sitsRight(slot.firstChild)) continue;
        const chip = [...stage.querySelectorAll(".gm-chip")].find(c => c.dataset[chipKey] === slot.dataset[slotKey] && !sitsRight(c));
        if (!chip) continue;
        if (slot.firstChild) pool.append(slot.firstChild);
        slot.append(chip); chip.classList.remove("is-wrong"); chip.classList.add("is-right");
    }
}

const hud = (...items) => h("div", { class: "gm-hud" }, items.map(item => h("span", { class: "gm-hud-item" }, item)));

// ---------- 1. Sort It (good / bad, even / odd, true / false ...) ----------
function mountSort(stage, pack, finish) {
    const data = pack.sort;
    const pick = (side) => shuffle(data.items.filter(i => i.side === side)).slice(0, 5);
    const items = shuffle([...pick("left"), ...pick("right")]);
    const tries = h("span", {}, "Tries: 0 / 3");
    const pool = h("div", { class: "gm-pool" });
    const bucket = (side, title) => h("div", { class: "gm-bucket" }, h("h4", {}, title), h("div", { class: "gm-bucket-body", dataset: { side } }));
    const left = bucket("left", data.left), right = bucket("right", data.right);
    const button = h("button", { class: "gm-btn primary", type: "button", disabled: true }, "Check");

    const bodies = [left.lastChild, right.lastChild];
    const refresh = () => { button.disabled = pool.children.length > 0; };
    const placer = createPlacer((chip, zone) => { chip.classList.remove("is-wrong", "is-right"); zone.append(chip); refresh(); });
    placer.zone(pool); bodies.forEach(placer.zone);
    items.forEach(item => {
        const chip = h("button", { class: "gm-chip", type: "button", dataset: { side: item.side } }, item.text);
        placer.chip(chip); pool.append(chip);
    });

    makeChecker({
        button, finish, onTry: (n) => { tries.textContent = `Tries: ${n} / 3`; },
        evaluate: () => bodies.flatMap(body => [...body.children].map(chip => ({ chip, ok: chip.dataset.side === body.dataset.side }))),
        sendBack: (chip) => { pool.append(chip); refresh(); },
        reveal: () => [...stage.querySelectorAll(".gm-chip")].forEach(chip => {
            if (chip.dataset.locked) return;
            bodies.find(b => b.dataset.side === chip.dataset.side).append(chip);
            chip.classList.remove("is-wrong"); chip.classList.add("is-right");
        }),
    });
    stage.append(
        hud(tries, "Tap or drag each card into its group."),
        pool, h("div", { class: "gm-buckets" }, left, right), h("div", { class: "gm-actions" }, button),
    );
}

// ---------- 2. Hangman ----------
const HANGMAN_PARTS = [
    '<circle cx="110" cy="52" r="14"/>', '<path d="M110 66v42"/>', '<path d="M110 78 90 96"/>',
    '<path d="M110 78l20 18"/>', '<path d="M110 108 92 136"/>', '<path d="M110 108l18 28"/>',
];

function mountHangman(stage, pack, finish) {
    const rounds = shuffle(pack.terms).slice(0, 3);
    let index = 0, solved = 0, word = "", clue = "", guessed = new Set(), errors = 0, over = false;
    const MAX_ERRORS = 6;
    const round = h("span"), errorsEl = h("span");
    const drawing = h("svg", { class: "gm-hang", viewBox: "0 0 160 150", "aria-hidden": "true" });
    const tiles = h("div", { class: "gm-tiles", "aria-live": "polite" });
    const clueEl = h("p", { class: "gm-clue", hidden: true });
    const clueBtn = h("button", { class: "gm-btn", type: "button" }, "Show clue");
    const keys = h("div", { class: "gm-keys" });
    const buttons = {};
    clueBtn.addEventListener("click", () => { clueEl.hidden = !clueEl.hidden; clueBtn.textContent = clueEl.hidden ? "Show clue" : "Hide clue"; });
    for (const letter of "ABCDEFGHIJKLMNOPQRSTUVWXYZ") {
        buttons[letter] = h("button", { class: "gm-key", type: "button", onclick: () => guess(letter) }, letter);
        keys.append(buttons[letter]);
    }

    const draw = () => {
        drawing.innerHTML = '<path d="M20 144h120M44 144V12h66v22" fill="none"/>' + HANGMAN_PARTS.slice(0, errors).join("");
    };
    const paint = (reveal = false) => {
        tiles.replaceChildren(...[...word].map(letter => h("span", {
            class: `gm-tile${guessed.has(letter) ? " is-on" : reveal ? " is-missed" : ""}`,
        }, guessed.has(letter) || reveal ? letter : "")));
        errorsEl.textContent = `Errors: ${errors} / ${MAX_ERRORS}`;
        round.textContent = `Word ${index + 1} of ${rounds.length}`;
        draw();
    };
    const next = () => {
        index += 1;
        if (index >= rounds.length) return finish(solved, `${solved} of ${rounds.length} words`);
        start();
    };
    function start() {
        word = rounds[index].word; clue = rounds[index].clue;
        guessed = new Set(); errors = 0; over = false;
        clueEl.textContent = clue; clueEl.hidden = true; clueBtn.textContent = "Show clue";
        Object.values(buttons).forEach(b => { b.disabled = false; b.className = "gm-key"; });
        paint();
    }
    function guess(letter) {
        if (over || guessed.has(letter)) return;
        guessed.add(letter);
        const hit = word.includes(letter);
        buttons[letter].disabled = true;
        buttons[letter].classList.add(hit ? "is-hit" : "is-miss");
        if (!hit) errors += 1;
        paint();
        if ([...word].every(l => guessed.has(l))) { over = true; solved += 1; setTimeout(next, 900); }
        else if (errors >= MAX_ERRORS) { over = true; paint(true); setTimeout(next, 1700); }
    }
    const onKey = (e) => { if (!e.ctrlKey && !e.metaKey && !e.altKey && /^[a-z]$/i.test(e.key)) guess(e.key.toUpperCase()); };
    document.addEventListener("keydown", onKey);

    stage.append(hud(round, errorsEl), h("div", { class: "gm-hang-row" }, drawing, h("div", {}, tiles, clueEl, clueBtn)), keys);
    start();
    return () => document.removeEventListener("keydown", onKey);
}

// ---------- 3. Word Search ----------
const WS_SIZE = 10;
const WS_DIRS = [[0, 1], [1, 0], [1, 1], [-1, 1]];   // right, down, down-right, up-right

function buildWordSearch(words, size = WS_SIZE) {
    const grid = Array.from({ length: size }, () => Array(size).fill(""));
    const placed = [];
    for (const word of [...words].sort((a, b) => b.length - a.length)) {
        for (let attempt = 0; attempt < 600; attempt++) {
            const [dr, dc] = pickOne(WS_DIRS), r0 = randInt(0, size - 1), c0 = randInt(0, size - 1);
            const rEnd = r0 + dr * (word.length - 1), cEnd = c0 + dc * (word.length - 1);
            if (rEnd < 0 || rEnd >= size || cEnd < 0 || cEnd >= size) continue;
            let fits = true;
            for (let i = 0; i < word.length && fits; i++) {
                const cell = grid[r0 + dr * i][c0 + dc * i];
                fits = cell === "" || cell === word[i];
            }
            if (!fits) continue;
            for (let i = 0; i < word.length; i++) grid[r0 + dr * i][c0 + dc * i] = word[i];
            placed.push(word);
            break;
        }
    }
    const pool = words.join("") + "ETAOINSRHLDCU";   // filler leans on letters from the words so it is not obvious
    for (let r = 0; r < size; r++) for (let c = 0; c < size; c++) if (!grid[r][c]) grid[r][c] = pickOne([...pool]);
    return { grid, placed };
}

function mountWordSearch(stage, pack, finish) {
    const words = shuffle(pack.terms.map(t => t.word).filter(w => w.length <= WS_SIZE)).slice(0, 6);
    const { grid, placed } = buildWordSearch(words);
    const found = new Set();
    const startedAt = Date.now();
    const timer = h("span", {}, "Time: 0:00");
    const status = h("span", {}, `Found: 0 / ${placed.length}`);
    const list = h("ul", { class: "gm-wordlist" }, placed.map(w => h("li", { dataset: { word: w } }, w)));
    const board = h("div", { class: "gm-ws", style: `--n:${WS_SIZE}` });
    const cells = grid.map((row, r) => row.map((letter, c) => {
        const cell = h("div", { class: "gm-ws-cell", dataset: { r, c } }, letter);
        board.append(cell);
        return cell;
    }));

    let start = null, path = [];
    const cellAt = (x, y) => { const el = document.elementFromPoint(x, y); return el && el.closest(".gm-ws-cell") && board.contains(el) ? el.closest(".gm-ws-cell") : null; };
    const lineTo = (a, b) => {   // straight line of cells from a to b, or null when they are not in line
        const r0 = +a.dataset.r, c0 = +a.dataset.c, r1 = +b.dataset.r, c1 = +b.dataset.c;
        const dr = r1 - r0, dc = c1 - c0;
        if (!(dr === 0 || dc === 0 || Math.abs(dr) === Math.abs(dc))) return null;
        const n = Math.max(Math.abs(dr), Math.abs(dc));
        return Array.from({ length: n + 1 }, (_, i) => cells[r0 + Math.sign(dr) * i][c0 + Math.sign(dc) * i]);
    };
    const mark = (list2, cls, on) => list2.forEach(cell => cell.classList.toggle(cls, on));

    board.addEventListener("pointerdown", (e) => {
        const cell = cellAt(e.clientX, e.clientY);
        if (!cell) return;
        e.preventDefault();
        board.setPointerCapture(e.pointerId);
        start = cell; path = [cell]; mark(path, "is-pick", true);
    });
    board.addEventListener("pointermove", (e) => {
        if (!start) return;
        const cell = cellAt(e.clientX, e.clientY);
        const line = cell && lineTo(start, cell);
        if (!line) return;
        mark(path, "is-pick", false); path = line; mark(path, "is-pick", true);
    });
    const end = () => {
        if (!start) return;
        const text = path.map(c => c.textContent).join("");
        const hit = placed.find(w => !found.has(w) && (w === text || w === [...text].reverse().join("")));
        mark(path, "is-pick", false);
        if (hit) {
            found.add(hit);
            path.forEach(c => c.classList.add("is-found", `tone-${found.size % 6}`));
            list.querySelector(`[data-word="${hit}"]`).classList.add("is-done");
            status.textContent = `Found: ${found.size} / ${placed.length}`;
            if (found.size === placed.length) {
                const seconds = Math.round((Date.now() - startedAt) / 1000);
                setTimeout(() => finish(seconds <= 90 ? 3 : seconds <= 180 ? 2 : 1, `All words in ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`), 700);
            }
        }
        start = null; path = [];
    };
    board.addEventListener("pointerup", end);
    board.addEventListener("pointercancel", end);

    const tick = setInterval(() => {
        const s = Math.floor((Date.now() - startedAt) / 1000);
        timer.textContent = `Time: ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
    }, 1000);
    stage.append(hud(status, timer, "Drag across the letters. Words run across, down or diagonally, and can be read backwards."), h("div", { class: "gm-ws-wrap" }, board, list));
    return () => clearInterval(tick);
}

// ---------- 4. Match Words ----------
function mountMatch(stage, pack, finish) {
    const pairs = shuffle(pack.match).slice(0, 5);
    let mistakes = 0, matched = 0, picked = null;
    const mistakesEl = h("span", {}, "Mistakes: 0");
    const make = (side, text, id) => h("button", { class: "gm-card", type: "button", dataset: { side, id } }, text);
    const leftCol = h("div", { class: "gm-col" }, shuffle(pairs.map((p, i) => make("a", p.a, i))));
    const rightCol = h("div", { class: "gm-col" }, shuffle(pairs.map((p, i) => make("b", p.b, i))));

    stage.addEventListener("click", (e) => {
        const card = e.target.closest(".gm-card");
        if (!card || card.disabled) return;
        if (!picked || picked.dataset.side === card.dataset.side) {   // first pick, or switching to another card on the same side
            if (picked) picked.classList.remove("is-picked");
            picked = card === picked ? null : card;
            if (picked) picked.classList.add("is-picked");
            return;
        }
        const first = picked; picked = null;
        first.classList.remove("is-picked");
        if (first.dataset.id === card.dataset.id) {
            matched += 1;
            [first, card].forEach(c => { c.disabled = true; c.classList.add("is-matched", `tone-${matched % 6}`); });
            if (matched === pairs.length) setTimeout(() => finish(mistakes <= 1 ? 3 : mistakes <= 3 ? 2 : 1, `${mistakes} ${mistakes === 1 ? "mistake" : "mistakes"}`), 800);
        } else {
            mistakes += 1;
            mistakesEl.textContent = `Mistakes: ${mistakes}`;
            [first, card].forEach(c => { c.classList.add("is-wrong"); setTimeout(() => c.classList.remove("is-wrong"), 500); });
        }
    });
    stage.append(hud(mistakesEl, "Tap a term, then tap its meaning."), h("div", { class: "gm-match" }, leftCol, rightCol));
}

// ---------- 5. Complete the sentence ----------
function mountBlanks(stage, pack, finish) {
    const items = shuffle(pack.blanks).slice(0, 4);
    const tries = h("span", {}, "Tries: 0 / 3");
    const pool = h("div", { class: "gm-pool" });
    const button = h("button", { class: "gm-btn primary", type: "button", disabled: true }, "Check");
    const slots = [];
    const refresh = () => { button.disabled = slots.some(s => !s.firstChild); };
    const placer = createPlacer((chip, zone) => {
        chip.classList.remove("is-wrong", "is-right");
        if (zone.classList.contains("gm-slot") && zone.firstChild && zone.firstChild !== chip) { const old = zone.firstChild; old.classList.remove("is-wrong"); pool.append(old); }
        zone.append(chip); refresh();
    });
    placer.zone(pool);

    const sentences = items.map(item => {
        const [before, after] = item.sentence.split("___");
        const slot = h("span", { class: "gm-slot", dataset: { answer: item.answer.toLowerCase() } });
        placer.zone(slot); slots.push(slot);
        return h("p", { class: "gm-sentence" }, before, slot, after);
    });
    shuffle(items).forEach(item => {
        const chip = h("button", { class: "gm-chip", type: "button", dataset: { answer: item.answer.toLowerCase() } }, item.answer);
        placer.chip(chip); pool.append(chip);
    });

    makeChecker({
        button, finish, onTry: (n) => { tries.textContent = `Tries: ${n} / 3`; },
        evaluate: () => slots.map(slot => ({ chip: slot.firstChild, ok: slot.firstChild.dataset.answer === slot.dataset.answer })),
        sendBack: (chip) => { pool.append(chip); refresh(); },
        reveal: () => revealInto(stage, pool, slots, "answer", "answer"),
    });
    stage.append(hud(tries, "Tap or drag each word into the sentence where it belongs."), h("div", { class: "gm-sentences" }, sentences), pool, h("div", { class: "gm-actions" }, button));
}

// ---------- 6. Math Operations ----------
// Each equation has one gap. Drag the expression whose value fits. The numbers are made here, so the games always
// work and the answers are always right, no matter what the lesson says.
const OPS = ["+", "−", "×", "÷"];
const signed = (n) => (n < 0 ? `−${-n}` : String(n));

function expressionFor(value) {
    const kinds = ["sum", "difference", "product"];
    for (let tries = 0; tries < 20; tries++) {
        const kind = pickOne(kinds);
        if (kind === "sum" && value >= 4) { const p = randInt(1, value - 1); return `(${p} + ${value - p})`; }
        if (kind === "difference") { const q = randInt(2, 30); return `(${value + q} − ${q})`; }
        if (kind === "product") {
            const factors = [];
            for (let f = 2; f <= 12; f++) if (value % f === 0 && value / f >= 2) factors.push(f);
            if (factors.length) { const f = pickOne(factors); return `(${f} × ${value / f})`; }
        }
    }
    return `(${value + 5} − 5)`;
}

function makeEquation(level) {
    const span = level >= 4 ? 60 : level >= 2 ? 40 : 25;
    const op = pickOne(OPS);
    if (op === "+") { const a = randInt(3, span), need = randInt(6, span); return { pre: `${a} +`, post: `= ${a + need}`, need }; }
    if (op === "−") { const a = randInt(10, span), need = randInt(5, span); return { pre: `${a} −`, post: `= ${signed(a - need)}`, need }; }
    if (op === "×") { const a = randInt(2, 12), need = randInt(3, 12); return { pre: `${a} ×`, post: `= ${a * need}`, need }; }
    const b = randInt(2, 12), r = randInt(2, 12);
    return { pre: "", post: `÷ ${b} = ${r}`, need: b * r };
}

function mountMathOps(stage, pack, finish) {
    const level = GameStore.level(GameStore.load().xp);
    let equations = [];
    for (let guard = 0; guard < 50 && equations.length < 4; guard++) {   // four different gap values, so every answer is unique
        const eq = makeEquation(level);
        if (!equations.some(e => e.need === eq.need)) equations.push(eq);
    }
    const needs = new Set(equations.map(e => e.need));
    const distractors = [];
    while (distractors.length < 2) {
        const value = pickOne([...needs]) + pickOne([-9, -6, -4, -3, -2, 2, 3, 4, 6, 9]);
        if (value >= 2 && !needs.has(value) && !distractors.includes(value)) distractors.push(value);
    }
    const tries = h("span", {}, "Tries: 0 / 3");
    const pool = h("div", { class: "gm-pool" });
    const button = h("button", { class: "gm-btn primary", type: "button", disabled: true }, "Check");
    const slots = [];
    const refresh = () => { button.disabled = slots.some(s => !s.firstChild); };
    const placer = createPlacer((chip, zone) => {
        chip.classList.remove("is-wrong", "is-right");
        if (zone.classList.contains("gm-slot") && zone.firstChild && zone.firstChild !== chip) { const old = zone.firstChild; old.classList.remove("is-wrong"); pool.append(old); }
        zone.append(chip); refresh();
    });
    placer.zone(pool);

    const rows = equations.map(eq => {
        const slot = h("span", { class: "gm-slot gm-slot-wide", dataset: { need: eq.need } });
        placer.zone(slot); slots.push(slot);
        return h("div", { class: "gm-equation" }, eq.pre && h("span", {}, eq.pre), slot, h("span", {}, eq.post));
    });
    shuffle([...needs, ...distractors]).forEach(value => {
        const chip = h("button", { class: "gm-chip gm-chip-math", type: "button", dataset: { value } }, expressionFor(value));
        placer.chip(chip); pool.append(chip);
    });

    makeChecker({
        button, finish, onTry: (n) => { tries.textContent = `Tries: ${n} / 3`; },
        evaluate: () => slots.map(slot => ({ chip: slot.firstChild, ok: slot.firstChild.dataset.value === slot.dataset.need })),
        sendBack: (chip) => { pool.append(chip); refresh(); },
        reveal: () => revealInto(stage, pool, slots, "value", "need"),
    });
    stage.append(hud(tries, "Work out each expression, then drop it where it makes the equation true."), h("div", { class: "gm-equations" }, rows), pool, h("div", { class: "gm-actions" }, button));
}

// ---------- 7. Word Connect ----------
function mountConnect(stage, pack, finish) {
    const usable = pack.terms.filter(t => t.word.length >= 4 && t.word.length <= 8);
    const rounds = shuffle(usable.length >= 3 ? usable : BUILTIN_PACK.terms.filter(t => t.word.length <= 8)).slice(0, 3);
    const SIZE = 260, RADIUS = 92, NODE = 28, HIT = 30;   // design units; the wheel scales with CSS
    let index = 0, solved = 0, mistakes = 0, roundMistakes = 0, answer = "", letters = [], path = [], revealed = 0, active = false, busy = false;

    const roundEl = h("span"), mistakesEl = h("span");
    const slotsEl = h("div", { class: "gm-tiles" });
    const clueEl = h("p", { class: "gm-clue" });
    const preview = h("div", { class: "gm-preview", "aria-live": "polite" });
    const svg = h("svg", { class: "gm-wheel-lines", viewBox: `0 0 ${SIZE} ${SIZE}`, "aria-hidden": "true" });
    const wheel = h("div", { class: "gm-wheel" }, svg);
    const hintBtn = h("button", { class: "gm-btn", type: "button" }, "Hint");
    const shuffleBtn = h("button", { class: "gm-btn", type: "button" }, "Shuffle");
    let nodes = [];

    const center = (i) => { const a = (Math.PI * 2 * i) / letters.length - Math.PI / 2; return [SIZE / 2 + RADIUS * Math.cos(a), SIZE / 2 + RADIUS * Math.sin(a)]; };
    const paintSlots = (fillAll = false, tone = "") => slotsEl.replaceChildren(...[...answer].map((letter, i) =>
        h("span", { class: `gm-tile${fillAll || i < revealed ? ` is-on ${tone}` : ""}` }, fillAll || i < revealed ? letter : "")));
    const paintStats = () => { roundEl.textContent = `Word ${index + 1} of ${rounds.length}`; mistakesEl.textContent = `Mistakes: ${mistakes}`; };
    const paintLines = (pointer) => {
        const pts = path.map(center); if (pointer) pts.push(pointer);
        svg.innerHTML = pts.length > 1 ? `<polyline points="${pts.map(p => p.map(n => n.toFixed(1)).join(",")).join(" ")}"/>` : "";
        nodes.forEach((node, i) => node.classList.toggle("is-on", path.includes(i)));
        preview.textContent = path.map(i => letters[i]).join("");
        preview.classList.toggle("is-empty", path.length === 0);
    };
    const scramble = () => {
        let order = shuffle([...answer]);
        for (let guard = 0; guard < 10 && order.join("") === answer; guard++) order = shuffle(order);
        letters = order;
        nodes.forEach(n => n.remove());
        nodes = letters.map((letter, i) => {
            const [x, y] = center(i);
            const node = h("div", { class: "gm-node", style: `left:${(x / SIZE) * 100}%;top:${(y / SIZE) * 100}%` }, letter);
            wheel.append(node); return node;
        });
        path = []; paintLines();
    };
    function start() {
        answer = rounds[index].word; revealed = 0; roundMistakes = 0; busy = false;
        clueEl.textContent = rounds[index].clue;
        paintSlots(); paintStats(); scramble();
    }
    const advance = (ok) => {
        busy = true;
        if (ok) solved += 1;
        setTimeout(() => {
            index += 1;
            if (index >= rounds.length) {
                const stars = solved === 0 ? 0 : solved === rounds.length ? (mistakes <= 1 ? 3 : 2) : 1;
                return finish(stars, `${solved} of ${rounds.length} words`);
            }
            start();
        }, ok ? 900 : 1600);
    };

    const toPoint = (e) => { const r = wheel.getBoundingClientRect(); return [((e.clientX - r.left) / r.width) * SIZE, ((e.clientY - r.top) / r.height) * SIZE]; };
    const nodeAt = ([x, y]) => letters.findIndex((_, i) => { const [cx, cy] = center(i); return Math.hypot(cx - x, cy - y) < HIT; });
    wheel.addEventListener("pointerdown", (e) => {
        if (busy) return;
        const hit = nodeAt(toPoint(e));
        if (hit === -1) return;
        e.preventDefault(); wheel.setPointerCapture(e.pointerId);
        active = true; path = [hit]; paintLines(toPoint(e));
    });
    wheel.addEventListener("pointermove", (e) => {
        if (!active) return;
        const point = toPoint(e), hit = nodeAt(point);
        if (hit !== -1 && !path.includes(hit)) path.push(hit);
        else if (hit !== -1 && path.length > 1 && hit === path[path.length - 2]) path.pop();   // slide back to undo the last letter
        paintLines(point);
    });
    const release = () => {
        if (!active) return;
        active = false;
        const word = path.map(i => letters[i]).join("");
        if (word.length >= 2) {
            if (word === answer) { paintSlots(true, "is-hit"); preview.classList.add("is-right"); setTimeout(() => preview.classList.remove("is-right"), 800); path = []; paintLines(); return advance(true); }
            mistakes += 1; roundMistakes += 1; paintStats();
            wheel.classList.add("is-shake"); setTimeout(() => wheel.classList.remove("is-shake"), 400);
            if (roundMistakes >= 3) { paintSlots(true, "is-missed"); path = []; paintLines(); return advance(false); }
        }
        path = []; paintLines();
    };
    wheel.addEventListener("pointerup", release);
    wheel.addEventListener("pointercancel", release);
    shuffleBtn.addEventListener("click", () => { if (!busy) scramble(); });
    hintBtn.addEventListener("click", () => { if (busy || revealed >= answer.length - 1) return; revealed += 1; mistakes += 0.5; mistakesEl.textContent = `Mistakes: ${mistakes}`; paintSlots(); });

    stage.append(hud(roundEl, mistakesEl, "Slide your finger across the letters, in order, to spell the word."), slotsEl, clueEl, preview, wheel, h("div", { class: "gm-actions" }, shuffleBtn, hintBtn));
    start();
}

// ---------- the list ----------
const GAMES = [
    { id: "sort", name: "Sort It", blurb: "Drag each idea into the group it belongs to.", mount: mountSort,
      icon: gameIcon('<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="13" width="8" height="8" rx="2"/><path d="M15 6h5M17.5 3.5 20 6l-2.5 2.5M9 18H4M6.5 15.5 4 18l2.5 2.5"/>') },
    { id: "hangman", name: "Hangman", blurb: "Guess three lesson terms before the drawing is finished.", mount: mountHangman,
      icon: gameIcon('<path d="M4 21h14M7 21V3h8v3"/><circle cx="15" cy="9" r="2.2"/><path d="M15 11.2V16M15 13l-2 2M15 13l2 2"/>') },
    { id: "wordsearch", name: "Word Search", blurb: "Find the lesson words hidden in the letter grid.", mount: mountWordSearch,
      icon: gameIcon('<circle cx="10.5" cy="10.5" r="6.5"/><path d="m20 20-4.8-4.8M8 10.5h5"/>') },
    { id: "match", name: "Match Words", blurb: "Connect each term with its meaning.", mount: mountMatch,
      icon: gameIcon('<rect x="3" y="5" width="7" height="5" rx="1.5"/><rect x="14" y="14" width="7" height="5" rx="1.5"/><path d="M10 7.5h2a2 2 0 0 1 2 2v5M14 16.5h-2"/>') },
    { id: "blanks", name: "Complete the Sentence", blurb: "Drop the missing words into the lesson sentences.", mount: mountBlanks,
      icon: gameIcon('<path d="M4 7h16M4 12h5M15 12h5M4 17h16"/><rect x="9.5" y="9.5" width="5" height="5" rx="1" stroke-dasharray="2 2"/>') },
    { id: "mathops", name: "Math Operations", blurb: "Drag the right expression into each equation.", mount: mountMathOps,
      icon: gameIcon('<path d="M5 8h6M8 5v6M14 17h6M5 17l5 0M14 6l6 0M14 9l6 0"/>') },
    { id: "connect", name: "Word Connect", blurb: "Slide across the circle of letters to spell the term.", mount: mountConnect,
      icon: gameIcon('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="6" r="1.6"/><circle cx="17.2" cy="15" r="1.6"/><circle cx="6.8" cy="15" r="1.6"/><path d="M12 6l5.2 9M17.2 15H6.8"/>') },
];
