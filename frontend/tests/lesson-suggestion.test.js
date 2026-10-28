const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function createHarness() {
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) elements.set(id, {
            id, value: "", hidden: false, disabled: false, textContent: "", className: "", files: [],
            listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; },
            replaceChildren(...children) { this.children = children; if (this.id === "materialSelect" && children.length > 1) this.value = children[1].value; if (this.id === "lessonSubjectSelect" && children.length) this.value = children[0].value; },
            append(...children) { this.children = [...(this.children || []), ...children]; },
            set innerHTML(value) { this._innerHTML = value; if (this.id === "lessonList") this.children = [element("lessonSubjectSelect"), element("materialSelect")]; else this.children = []; },
            get innerHTML() { return this._innerHTML || ""; },
            querySelectorAll() { return []; },
        });
        return elements.get(id);
    };
    const form = element("lessonForm");
    form.elements = { lessonCount: { value: "1" }, lessonSource: { value: "library" } };
    form.addEventListener = (name, cb) => { form.listeners[name] = cb; };
    const subjectSelect = element("lessonSubjectSelect");
    subjectSelect.value = "7";
    subjectSelect.options = [];
    subjectSelect.selectedOptions = [{ textContent: "Algebra" }];
    const calls = [];
    function createElement(id) {
        if (!elements.has(id)) element(id);
        return elements.get(id);
    }
    const context = {
            document: { getElementById: element, createElement: tag => createElement(`created-${Math.random()}`), createTextNode: text => ({ textContent: text }) },
        window: { addEventListener() {} },
        location: { hostname: "localhost" },
        IS_LOCAL_HOST: true,
        API: "http://localhost:8000",
        localStorage: { getItem: () => "token" },
        Option: function Option(text, value) { this.textContent = text; this.value = value; },
        FormData: class { constructor() { this.entries = []; } append(...args) { this.entries.push(args); } },
        fetch: async (url, options = {}) => {
            calls.push({ url, options });
            if (url.endsWith("/materials")) return { ok: true, json: async () => [{ filename: "lesson.pdf", display_name: "lesson.pdf", branch: "Algebra" }] };
            if (url.endsWith("/subjects")) return { ok: true, json: async () => [{ id: 7, name: "Algebra", is_personal: false }] };
            if (url.endsWith("/suggest-from-file")) return { ok: true, json: async () => ({ title: "Fractions", description: "Compare fractions", content: "## Example" }) };
            return { ok: true, json: async () => [] };
        },
        setInterval() {}, console, confirm: () => true, alert() {},
        withButtonLoading: async (_button, callback) => callback(),
    };
    context.globalThis = context;
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../js/teacher.js"), "utf8"), context);
    context.activeLessonSubjectId = 7;
    return { elements, calls, context, element };
}

test("selected uploaded file suggestion fills editable lesson fields without saving", async () => {
    const { elements, calls, context, element } = createHarness();
    await new Promise(resolve => setTimeout(resolve, 50));
    const select = elements.get("materialSelect");
    select.value = "lesson.pdf";
    const subjectSelect = element("lessonSubjectSelect");
    subjectSelect.value = "7";
    assert.equal(context.activeLessonSubjectId, 7);
    await context.suggestLessonFromMaterial();
    assert.equal(calls.some(call => call.url.includes("/lessons/suggest-from-file")), true);
    const request = calls.find(call => call.url.endsWith("/suggest-from-file"));
    assert.deepEqual(request.options.body.entries, [["filename", "lesson.pdf"]]);
    assert.equal(elements.get("lessonTitleInput").value, "Fractions");
    assert.equal(elements.get("lessonDescriptionInput").value, "Compare fractions");
    assert.equal(elements.get("lessonContentInput").value, "## Example");
    assert.equal(elements.get("lessonContentField").hidden, false);
    assert.equal(elements.get("saveBtn").hidden, true);
});
