# PromptSaver Token Optimizer

> **Minimum tokens required to express maximum intent.**

PromptSaver Token Optimizer is a **Manifest V3 Chrome extension** that uses a **locally running LLM** to optimize AI prompts. It rewrites messy, repetitive, or unnecessarily long prompts to make them more concise while preserving their original meaning, requirements, and intent.

## ✨ Features

- 🤖 **Local LLM-powered optimization** — prompts are processed using a model running on your computer.
- 🌐 **Multi-platform support** — works with ChatGPT, Claude, and Gemini.
- ✂️ **Prompt compression** — removes unnecessary wording, repetition, and conversational filler.
- 🧠 **Intent preservation** — designed to preserve requirements, constraints, technical details, and important context.
- 📊 **Token statistics** — shows estimated original tokens, optimized tokens, tokens saved, and percentage reduction.
- 🔒 **Local-first privacy** — prompts are sent to a local service rather than a PromptSaver cloud backend.
- 💾 **Local usage tracking** — optimization statistics are stored using Chrome's local storage.

## 🧩 Supported Websites

The extension currently supports:

- `chatgpt.com`
- `chat.openai.com`
- `claude.ai`
- `gemini.google.com`

## 🏗️ Architecture

```text
                Supported AI Website
                        │
                        ▼
                   content.js
                        │
                        ▼
                  background.js
                        │
                        ▼
              ┌─────────────────┐
              │  server.py      │
              │  POST /optimize │
              └─────────────────┘
                        │
                        ▼
              ┌─────────────────────────┐
              │  Fast Local Check       │
              │  (should_optimize?)     │
              │  - Token estimate       │
              │  - Filler detection     │
              │  - Repetition check     │
              │  - Scoring heuristics   │
              └─────────────────────────┘
                        │
              ┌─────────┴─────────┐
              │                   │
           Score < 3          Score >= 3
              │                   │
              ▼                   ▼
         Return Original      Call Ollama
         (Skip Ollama)            │
              │                   ▼
              │         ┌──────────────────┐
              │         │  LLM Optimization│
              │         │  (with System    │
              │         │   Prompt)        │
              │         └──────────────────┘
              │                   │
              └─────────┬─────────┘
                        ▼
              ┌─────────────────────────┐
              │  Validation             │
              │  - Preserve code blocks │
              │  - Preserve URLs        │
              │  - Preserve numbers     │
              │  - Preserve negations   │
              └─────────────────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │  Response with Metadata      │
         │  - optimized prompt          │
         │  - token counts & savings    │
         │  - validation status         │
         │  - optimization skip reason  │
         │  - model used                │
         └──────────────────────────────┘
                        │
                        ▼
                  background.js
                        │
                        ▼
             Chrome Local Storage
                      │
                      ▼
                Usage Statistics
```

### Component Details

**content.js** — Runs on supported AI websites, injects the optimize button, and sends prompts to the background script.

**background.js** — Forwards optimization requests from content.js to the local server via `http://127.0.0.1:8765/optimize`.

**server.py** — Implements three key stages:
1. **Fast Local Check** — Heuristic scoring determines if Ollama optimization is worthwhile
2. **Ollama Integration** — Calls local LLM only for prompts scoring ≥ 3
3. **Validation** — Ensures critical elements (code, URLs, numbers, negations) are preserved

**Ollama / Local LLM** — Processes the prompt using the specified model (default: `qwen2.5:3b`) with a fine-tuned system prompt.

## 📁 Project Structure

```text
PromptSaver-Token-Optimizer/
│
├── extension/
│   ├── background.js    # Forwards optimization requests
│   ├── content.js       # Runs on supported AI websites
│   ├── content.css      # In-page extension styles
│   ├── manifest.json    # Chrome extension configuration
│   ├── popup.html       # Extension popup
│   ├── popup.js         # Health status and usage statistics
│   ├── popup.css        # Popup styles
│   ├── icon16.svg       # Extension icon
│   ├── icon48.svg       # Extension icon
│   └── icon128.svg      # Extension icon
│
├── server/
│   ├── server.py        # Local API and Ollama integration
│   ├── run.bat          # Windows startup script
│   └── run.sh           # Linux/macOS startup script
│
├── .gitignore
├── .gitattributes
└── README.md
```

## 🧪Output Example

A messy prompt:

```text
hey basically i want you to make a login page for my react
project and it should have username and password and if the
password is wrong then show an error and i don't want to use
a database because this is just a prototype and after the
user logs in i want them to go to the home page and there
should also be a logout button and make it look good and
responsive
```

PromptToken Optimizer can transform it into a more concise prompt such as:

```text
Create a responsive React login page with:

- Username and password authentication
- Validation and error messages
- Local/object-based credentials; no database
- Redirect to the home page after login
- Logout functionality
- Clean, modern UI
```

The goal is **not simply to make prompts shorter**. The goal is to remove unnecessary tokens while preserving the user's actual requirements.

## 🔌 Local Service API

The extension expects the local service to expose the following endpoints.

### `GET /health`

Used by the extension to check whether the local service and model are available.

Example response:

```json
{
  "ok": true,
  "model": "qwen2.5:3b"
}
```

### `POST /optimize`

The extension sends:

```json
{
  "prompt": "The prompt to optimize"
}
```

The service returns:

```json
{
  "optimized": "The optimized prompt",
  "model": "qwen2.5:3b",
  "original_tokens": 120,
  "optimized_tokens": 82,
  "tokens_saved": 38,
  "reduction_percent": 31.7,
  "validation_passed": true,
  "optimization_skipped": false
}
```

**Note:** If the prompt is already concise (score < 3 on heuristics), the service returns:

```json
{
  "optimized": "The prompt (unchanged)",
  "original_tokens": 45,
  "optimized_tokens": 45,
  "tokens_saved": 0,
  "reduction_percent": 0,
  "model": "none",
  "validation_passed": true,
  "optimization_skipped": true,
  "reason": "Prompt is already concise. Ollama was not called."
}
```

## 📊 Token Measurement

The current MVP uses an **estimated token count** based on approximately four characters per token.

This means the displayed token savings are useful for comparing the original and optimized prompts, but they are **not exact tokenizer counts** for ChatGPT, Claude, or Gemini.

Future versions can add platform-specific tokenizers for more accurate measurements.


## 👨‍💻 Author

**Arnav Deore**  
MCA Student, Christ University, Bangalore
