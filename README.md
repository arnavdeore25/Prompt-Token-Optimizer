# Prompt Token Optimizer

Prompt Token Optimizer is a local, privacy-first Chrome extension that shortens messy AI prompts while keeping the original intent, constraints, and technical details intact.

It works by sending the prompt to a local Python service, which checks whether optimization is worth doing, optionally calls an Ollama model, and validates that important content such as URLs, numbers, negations, and code blocks is preserved.

## Features

- Local prompt optimization through Ollama
- Chrome extension for supported AI sites
- Fast heuristic check before LLM usage
- Validation step to preserve key prompt details
- Token savings and reduction stats
- No cloud dependency for prompt rewriting
- Local usage tracking in Chrome storage

## Supported sites

The extension is configured for:

- https://chatgpt.com/
- https://chat.openai.com/
- https://claude.ai/
- https://gemini.google.com/

## How it works

1. The user selects or pastes a prompt in a supported AI website.
2. The content script sends the prompt to the extension background worker.
3. The background worker sends a POST request to the local service at http://127.0.0.1:8765/optimize.
4. The Python server runs a fast local heuristic check.
5. If the prompt is long or noisy enough, it calls the configured local model through Ollama.
6. The optimized result is validated and returned with metadata such as original tokens, optimized tokens, and savings.

## Architecture

```text
Browser AI site
      │
      ▼
content.js
      │
      ▼
background.js
      │
      ▼
Python local server (server.py)
      │
      ├─ fast local heuristic check
      ├─ Ollama model request
      └─ validation before returning result
      │
      ▼
Local model via Ollama
```

## Project structure

```text
Prompt-Token-Optimizer/
├── extension/
│   ├── background.js
│   ├── content.css
│   ├── content.js
│   ├── icon16.svg
│   ├── icon48.svg
│   ├── icon128.svg
│   ├── manifest.json
│   ├── popup.css
│   ├── popup.html
│   └── popup.js
├── server/
│   ├── run.bat
│   ├── run.sh
│   └── server.py
├── README.md
└── .gitignore
```

## Prerequisites

Before using the extension, install and run Ollama on your machine.

Example:

```bash
ollama pull qwen2.5:3b
```

The default model is qwen2.5:3b, but you can override it with environment variables if needed.

## Setup

### 1. Start the local server

From the server folder:

Windows:

```powershell
python server.py
```

Or use the included helper:

```powershell
run.bat
```

Linux/macOS:

```bash
python server.py
```

or

```bash
bash run.sh
```

### 2. Load the extension in Chrome

1. Open Chrome and go to chrome://extensions
2. Turn on Developer mode
3. Click Load unpacked
4. Select the extension folder in this project

### 3. Use it

Open a supported website, paste a long or messy prompt, and click the Prompt Token Optimizer action from the page UI.

## Local server API

### GET /health

Returns whether the local service and model are available.

Example:

```json
{
  "ok": true,
  "model": "qwen2.5:3b",
  "available_models": ["qwen2.5:3b"],
  "status": "ok"
}
```

### POST /optimize

Request:

```json
{
  "prompt": "Write a React login form with validation and no database."
}
```

Response:

```json
{
  "optimized": "Create a React login form with validation. Do not use a database.",
  "original_tokens": 160,
  "optimized_tokens": 90,
  "tokens_saved": 70,
  "reduction_percent": 43.8,
  "model": "qwen2.5:3b",
  "validation_passed": true,
  "optimization_skipped": false,
  "error_code": "ok"
}
```

## Configuration

The Python server supports environment variables such as:

```bash
PROMPT_SAVER_MODEL=qwen2.5:3b
PROMPT_SAVER_FALLBACK_MODELS=llama3.1:8b,mistral
PROMPT_SAVER_OLLAMA_URL=http://127.0.0.1:11434
PROMPT_SAVER_PORT=8765
PROMPT_SAVER_HEALTH_TIMEOUT=3
PROMPT_SAVER_REQUEST_TIMEOUT=180
PROMPT_SAVER_RETRIES=2
PROMPT_SAVER_MAX_PROMPT_LENGTH=30000
```

## Privacy and behavior

- Prompt text is sent only to the local service running on your machine.
- The extension does not require a remote backend for optimization.
- Optimization is intentionally conservative: if validation fails, the original prompt is kept.
- The service tries to skip unnecessary work when the prompt is already concise.

## Notes

This project uses an estimated token count rather than a perfect tokenizer implementation. It is designed for practical prompt comparison and savings tracking rather than exact model-specific token accounting.

## Author

Arnav Deore
