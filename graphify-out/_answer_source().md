---
source_file: "backend/rag.py"
type: "code"
community: "Retrieval Augmented Generation"
location: "L176"
tags:
  - graphify/code
  - graphify/EXTRACTED
  - community/Retrieval_Augmented_Generation
---

# _answer_source()

## Connections
- [[Yields (text, finish_reason). Attempts Groq - Gemini - Ollama fallback chain.]] - `rationale_for` [EXTRACTED]
- [[_gemini_stream()]] - `calls` [EXTRACTED]
- [[_groq_stream()]] - `calls` [EXTRACTED]
- [[_ollama_stream()]] - `calls` [EXTRACTED]
- [[_use_groq()]] - `calls` [EXTRACTED]
- [[ask_stream()]] - `calls` [EXTRACTED]
- [[rag.py]] - `contains` [EXTRACTED]

#graphify/code #graphify/EXTRACTED #community/Retrieval_Augmented_Generation