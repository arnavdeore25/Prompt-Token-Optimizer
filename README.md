# PromptSaver Token Optimizer

PromptSaver Token Optimizer is a Manifest V3 Chrome extension for optimizing AI prompts with a model running locally on your computer. Its goal is to reduce unnecessary tokens while preserving the prompt's meaning and intent.

> Minimum tokens required to express maximum intent.

## Features

- Supports ChatGPT, Claude, and Gemini.
- Uses a local model service instead of a PromptSaver backend.
- Shows local model availability in the extension popup.
- Tracks optimized prompts, estimated tokens saved, and average reduction.
- Stores usage statistics locally with Chrome storage.

## Supported Websites

The content script is enabled on:
- `chatgpt.com`
- `chat.openai.com`
- `claude.ai`
- `gemini.google.com`

## Architecture

The browser extension communicates with a local service at `http://127.0.0.1:8765`:

```text
Supported AI website
				|
				v
	 content.js  --->  background.js  --->  local model service
				|                                      |
				+---------- Chrome local storage <----+
```
The repository contains the browser extension only. A local service must be running separately.

## Local Service API

The extension expects the service to expose these endpoints.

### `GET /health`

Used by the popup to check the service and model status. A successful response may look like:

```json
{
	"ok": true,
	"model": "your-local-model"
}
```

### `POST /optimize`

The extension sends:

```json
{
	"prompt": "The prompt to optimize"
}
```

The response must contain an `optimized` string. The extension also understands these optional fields:

```json
{
	"optimized": "The optimized prompt",
	"model": "your-local-model",
	"original_tokens": 120,
	"optimized_tokens": 82,
	"validation_passed": true
}
```

The local service can use a runtime such as Ollama, but its implementation is not included in this repository.

## Installation

1. Start the local model service on `127.0.0.1:8765`.
2. Open `chrome://extensions` in Chrome or another Chromium-based browser.
3. Enable **Developer mode**.
4. Click **Load unpacked**.
5. Select the `extension` folder from this repository.
6. Open one of the supported websites and refresh the page.

Open the Prompt Token Optimizer popup to confirm the local service status and view statistics.

## Troubleshooting

### Local server offline

Confirm that the local service is running on port `8765`:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
```

Then reload the extension and the supported website.

### Model not installed

The service is reachable, but its configured model is unavailable. Install or configure the model expected by your local service, then check `/health` again.

### Extension changes are not visible

Return to `chrome://extensions`, click **Reload** and refresh the AI website tab.

## Project Structure

```text
extension/
├── background.js   # Forwards optimization requests to the local service
├── content.js      # Runs on supported AI websites
├── content.css     # In-page extension styles
├── manifest.json   # Chrome extension configuration
├── popup.html      # Popup markup
├── popup.js        # Health status and usage statistics
├── popup.css       # Popup styles
└── icon*.svg       # Extension icons
```

## Author

Arnav Deore  
MCA Student, Christ University, Bangalore