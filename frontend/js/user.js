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
// Protects LaTeX math brackets from being deleted by the Markdown parser
function protectMath(text) {
    return text
        .replace(/\\\[/g, '\\\\[')
        .replace(/\\\]/g, '\\\\]')
        .replace(/\\\(/g, '\\\\(')
        .replace(/\\\)/g, '\\\\)');
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
        const item = document("div");
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
        if (messages.length > 0) {
            for (const m of messages) {
                addMessage(m.content, m.role === "user" ? "user" : "bot", m.images);
            }
        } else {
            showGreeting();
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
    if (!await uiConfirm("Delete this conversation? This can't be undone.", { title: "Delete conversation", okText: "Delete", danger: true })) return;
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
        input.value = pendingAuestion;
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

function addMessage(text, role, imageDataUrl) {
    const div = document.createElement("div");
    div.className = `msg ${role}`;
    
    // Parse Markdown tables/formatting
    // Change this line:
    if (role === "bot") text = stripEmoji(text);
    div.innerHTML = typeof marked !== "undefined" ? marked.parse(protectMath(text)) : text;
    
    // Tell MathJax to turn \frac and [ ] into visual math
    if (typeof MathJax !== "undefined") {
        MathJax.typesetPromise([div]).catch((err) => console.log(err));
    }

    const imageUrls = Array.isArray(imageDataUrl) ? imageDataUrl : [imageDataUrl];
    for (const imageUrl of imageUrls) {
        if (typeof imageUrl !== "string" || !/^data:image\/(?:jpeg|png|webp);base64,/.test(imageUrl)) continue;
        const img = document.createElement("img");
        img.className = "attached";
        img.src = imageUrl;
        img.alt = "Attached image";
        div.appendChild(img);
    }
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

// --- Image attachment ---
const attachImageBtn = document.getElementById("attachImageBtn");
const imageFileInput = document.getElementById("imageFileInput");
const imagePreviewRow = document.getElementById("imagePreviewRow");
const imagePreviewThumb = document.getElementById("imagePreviewThumb");
const removeImageBtn = document.getElementById("removeImageBtn");

let pendingImageDataUrl = null; // full "data:image/...;base64,...." for preview/display
let pendingImageBase64 = null;  // same, with the data: prefix stripped, for the API
let pendingImageMimeType = null;

attachImageBtn.addEventListener("click", () => imageFileInput.click());

imageFileInput.addEventListener("change", () => {
    const file = imageFileInput.files[0];
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
        uiAlert("Choose a JPEG, PNG, or WebP image.");
        imageFileInput.value = "";
        return;
    }
    const reader = new FileReader();
    reader.onload = () => {
        // Shrink big phone photos first: smaller uploads are faster and stay under the AI provider's size limit.
        const img = new Image();
        img.onload = () => {
            const MAX_SIDE = 1024;
            let dataUrl = reader.result, mime = file.type;
            if (true) {  // Always compress
                const scale = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
                const canvas = document.createElement("canvas");
                canvas.width = Math.round(img.width * scale);
                canvas.height = Math.round(img.height * scale);
                const ctx = canvas.getContext("2d");
                ctx.fillStyle = "#fff"; // JPEG has no transparency
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                dataUrl = canvas.toDataURL("image/jpeg", 0.7);
                mime = "image/jpeg";
            }
            pendingImageDataUrl = dataUrl;
            pendingImageBase64 = dataUrl.split(",")[1]; // strip "data:image/png;base64,"
            pendingImageMimeType = mime;
            imagePreviewThumb.src = pendingImageDataUrl;
            imagePreviewRow.classList.add("show");
        };
        img.onerror = () => uiAlert("Could not read that image. Try another one.");
        img.src = reader.result;
    };
    reader.readAsDataURL(file);
    imageFileInput.value = ""; // allow re-selecting the same file later
});

removeImageBtn.addEventListener("click", clearPendingImage);

function clearPendingImage() {
    pendingImageDataUrl = null;
    pendingImageBase64 = null;
    pendingImageMimeType = null;
    imagePreviewRow.classList.remove("show");
    imagePreviewThumb.src = "";
}

// Sends the question and streams the answer back token by token via
// stream-ask.js, instead of waiting for the whole response — this is what
// makes replies start appearing immediately instead of after a long pause.
async function sendQuestion() {
    const question = input.value.trim();
    if (!question) return;

    // First message in a brand-new (unsaved) chat: clear the greeting so it
    // doesn't sit above the real conversation.
    if (activeConversationId === null && chat.children.length === 1) {
        chat.innerHTML = "";
    }

    addMessage(question, "user", pendingImageDataUrl);
    const imageToSend = pendingImageBase64 ? [pendingImageBase64] : null;
    const imageTypesToSend = pendingImageMimeType ? [pendingImageMimeType] : null;
    clearPendingImage();
    input.value = "";
    sendBtn.disabled = true;

    const thinking = showDots();
    let stopPolling = null;
    let streamedText = "";
    let tokensStarted = false;

    await streamAsk(
        {
            question,
            conversation_id: activeConversationId,
            images: imageToSend,
            image_mime_types: imageTypesToSend,
        },
        {
            onMeta: (event) => {
                // Still show live queue position for the real wait between
                // "your turn is queued" and the model actually starting to
                // generate — tokens haven't started yet at this point.
                if (event.was_queued) {
                    stopPolling = startQueuePolling(thinking);
                }
                const isNewConversation = activeConversationId === null;
                activeConversationId = event.conversation_id;
                if (isNewConversation) {
                    conversations.unshift({
                        id: event.conversation_id,
                        title: event.conversation_title,
                        created_at: new Date().toISOString(),
                    });
                }
                renderSidebar();
            },
            onToken: (text) => {
                if (!tokensStarted) {
                    tokensStarted = true;
                    if (stopPolling) { stopPolling(); stopPolling = null; }
                    thinking.textContent = ""; 
                }
                streamedText += text;
                // Change this line:
                thinking.innerHTML = typeof marked !== "undefined" ? marked.parse(protectMath(streamedText)) : streamedText;
                chat.scrollTop = chat.scrollHeight;
            },
            onDone: (event) => {
                // Render the math fractions once the stream finishes
                if (typeof MathJax !== "undefined") {
                    MathJax.typesetPromise([thinking]).catch((err) => console.log(err));
                }
            },
            onError: (detail) => {
                if (stopPolling) { stopPolling(); stopPolling = null; }
                thinking.textContent = detail || "Error";
            },
        }
    );

    sendBtn.disabled = false;
    input.focus();
}