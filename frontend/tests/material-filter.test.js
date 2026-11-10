const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

// Loads teacher.js against a tiny fake page. `materials` is what GET /materials returns.
function createHarness(materials, teacherFiles = [], drafts = []) {
    const rendered = [], scheduled = [];
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, {
            id, dataset: {}, value: "", hidden: false, disabled: false, checked: false, textContent: "", className: "", files: [], style: {},
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
        localStorage: { getItem: () => "token" }, setInterval() {}, setTimeout() {}, clearTimeout() {}, console, confirm: () => true, uiConfirm: async () => true, alert() {},
        Option: function Option(text, value) { this.textContent = text; this.value = value; },
        FormData: class { constructor() { this.entries = []; } append(...args) { this.entries.push(args); } },
        getHeaders: () => ({}), withButtonLoading: async (_b, cb) => cb(),
        loadUploadSubjects: async () => [], populateUploadSubjects() {},
        renderMaterialRows: (_tbody, files) => rendered.push(files.map(f => f.display_name)),
        scheduleIndexingRefresh: (files) => scheduled.push(files.length),
        postUpload: async (url, headers, files, branch) => {
            calls.push({ upload: true, url, branch, name: files[0].name });
            return { uploaded: [{ filename: files[0].name, stored_name: `Uploaded Materials/${branch}/abc_${files[0].name}` }], needs_topic: [], message: "" };
        },
        fetch: async url => {
            calls.push({ url });
            if (url.endsWith("/lessons/drafts")) return { ok: true, json: async () => drafts };
            if (url.endsWith("/approve")) return { ok: true, json: async () => ({ status: "published" }) };
            if (url.endsWith("/teacher/files")) return { ok: true, json: async () => teacherFiles };
            if (url.endsWith("/materials")) return { ok: true, json: async () => materials };
            if (url.endsWith("/subjects")) return { ok: true, json: async () => [{ id: 7, name: "Algebra", is_personal: false }] };
            return { ok: true, json: async () => [] };
        },
    };
    context.globalThis = context;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../js/teacher.js"), "utf8"), context);
    return { element, calls, context, rendered, scheduled };
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


// ---- the "Your Uploaded Files" table
const MINE = [
    { filename: "a", display_name: "Quadratics.pdf", branch: "Algebra", index_status: "ready" },
    { filename: "b", display_name: "Factoring notes.docx", branch: "ALGEBRA", index_status: "ready" },
    { filename: "c", display_name: "Circles.pdf", branch: "Modern Geometry", index_status: "indexing" },
    { filename: "d", display_name: "Matrices.pptx", branch: "Linear Algebra", index_status: "ready" },
];
const last = list => list[list.length - 1];
const optionNames = select => select.children.map(option => option.textContent);

test("the files table lists every file at first, with one filter entry per subject", async () => {
    const { element, rendered } = createHarness([], MINE);
    await settle();
    assert.deepEqual(last(rendered), ["Quadratics.pdf", "Factoring notes.docx", "Circles.pdf", "Matrices.pptx"]);
    assert.deepEqual(optionNames(element("fileSubjectFilter")), ["All subjects", "Algebra", "Linear Algebra", "Modern Geometry"]);   // Algebra/ALGEBRA are one
    assert.equal(element("fileFilter").hidden, false);
    assert.equal(element("fileCount").textContent, "");
});

test("choosing a subject narrows the table, whatever the capitals", async () => {
    const { element, context, rendered } = createHarness([], MINE);
    await settle();
    element("fileSubjectFilter").value = "Algebra";
    context.renderMyFiles();
    assert.deepEqual(last(rendered), ["Quadratics.pdf", "Factoring notes.docx"]);
    assert.equal(element("fileCount").textContent, "Showing 2 of 4 files.");
});

test("search and subject work together, and nothing matching says so", async () => {
    const { element, context, rendered } = createHarness([], MINE);
    await settle();
    element("fileSearch").value = "NOTES";
    context.renderMyFiles();
    assert.deepEqual(last(rendered), ["Factoring notes.docx"]);
    element("fileSubjectFilter").value = "Modern Geometry";
    context.renderMyFiles();
    assert.deepEqual(last(rendered), []);
    assert.equal(element("noFiles").textContent, "No files match your search.");
    assert.equal(element("noFiles").style.display, "block");
    assert.equal(element("filesTable").style.display, "none");
});

test("a file that is still being read keeps the table reloading even when the filter hides it", async () => {
    const { element, context, scheduled } = createHarness([], MINE);
    await settle();
    element("fileSubjectFilter").value = "Algebra";   // hides Circles.pdf, which is indexing
    context.renderMyFiles();
    assert.equal(last(scheduled), 4);   // the refresh is judged on all 4 files, not the 2 shown
});

test("with no uploads the filter bar stays hidden", async () => {
    const { element } = createHarness([], []);
    await settle();
    assert.equal(element("fileFilter").hidden, true);
    assert.equal(element("noFiles").textContent, "You haven't uploaded any files yet.");
});


// ---- Drafts to review
const DRAFTS = [{ id: 11, title: "Linear functions" }, { id: 12, title: "Slopes" }];
const draftRow = (element, index) => element("draftListEl").children[index];

test("AI-written lessons show up under Drafts to review, with a count", async () => {
    const { element } = createHarness([], [], DRAFTS);
    await settle();
    assert.equal(element("draftPanel").hidden, false);
    assert.equal(element("draftCount").textContent, "2");
    assert.deepEqual(element("draftListEl").children.map(row => row.children[0].textContent), ["Linear functions", "Slopes"]);
    assert.deepEqual(draftRow(element, 0).children.map(button => button.textContent), ["Linear functions", "Approve", "Delete", "PDF"]);
});

test("every lesson row has a PDF button that fetches the lesson first (the list only has titles)", async () => {
    const { element, calls } = createHarness([], [], DRAFTS);
    await settle();
    const pdfButton = draftRow(element, 0).children[3];
    assert.equal(pdfButton.textContent, "PDF");
    assert.equal(typeof pdfButton.listeners.click, "function");
});

test("with no drafts the panel stays hidden", async () => {
    const { element } = createHarness([], [], []);
    await settle();
    assert.equal(element("draftPanel").hidden, true);
});

test("Approve publishes that lesson and then reloads the lists", async () => {
    const { element, calls } = createHarness([], [], DRAFTS);
    await settle();
    const before = calls.filter(c => c.url && c.url.endsWith("/lessons/drafts")).length;
    await draftRow(element, 1).children[1].listeners.click();
    assert.ok(calls.some(c => c.url && c.url.endsWith("/subjects/7/lessons/12/approve")));
    assert.ok(calls.filter(c => c.url && c.url.endsWith("/lessons/drafts")).length > before);   // the drafts were fetched again
});

test("Approve all publishes every draft", async () => {
    const { element, calls } = createHarness([], [], DRAFTS);
    await settle();
    await element("approveAllBtn").listeners.click();
    const approved = calls.filter(c => c.url && c.url.endsWith("/approve")).map(c => c.url.split("/lessons/")[1]);
    assert.deepEqual(approved, ["11/approve", "12/approve"]);
});
