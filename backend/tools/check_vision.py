"""Try the figure-reading vision models on one picture, using the settings in backend/.env.

    python tools/check_vision.py diagram.png

It asks Groq (if GROQ_VISION_MODEL is set) and the Ollama reserve (if OLLAMA_BASE_URL and OLLAMA_VISION_MODEL are set)
separately and prints each answer with how long it took, so you can see that the tunnel and the model really work.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import config  # noqa: E402  (also loads .env)
import figures  # noqa: E402
from PIL import Image  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    png = figures._png(Image.open(sys.argv[1]))
    tests = []
    if figures._groq_on():
        tests.append((f"Groq: {config.GROQ_VISION_MODEL}", figures._describe_groq))
    if figures._ollama_on():
        tests.append((f"Ollama: {config.OLLAMA_VISION_MODEL} at {config.OLLAMA_BASE_URL}", figures._describe_ollama))
    if not tests:
        print("Nothing is set up. Set GROQ_VISION_MODEL (with GROQ_API_KEY) and/or OLLAMA_BASE_URL + OLLAMA_VISION_MODEL in backend/.env.")
        return 1
    for name, ask in tests:
        started = time.time()
        text = ask(png)
        took = time.time() - started
        print(f"\n{name}  ({took:.1f}s)")
        print("  ->", "FAILED or unavailable (see the warning above)" if text is None else (text or "(nothing to describe)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
