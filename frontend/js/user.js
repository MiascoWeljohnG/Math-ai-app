const chat = document.getElementById("chat");
const input = document.getElementById("questionInput");
const sendBtn = document.getElementById("sendBtn");

// Store conversation history
let chatHistory = [];

// --- Greeting on page load ---
function showGreeting() {
    const div = document.createElement("div");
    div.className = "msg bot";
    const username = localStorage.getItem("username") || "there";
    div.textContent = `Hi ${username}! I'm your math assistant. Ask me anything — a problem, a concept, or just say hi!`;
    chat.appendChild(div);
}
showGreeting();

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
            const res = await fetch(`${API}/queue-status`, {
                headers: { "Authorization": `Bearer ${localStorage.getItem("token")}` },
            });
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

    addMessage(question, "user");
    input.value = "";
    sendBtn.disabled = true;

    chatHistory.push({ role: "user", content: question });

    const thinking = showDots();
    const stopPolling = startQueuePolling(thinking);

    try {
        const res = await fetch(`${API}/ask`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${localStorage.getItem("token")}`,
            },
            body: JSON.stringify({
                question: question,
                history: chatHistory.slice(0, -1),
            }),
        });

        stopPolling();
        const data = await res.json();

        if (res.status === 503) {
            // Ollama is genuinely overloaded/timed out — distinct from a real error.
            thinking.textContent = `${data.detail || "The AI is busy right now. Please try again in a moment."}`;
            chatHistory.pop();
            return;
        }

        if (!res.ok) {
            thinking.textContent = ` ${data.detail || "Error"}`;
            chatHistory.pop();
            return;
        }

        thinking.textContent = data.answer;
        chatHistory.push({ role: "assistant", content: data.answer });

    } catch (err) {
        stopPolling();
        thinking.textContent = ` Network error: ${err.message}`;
        chatHistory.pop();
    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}   