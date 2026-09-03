# Prompt Token Optimizer

Prompt Token Optimizer is a Manifest V3 Chrome extension and local Python service for shortening messy prompts before they are sent to an AI website. Prompts stay on the user's machine: the extension calls `127.0.0.1`, and the Python service calls Ollama locally.

The service first applies a lightweight heuristic. Concise prompts are returned unchanged without calling Ollama. Longer or noisy prompts are rewritten by the configured Ollama model, then checked for preservation of URLs, numbers, code blocks, and common negations.

## Features

- Local prompt optimization through Ollama
- Chrome extension for supported AI sites
- Fast heuristic check before LLM usage
- Validation step to preserve key prompt details
- Token savings and reduction stats
- No cloud dependency for prompt rewriting
- Local usage tracking in Chrome storage

## Limitations

- Token counts are estimates. The service uses `tiktoken` with `cl100k_base` when available and falls back to characters divided by four.
- The optimizer is intentionally conservative. If the rewritten prompt is longer or fails validation, the original prompt is kept.
- The extension only injects its UI into the four hosts listed below.
- Ollama is required only when a prompt needs model-based rewriting; the HTTP server itself can start without Ollama.

## Supported sites

The extension is configured for:

- https://chatgpt.com/
- https://chat.openai.com/
- https://claude.ai/
- https://gemini.google.com/

## How It Works

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

## Project Structure

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

Install the following before using model-based optimization:

- Python 3.9 or later
- Google Chrome or a Chromium-based browser
- [Ollama](https://ollama.com/)

From the `server` directory, install the Python dependency:

```powershell
python -m pip install -r requirements.txt
```

Install and start Ollama, then download the default model:

```powershell
ollama pull qwen2.5:3b
```

The default model is `qwen2.5:3b`. It can be changed with environment variables described below.

## Setup

### 1. Start Ollama

Make sure Ollama is running and that the configured model is installed. On most systems, the Ollama application starts its local API automatically.

### 2. Start the local server

From the server folder:

Windows:

```powershell
python server.py
```

Or use the included Windows helper, which checks for Ollama, pulls the default model, installs Python dependencies, and starts the server:

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

### 3. Check the server

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

`ok: true` means the configured model is available. A `503` response with `status: model_unavailable` means the server is running but Ollama or the model is not ready.

### 4. Load the extension in Chrome

1. Open Chrome and go to chrome://extensions
2. Turn on Developer mode
3. Click Load unpacked
4. Select the extension folder in this project

### 5. Use it

Open a supported website, paste a long or messy prompt, and click the floating `Optimize` button. Review the original and optimized text in the modal, then either copy the result or use it in the composer.

The extension popup shows server/model status and cumulative local usage statistics. Statistics are stored with `chrome.storage.local`.

## Testing the Server

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Optimization request:

```powershell
$body = @{ prompt = "Can you please basically rewrite this prompt clearly while preserving https://example.com/docs, the number 8765, and the instruction do not remove the code block?" } | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8765/optimize -Method Post -ContentType "application/json" -Body $body
```

The service rejects an empty prompt with `400` and rejects prompts over the configured maximum with `413`. A concise prompt can receive a successful response with `optimization_skipped: true` and no Ollama call.

## Local server API

### `GET /health`

Returns whether the local service can find the configured Ollama model. The HTTP status is `200` when the model is available and `503` otherwise.

Example:

```json
{
  "ok": true,
  "model": "qwen2.5:3b",
  "available_models": ["qwen2.5:3b"],
      "status": "ok",
      "message": "",
      "tokenizer": "cl100k_base",
      "tokenizer_accurate": true
}
```

### `POST /optimize`

Request:

```json
{
      "prompt": "Can you please rewrite this clearly without removing https://example.com or the number 42?"
}
```

Response:

```json
{
      "optimized": "Rewrite this clearly without removing https://example.com or the number 42.",
      "original_tokens": 22,
      "optimized_tokens": 15,
      "tokens_saved": 7,
      "reduction_percent": 31.8,
  "model": "qwen2.5:3b",
  "validation_passed": true,
  "optimization_skipped": false,
  "error_code": "ok"
}
```

Possible error codes include `empty_prompt`, `prompt_too_large`, `prompt_too_short`, `model_unavailable`, `api_timeout`, `validation_failed`, and `internal_error`.

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
PROMPT_SAVER_TOKENIZER_ENCODING=cl100k_base
```

On Windows PowerShell, set a value for the current session with, for example:

```powershell
$env:PROMPT_SAVER_MODEL = "qwen2.5:3b"
python server.py
```

## Troubleshooting

### `python server.py` exits with code 1

The server binds to `127.0.0.1:8765` and then runs continuously. Ollama is not contacted during startup, so a startup exit is usually unrelated to model availability. Check the terminal traceback first. A common cause is that port `8765` is already in use:

```powershell
Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue
```

Stop the process using the port, or choose another port and use the same value for the extension's `SERVER` constant and host permissions.

If the server stays running but `/health` returns `503`, start Ollama and install the model named in the response. If the popup says the local server is offline, verify that the server is running at exactly `http://127.0.0.1:8765` and reload the extension.

## Privacy and Behavior

- Prompt text is sent only to the local service running on your machine.
- The extension does not require a remote backend for optimization.
- Optimization is intentionally conservative: if validation fails, the original prompt is kept.
- The service tries to skip unnecessary work when the prompt is already concise.

## Author

Arnav Deore
