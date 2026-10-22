// Removes emoji from AI text (old saved chats, or a model slip). Math symbols like π ∑ √ ÷ are untouched.
function stripEmoji(text) {
    return String(text).replace(/\p{Extended_Pictographic}(?=\uFE0F)|[\p{Emoji_Presentation}\u{1F3FB}-\u{1F3FF}\uFE0F\u200D]/gu, "");
}

function renderFinalMessage(element, rawText) {
    if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
        element.textContent = stripEmoji(rawText);
        return;
    }

    element.innerHTML = DOMPurify.sanitize(marked.parse(stripEmoji(rawText)));
    if (typeof renderMathInElement === "function") {
        renderMathInElement(element, {
            delimiters: [
                { left: "$$", right: "$$", display: true },
                { left: "$", right: "$", display: false },
            ],
            throwOnError: false,
        });
    }
}
