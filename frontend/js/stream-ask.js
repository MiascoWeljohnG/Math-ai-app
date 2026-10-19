// Shared NDJSON stream reader for POST /ask, used by both the main chat
// (user.js) and the materials-viewer side panel (materials.js) so the
// line-buffering/parsing logic for a streamed response lives in one place
// instead of being copy-pasted and drifting between the two.
//
// payload: the request body (question, conversation_id, etc.)
// callbacks: { onMeta(event), onToken(text), onDone(event), onError(detail) }
async function streamAsk(payload, { onMeta, onToken, onDone, onError } = {}) {
    let res;
    try {
        res = await fetch(`${API}/ask`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${localStorage.getItem("token")}`,
            },
            body: JSON.stringify(payload),
        });
    } catch (err) {
        if (onError) onError(`Network error: ${err.message}`);
        return;
    }

    if (!res.ok) {
        let detail = "Error";
        try { detail = (await res.json()).detail || detail; } catch (_) { /* body wasn't JSON */ }
        if (onError) onError(detail);
        return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
        let chunk;
        try {
            chunk = await reader.read();
        } catch (err) {
            if (onError) onError(`Connection lost: ${err.message}`);
            return;
        }
        if (chunk.done) break;
        buffer += decoder.decode(chunk.value, { stream: true });

        let newlineIndex;
        while ((newlineIndex = buffer.indexOf("\n")) !== -1) {
            const line = buffer.slice(0, newlineIndex).trim();
            buffer = buffer.slice(newlineIndex + 1);
            if (!line) continue;

            let event;
            try {
                event = JSON.parse(line);
            } catch (_) {
                continue; // a malformed line shouldn't kill the whole stream
            }

            if (event.type === "meta" && onMeta) onMeta(event);
            else if (event.type === "token" && onToken) onToken(stripEmoji(event.text));
            else if (event.type === "done" && onDone) onDone(event);
            else if (event.type === "error" && onError) onError(event.detail);
        }
    }
}
