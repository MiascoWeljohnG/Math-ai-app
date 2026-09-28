const chat = document.getElementById("chat");
const input = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");
const convoList = document.getElementById("convoList");
const newChatBtn = document.getElementById("newChatBtn");

// Currently open conversation. null = "new chat" not yet saved to the
// server (it gets created automatically the moment the first message is
// sent — see sendQuestion()).
let activeConversationId = null;
let conversations = []; // [{id, title, created_at}, ...] most recent first

function authHeaders() {
    return {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${localStorage.getItem("token")}`,
    };
}

// --- Sidebar: conversation list ---
async function loadConversations() {
    try {
        const res = await fetch(`${API}/conversations`, { headers: authHeaders() });
        if (!res.ok) return;
        conversations = await res.json();
        renderSidebar();
    } catch (_) { /* sidebar just stays empty if this fails */ }
}

function renderSidebar() {
    convoList.innerHTML = "";
    if (conversations.length === 0) {
        const empty = document.createElement("div");
        empty.className = "sidebar-empty";
        empty.textContent = "No conversations yet";
        convoList.appendChild(empty);
        return;
    }
    for (const c of conversations) {
        const item = document.createElement("div");
        item.className = "convo-item" + (c.id === activeConversationId ? " active" : "");
        item.innerHTML = `<span class="title">${escapeHtml(c.title)}</span><button class="del-btn" title="Delete">&times;</button>`;
        item.querySelector(".title").addEventListener("click", () => openConversation(c.id));
        item.querySelector(".del-btn").addEventListener("click", (e) => {
            e.stopPropagation();
            deleteConversation(c.id);
        });
        convoList.appendChild(item);
    }
}

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

async function openConversation(id) {
    activeConversationId = id;
    renderSidebar();
    chat.innerHTML = "";

    try {
        const res = await fetch(`${API}/conversations/${id}/messages`, { headers: authHeaders() });
        if (!res.ok) return;
        const messages = await res.json();
        if (messages.length === 0) {
            showGreeting();
        } else {
            for (const m of messages) {
                addMessage(m.content, m.role === "user" ? "user" : "bot");
            }
        }
    } catch (_) {
        showGreeting();
    }
}

function startNewChat() {
    activeConversationId = null;
    chat.innerHTML = "";
    showGreeting();
    renderSidebar();
    input.focus();
}
newChatBtn.addEventListener("click", startNewChat);

async function deleteConversation(id) {
    if (!confirm("Delete this conversation? This can't be undone.")) return;
    try {
        const res = await fetch(`${API}/conversations/${id}`, {
            method: "DELETE",
            headers: authHeaders(),
        });
        if (!res.ok) return;
        conversations = conversations.filter(c => c.id !== id);
        if (activeConversationId === id) {
            startNewChat();
        } else {
            renderSidebar();
        }
    } catch (_) { /* ignore */ }
}

// --- Greeting ---
function showGreeting() {
    const div = document.createElement("div");
    div.className = "msg bot";
    const username = localStorage.getItem("username") || "there";
    div.textContent = `Hi ${username}! I'm your math assistant. Ask me anything — a problem, a concept, or just say hi!`;
    chat.appendChild(div);
}

// --- Initial load: restore the last-open conversation, or show the greeting
// if this account has none yet. Because history lives on the server, this
// works the same after a refresh or a fresh login. ---
(async function init() {
    // A question typed into the landing page's "Ask anything" bar arrives
    // here as a one-shot handoff — start a fresh conversation with it
    // immediately instead of loading whatever chat was open last.
    const pendingQuestion = sessionStorage.getItem("landingPendingQuestion");
    if (pendingQuestion) {
        sessionStorage.removeItem("landingPendingQuestion");
        await loadConversations();
        startNewChat();
        input.value = pendingQuestion;
        sendQuestion();
        return;
    }

    await loadConversations();
    if (conversations.length > 0) {
        openConversation(conversations[0].id);
    } else {
        showGreeting();
    }
})();

// Allow Enter key to send
input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
    }
});

function addMessage(text, role) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    div.textContent = text;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

function showDots() {
    const div = document.createElement("div");
    div.className = "msg bot";
    div.innerHTML = `<span class="dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>`;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

// While the request is queued behind other students, poll for how many are
// ahead and show it instead of a silent set of bouncing dots. There's no
// streaming yet, so this is the cheapest way to give real feedback.
function startQueuePolling(thinkingDiv) {
    let stopped = false;
    const dotsHTML = `<span class="dots"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>`;

    const poll = async () => {
        if (stopped) return;
        try {
            const res = await fetch(`${API}/queue-status`, { headers: authHeaders() });
            if (res.ok) {
                const data = await res.json();
                thinkingDiv.innerHTML = data.waiting > 0
                    ? `${data.waiting} student${data.waiting > 1 ? "s" : ""} ahead of you, hang tight...`
                    : dotsHTML;
                chat.scrollTop = chat.scrollHeight;
            }
        } catch (_) { /* ignore transient polling errors */ }
    };

    poll();
    const interval = setInterval(poll, 1200);
    return () => { stopped = true; clearInterval(interval); };
}

async function sendQuestion() {
    const question = input.value.trim();
    if (!question) return;

    // First message in a brand-new (unsaved) chat: clear the greeting so it
    // doesn't sit above the real conversation.
    if (activeConversationId === null && chat.children.length === 1) {
        chat.innerHTML = "";
    }

    addMessage(question, "user");
    input.value = "";
    sendBtn.disabled = true;

    const thinking = showDots();
    const stopPolling = startQueuePolling(thinking);

    try {
        const res = await fetch(`${API}/ask`, {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({
                question: question,
                conversation_id: activeConversationId,
            }),
        });

        stopPolling();
        const data = await res.json();

        if (!res.ok) {
            thinking.textContent = data.detail || "Error";
            return;
        }

        thinking.textContent = data.answer;

        // A brand-new chat just got its server-side conversation created on
        // this first message — add it to the sidebar now.
        const isNewConversation = activeConversationId === null;
        activeConversationId = data.conversation_id;
        if (isNewConversation) {
            conversations.unshift({
                id: data.conversation_id,
                title: data.conversation_title,
                created_at: new Date().toISOString(),
            });
        }
        renderSidebar();

    } catch (err) {
        stopPolling();
        thinking.textContent = `Network error: ${err.message}`;
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}
