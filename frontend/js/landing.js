const landingInput = document.getElementById("landingInput");
const startChattingBtn = document.getElementById("startChattingBtn");

// --- Progress bars ---
// There's no real lesson-tracking system yet, so these percentages come
// from the backend's deterministic mock data (see backend/progress.py) —
// consistent per student, but not tied to actual completed lessons.
async function loadProgress() {
    try {
        const res = await fetch(`${API}/progress`, {
            headers: { "Authorization": `Bearer ${localStorage.getItem("token")}` },
        });
        if (!res.ok) return;
        const progress = await res.json(); // [{branch, percent}, ...]

        document.querySelectorAll(".tile").forEach(tile => {
            const branch = tile.dataset.branch;
            const entry = progress.find(p => p.branch === branch);
            const pct = entry ? entry.percent : 0;
            tile.querySelector(".tile-progress-fill").style.width = `${pct}%`;
            tile.querySelector(".tile-progress-pct").textContent = `${pct}% complete`;
        });
    } catch (_) {
        document.querySelectorAll(".tile-progress-pct").forEach(el => el.textContent = "");
    }
}
loadProgress();

// --- Tiles: each branch opens a fresh chat nudged toward that topic ---
// There's no real per-branch content filtering in the AI yet (it searches
// the whole shared knowledge base either way) — this just seeds the first
// message so the conversation starts on-topic.
document.querySelectorAll(".tile").forEach(tile => {
    tile.addEventListener("click", () => {
        const branch = tile.dataset.branch;
        sessionStorage.setItem("landingPendingQuestion", `I'd like to practice ${branch}. Can you help me get started?`);
        window.location.href = "user.html";
    });
});

// --- "Ask anything" bar ---
function goToChat() {
    const question = landingInput.value.trim();
    if (question) {
        sessionStorage.setItem("landingPendingQuestion", question);
    }
    window.location.href = "user.html";
}

startChattingBtn.addEventListener("click", goToChat);
landingInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
        e.preventDefault();
        goToChat();
    }
});
landingInput.addEventListener("click", (e) => e.stopPropagation());
