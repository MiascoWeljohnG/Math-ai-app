const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

// Loads teacher.js against a tiny fake page. `materials` is what GET /materials returns.
function createHarness(materials) {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, {
            id, value: "", hidden: false, disabled: false, checked: false, textContent: "", className: "", files: [], style: {},
            listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; },
            replaceChildren(...children) { this.children = children; },
            append(...children) { this.children = [...(this.children || []), ...children]; },
            querySelectorAll() { return []; }, querySelector() { return null; },
        });
        return elements.get(id);
    };
    const form = element("lessonForm");
    form.elements = { lessonCount: { value: "1" }, lessonSource: { value: "library" } };
    element("lessonSubjectSelect").selectedOptions = [{ textContent: "Algebra" }];
    element("materialSubjectOnly").checked = true;
    const calls = [];
    const context = {
        document: { getElementById: element, querySelector: selector => element(`q ${selector}`), createElement: () => element(`created-${Math.random()}`), createTextNode: text => ({ textContent: text }) },
        window: { addEventListener() {} }, location: { hostname: "localhost" }, IS_LOCAL_HOST: true, API: "http://api",
        localStorage: { getItem: () => "token" }, setInterval() {}, setTimeout() {}, clearTimeout() {}, console, confirm: () => true, alert() {},
        Option: function Option(text, value) { this.textContent = text; this.value = value; },
        FormData: class { constructor() { this.entries = []; } append(...args) { this.entries.push(args); } },
        getHeaders: () => ({}), withButtonLoading: async (_b, cb) => cb(),
        loadUploadSubjects: async () => [], populateUploadSubjects() {}, renderMaterialRows() {},
        postUpload: async (url, headers, files, branch) => {
            calls.push({ upload: true, url, branch, name: files[0].name });
            return { uploaded: [{ filename: files[0].name, stored_name: `Uploaded Materials/${branch}/abc_${files[0].name}` }], needs_topic: [], message: "" };
        },
        fetch: async url => {
            calls.push({ url });
            if (url.endsWith("/materials")) return { ok: true, json: async () => materials };
            if (url.endsWith("/subjects")) return { ok: true, json: async () => [{ id: 7, name: "Algebra", is_personal: false }] };
            return { ok: true, json: async () => [] };
        },
    };
    context.globalThis = context;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../js/teacher.js"), "utf8"), context);
    return { element, calls, context };
}

const FILES = [
    { filename: "u/Algebra/1_Quadratics.pdf", display_name: "Quadratics.pdf", branch: "Algebra" },
    { filename: "u/Algebra/2_Factoring notes.docx", display_name: "Factoring notes.docx", branch: "ALGEBRA" },
    { filename: "u/Geometry/3_Circles.pdf", display_name: "Circles.pdf", branch: "Geometry" },
];
const names = select => select.children.slice(1).map(option => option.textContent);
const settle = () => new Promise(resolve => setTimeout(resolve, 20));

test("the picker lists only the selected subject's files, whatever the capitals", async () => {
    const { element } = createHarness(FILES);
    await settle();
    assert.deepEqual(names(element("materialSelect")), ["Quadratics.pdf", "Factoring notes.docx"]);
    assert.match(element("materialCount").textContent, /Showing 2 of 3/);
});

test("unticking the box shows every file, with its subject", async () => {
    const { element, context } = createHarness(FILES);
    await settle();
    element("materialSubjectOnly").checked = false;
    context.renderMaterialOptions();
    assert.equal(element("materialSelect").children.length, 4);
    assert.ok(names(element("materialSelect")).includes("Circles.pdf (Geometry)"));
});

test("search narrows the list by every word, in file name or subject", async () => {
    const { element, context } = createHarness(FILES);
    await settle();
    element("materialSearch").value = "NOTES factoring";
    context.renderMaterialOptions();
    assert.deepEqual(names(element("materialSelect")), ["Factoring notes.docx"]);
    element("materialSearch").value = "circles";   // exists, but in another subject
    context.renderMaterialOptions();
    assert.equal(element("materialSelect").children.length, 1);
    assert.match(element("materialCount").textContent, /No files match/);
});

test("a subject with no files says so and points at the checkbox", async () => {
    const { element, context } = createHarness([FILES[2]]);
    await settle();
    assert.equal(element("materialSelect").children.length, 1);
    assert.match(element("materialCount").textContent, /No files are filed under Algebra/);
});

test("the chosen file stays chosen while the search changes", async () => {
    const { element, context } = createHarness(FILES);
    await settle();
    element("materialSelect").value = "u/Algebra/1_Quadratics.pdf";
    element("materialSearch").value = "quad";
    context.renderMaterialOptions();
    assert.equal(element("materialSelect").value, "u/Algebra/1_Quadratics.pdf");
});

test("an uploaded lesson file is saved once under the subject and then used by its saved name", async () => {
    const { element, calls, context } = createHarness(FILES);
    await settle();
    context.document.getElementById("lessonForm").elements.lessonSource.value = "upload";
    element("saveLessonFile").checked = true;
    element("lessonFileInput").files = [{ name: "book.pdf" }];
    element("pageStartInput").value = "5"; element("pageEndInput").value = "9";
    const first = await context.resolveSource();
    const second = await context.resolveSource();   // pressing Generate again must not upload again
    assert.equal(calls.filter(c => c.upload).length, 1);
    assert.equal(calls.find(c => c.upload).branch, "Algebra");
    assert.deepEqual([first.file, first.filename, first.pageStart, first.pageEnd], [null, "Uploaded Materials/Algebra/abc_book.pdf", "5", "9"]);
    assert.equal(second.filename, first.filename);
});

test("without the tick the file is only read, never uploaded", async () => {
    const { element, calls, context } = createHarness(FILES);
    await settle();
    context.document.getElementById("lessonForm").elements.lessonSource.value = "upload";
    element("saveLessonFile").checked = false;
    const file = { name: "book.pdf" };
    element("lessonFileInput").files = [file];
    const source = await context.resolveSource();
    assert.equal(source.file, file);
    assert.equal(calls.filter(c => c.upload).length, 0);
});
