const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

// Loads materials.js on a tiny fake page. `subjects` is what GET /subjects returns (null = that request fails).
function load({ subjects, files }) {
    const created = [], statics = new Map();
    const makeElement = tag => ({
        set innerHTML(html) { this.html = html; if (html === "") { this.children = []; } },   // like the real DOM: clearing it empties the list
        get innerHTML() { return this.html || ""; },
        tag, id: "", className: "", textContent: "", value: "", hidden: false, dataset: {}, children: [], options: [], listeners: {},
        append(...c) { this.children.push(...c); }, appendChild(c) { this.children.push(c); return c; },
        setAttribute() {}, addEventListener(name, cb) { this.listeners[name] = cb; }, focus() {}, querySelector() { return null; },
        add(option) { this.options.push(option); },
        replaceChildren(...items) { this.options = items; this.children = items; },
    });
    const context = {
        document: {
            getElementById(id) {
                const made = created.find(e => e.id === id);
                if (made) return made;
                if (!statics.has(id)) statics.set(id, makeElement("static"));
                return statics.get(id);
            },
            createElement(tag) { const e = makeElement(tag); created.push(e); return e; },
            querySelectorAll: () => [], addEventListener() {},
        },
        API: "http://api", localStorage: { getItem: () => "t" }, console, JSON,
        Option: function Option(text, value) { this.textContent = text; this.value = value; },
        fetch: async url => {
            if (url.endsWith("/subjects")) {
                return subjects === null ? { ok: false, status: 500, json: async () => ({}) } : { ok: true, json: async () => subjects };
            }
            if (url.endsWith("/materials")) return { ok: true, json: async () => files };
            return { ok: true, json: async () => [] };
        },
    };
    context.window = context;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../js/materials.js"), "utf8"), context);
    const select = () => created.find(e => e.id === "branchSelect");
    const shown = () => context.document.getElementById("fileList").children.filter(item => item.className.startsWith("file-item")).map(btn => btn.children[0].textContent);
    return { context, select, shown, settle: () => new Promise(resolve => setTimeout(resolve, 20)) };
}

const SUBJECTS = [
    { id: 1, name: "Mathematics in the Modern World", is_personal: false },
    { id: 2, name: "Trigonometry", is_personal: false },
    { id: 3, name: "My own topic", is_personal: true },       // a student's private subject: no teacher files belong to it
];
const FILES = [
    { filename: "a", display_name: "Lesson 1.pdf", branch: "MATHEMATICS IN THE MODERN WORLD" },   // the teacher's subject, any capitals
    { filename: "b", display_name: "Sine rule.pdf", branch: "Trigonometry" },
    { filename: "c", display_name: "Old notes.pdf", branch: "General" },                          // not a subject (any more)
];
const labels = select => select.options.map(option => option.textContent);

test("the dropdown lists the school's subjects, not a fixed list", async () => {
    const page = load({ subjects: SUBJECTS, files: FILES });
    await page.settle();
    assert.deepEqual(labels(page.select()), ["All topics", "Mathematics in the Modern World", "Trigonometry", "General"]);
    assert.ok(!labels(page.select()).includes("Calculus"));
});

test("picking a subject shows the files filed under it, whatever the capitals", async () => {
    const page = load({ subjects: SUBJECTS, files: FILES });
    await page.settle();
    page.select().value = "Mathematics in the Modern World";
    page.select().listeners.change();
    assert.deepEqual(page.shown(), ["Lesson 1.pdf"]);
    page.select().value = "All";
    page.select().listeners.change();
    assert.deepEqual(page.shown(), ["Lesson 1.pdf", "Sine rule.pdf", "Old notes.pdf"]);
});

test("a subject with no files yet is still offered, and says so", async () => {
    const page = load({ subjects: [...SUBJECTS, { id: 4, name: "Logic", is_personal: false }], files: FILES });
    await page.settle();
    assert.ok(labels(page.select()).includes("Logic"));
    page.select().value = "Logic";
    page.select().listeners.change();
    assert.deepEqual(page.shown(), []);
    assert.equal(page.context.document.getElementById("fileList").children[0].textContent, "No Logic materials yet.");
});

test("files filed under a topic that isn't a subject stay reachable", async () => {
    const page = load({ subjects: SUBJECTS, files: FILES });
    await page.settle();
    page.select().value = "General";
    page.select().listeners.change();
    assert.deepEqual(page.shown(), ["Old notes.pdf"]);
});

test("if the subjects can't be loaded the files still show, with the topics they carry", async () => {
    const page = load({ subjects: null, files: FILES });
    await page.settle();
    assert.deepEqual(labels(page.select()), ["All topics", "General", "MATHEMATICS IN THE MODERN WORLD", "Trigonometry"]);
    assert.equal(page.shown().length, 3);
});

test("a subject name with spaces doesn't become several CSS classes", async () => {
    const page = load({ subjects: SUBJECTS, files: FILES });
    await page.settle();
    const badge = page.context.document.getElementById("fileList").children[0].children[1];
    assert.equal(badge.className, "branch-badge badge-MATHEMATICS-IN-THE-MODERN-WORLD");
});
