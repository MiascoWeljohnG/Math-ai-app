const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const API = "https://isipnayan.onrender.com";

// Loads auth.js on a tiny fake page. `answer.status` is what the fake server replies to every request.
function load({ token = "t" } = {}) {
    const created = [], replaced = [], store = new Map(token ? [["token", token], ["role", "teacher"], ["username", "teach"]] : []);
    const answer = { status: 200 };
    const element = tag => ({
        tag, children: [], attrs: {}, listeners: {}, className: "", textContent: "", id: "", dataset: {},
        append(...c) { this.children.push(...c); }, appendChild(c) { this.children.push(c); return c; },
        setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(n, cb) { this.listeners[n] = cb; },
        showModal() { this.opened = true; }, focus() {},
    });
    const context = {
        document: {
            body: element("body"), head: element("head"), getElementById: () => null, querySelectorAll: () => [], addEventListener() {},
            createElement(tag) { const e = element(tag); created.push(e); return e; },
        },
        location: { hostname: "isipnayan.vercel.app", search: "", replace: url => replaced.push(url), href: "" },
        localStorage: { getItem: k => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: k => store.delete(k) },
        fetch: async () => ({ status: answer.status }),
        Headers, Request, URLSearchParams, console,
    };
    context.window = context;   // like a browser: window.fetch IS the global fetch
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../js/auth.js"), "utf8"), context);
    const dialogs = () => created.filter(e => e.tag === "dialog");
    return { context, answer, created, replaced, store, dialogs };
}
const signedIn = { headers: { Authorization: "Bearer t" } };

test("a 401 on a signed-in call to our API opens the session-expired popup", async () => {
    const { context, answer, dialogs } = load();
    answer.status = 401;
    await context.fetch(`${API}/teacher/files`, signedIn);
    assert.equal(dialogs().length, 1);
    assert.equal(dialogs()[0].opened, true);
    const text = JSON.stringify(dialogs()[0]);
    assert.match(text, /Your session has expired/);
    assert.match(text, /Log in again/);
});

test("many requests failing at once still show the popup only once", async () => {
    const { context, answer, dialogs } = load();
    answer.status = 401;
    await Promise.all([1, 2, 3, 4, 5].map(() => context.fetch(`${API}/materials`, signedIn)));
    assert.equal(dialogs().length, 1);
});

test("a wrong password at sign-in (a 401 with no login token sent) does not trigger it", async () => {
    const { context, answer, dialogs } = load({ token: null });
    answer.status = 401;
    await context.fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" } });
    assert.equal(dialogs().length, 0);
});

test("a stale token left in storage doesn't make a failed sign-in show the popup either", async () => {
    const { context, answer, dialogs } = load();   // a token is stored, but the login call doesn't send it
    answer.status = 401;
    await context.fetch(`${API}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" } });
    assert.equal(dialogs().length, 0);
});

test("a 401 from some other website, or any other status from ours, is ignored", async () => {
    const { context, answer, dialogs } = load();
    answer.status = 401;
    await context.fetch("https://example.com/data", signedIn);
    answer.status = 500;
    await context.fetch(`${API}/materials`, signedIn);
    answer.status = 403;
    await context.fetch(`${API}/materials`, signedIn);
    assert.equal(dialogs().length, 0);
});

test("the response still reaches the page that asked for it", async () => {
    const { context, answer } = load();
    answer.status = 401;
    const response = await context.fetch(`${API}/materials`, signedIn);
    assert.equal(response.status, 401);   // the page's own error handling keeps working
});

test("'Log in again' clears the session and goes to the login page", async () => {
    const { context, answer, created, replaced, store } = load();
    answer.status = 401;
    await context.fetch(`${API}/materials`, signedIn);
    const button = created.find(e => e.tag === "button");
    button.listeners.click();
    assert.deepEqual(replaced, ["login.html"]);
    assert.equal(store.has("token"), false);
});

test("Esc can't dismiss the popup", async () => {
    const { context, answer, dialogs } = load();
    answer.status = 401;
    await context.fetch(`${API}/materials`, signedIn);
    let prevented = false;
    dialogs()[0].listeners.cancel({ preventDefault() { prevented = true; } });
    assert.equal(prevented, true);
});
