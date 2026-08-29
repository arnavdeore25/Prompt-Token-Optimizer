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


### Core Idea

> **PromptSaver Token Optimizer — Minimum tokens required to express maximum intent.**


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
                    server.py
                        │
                        ▼
                 Ollama / Local LLM
                        │
                        ▼
                Optimized Prompt


             Chrome Local Storage
                      │
                      ▼
                Usage Statistics
```

The Chrome extension communicates with the local service through:

```text
http://127.0.0.1:8765
```

The local service communicates with the LLM running through Ollama.

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
  "validation_passed": true
}
```

## 📊 Token Measurement

The current MVP uses an **estimated token count** based on approximately four characters per token.

This means the displayed token savings are useful for comparing the original and optimized prompts, but they are **not exact tokenizer counts** for ChatGPT, Claude, or Gemini.

Future versions can add platform-specific tokenizers for more accurate measurements.


## 👨‍💻 Author

**Arnav Deore**  
MCA Student, Christ University, Bangalore
