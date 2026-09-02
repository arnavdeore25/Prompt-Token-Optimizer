from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request

MODEL = os.getenv("PROMPT_SAVER_MODEL", "qwen2.5:3b")
FALLBACK_MODELS = [
    item.strip()
    for item in os.getenv("PROMPT_SAVER_FALLBACK_MODELS", "").split(",")
    if item.strip()
]
OLLAMA_BASE = os.getenv("PROMPT_SAVER_OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_GENERATE = f"{OLLAMA_BASE}/api/generate"
OLLAMA_TAGS = f"{OLLAMA_BASE}/api/tags"
PORT = int(os.getenv("PROMPT_SAVER_PORT", "8765"))
HEALTH_TIMEOUT = int(os.getenv("PROMPT_SAVER_HEALTH_TIMEOUT", "3"))
REQUEST_TIMEOUT = int(os.getenv("PROMPT_SAVER_REQUEST_TIMEOUT", "180"))
MAX_RETRIES = int(os.getenv("PROMPT_SAVER_RETRIES", "2"))
MAX_PROMPT_LENGTH = int(os.getenv("PROMPT_SAVER_MAX_PROMPT_LENGTH", "30000"))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s"
)
logger = logging.getLogger("prompt_saver")

SYSTEM = """You are PromptSaver. Rewrite the user's messy prompt into the shortest clear prompt that preserves full intent.

Preserve every requirement, constraint, negation (NOT/DO NOT/NEVER/ONLY/WITHOUT), number, URL, filename, identifier, technical term, code block, error message and output format.

Remove filler, repetition and unnecessary conversational wording. Reorganize scattered requirements when useful.

Do not invent requirements.

If already concise, keep it essentially unchanged.

Code blocks must be copied exactly.

Return ONLY the optimized prompt."""


# ---------------------------------------------------------
# TOKEN ESTIMATE
# ---------------------------------------------------------

def est(text):
    return max(0, (len(text.strip()) + 3) // 4)


# ---------------------------------------------------------
# MODEL DISCOVERY / HEALTH
# ---------------------------------------------------------

def list_available_models():
    try:
        with urllib.request.urlopen(OLLAMA_TAGS, timeout=HEALTH_TIMEOUT) as response:
            data = json.load(response)
    except Exception as exc:  # pragma: no cover - network failure path
        logger.warning("Model discovery failed: %s", exc)
        return []

    models = data.get("models", [])
    names = []
    for model in models:
        name = model.get("name", "")
        if name:
            names.append(name)
    return names


def resolve_model(preferred_model=None):
    preferred = preferred_model or MODEL
    candidates = [preferred]
    candidates.extend(FALLBACK_MODELS)

    available = list_available_models()
    if not available:
        return preferred, False

    for candidate in candidates:
        for name in available:
            if name == candidate or name.startswith(candidate + ":"):
                return candidate, True

    if available:
        return available[0], False

    return preferred, False


def health_status():
    available = list_available_models()
    selected_model, is_available = resolve_model()

    ok = bool(available and is_available)
    return {
        "ok": ok,
        "model": selected_model,
        "available_models": available,
        "status": "ok" if ok else "model_unavailable",
        "message": "" if ok else f"Run: ollama pull {selected_model}"
    }


# ---------------------------------------------------------
# FAST LOCAL CHECK
# ---------------------------------------------------------
# This runs BEFORE Ollama.
# It is intentionally lightweight so it takes almost no time.
# ---------------------------------------------------------

FILLER_PHRASES = [
    "i want you to",
    "i would like you to",
    "can you please",
    "could you please",
    "please kindly",
    "if possible",
    "basically",
    "actually",
    "in order to",
    "as i mentioned",
    "as i said",
    "i need you to",
    "what i want is",
    "the thing is",
]


def fast_should_optimize(prompt):
    """
    Returns:
        True  -> send prompt to Ollama
        False -> return original prompt immediately
    """

    text = prompt.strip()

    if not text:
        return False

    token_estimate = est(text)
    if token_estimate < 35:
        return False

    score = 0

    if token_estimate >= 80:
        score += 2

    if token_estimate >= 150:
        score += 2

    lower = text.lower()
    filler_count = sum(lower.count(phrase) for phrase in FILLER_PHRASES)
    score += min(filler_count, 3)

    sentences = [
        s.strip().lower()
        for s in re.split(r"[.!?]+", text)
        if s.strip()
    ]
    unique_sentences = set(sentences)

    if len(sentences) >= 4 and len(unique_sentences) < len(sentences):
        score += 3

    if re.search(r"\s{3,}", text):
        score += 1

    long_sentences = [s for s in sentences if len(s.split()) > 40]
    if long_sentences:
        score += 1

    word_count = len(text.split())
    if word_count >= 100:
        score += 2

    return score >= 3


# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------

def valid(original, optimized):
    checks = []

    important_items = re.findall(
        r"```[\s\S]*?```|https?://\S+|\b\d+(?:\.\d+)?%?\b",
        original
    )

    for item in important_items:
        checks.append(item in optimized)

    negations = [
        "do not",
        "don't",
        "never",
        "only",
        "without",
        "must not",
    ]

    for phrase in negations:
        if re.search(r"\b" + re.escape(phrase) + r"\b", original, re.I):
            checks.append(
                bool(re.search(r"\b" + re.escape(phrase) + r"\b", optimized, re.I))
            )

    return all(checks) if checks else True


# ---------------------------------------------------------
# OLLAMA REQUESTS
# ---------------------------------------------------------

def call_ollama(prompt, model_name):
    body = json.dumps({
        "model": model_name,
        "system": SYSTEM,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9
        }
    }).encode()

    req = urllib.request.Request(
        OLLAMA_GENERATE,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        payload = json.loads(response.read())
        return payload["response"].strip()


def generate(prompt):
    selected_model, is_available = resolve_model()
    if not is_available:
        raise RuntimeError(f"Model unavailable: {selected_model}")

    for attempt in range(1, MAX_RETRIES + 2):
        try:
            logger.info(
                "Optimizing prompt with model=%s attempt=%s prompt_chars=%s",
                selected_model,
                attempt,
                len(prompt)
            )
            return call_ollama(prompt, selected_model)
        except urllib.error.URLError as exc:
            logger.warning(
                "Ollama request failed for model=%s attempt=%s error=%s",
                selected_model,
                attempt,
                exc
            )
            if attempt > MAX_RETRIES:
                raise RuntimeError(f"API timeout or unavailable model: {selected_model}")
            time.sleep(min(2 ** attempt, 6))
        except Exception as exc:
            logger.error("Generation failed for model=%s: %s", selected_model, exc)
            raise

    raise RuntimeError(f"Unable to optimize prompt using model: {selected_model}")


# ---------------------------------------------------------
# HTTP SERVER
# ---------------------------------------------------------

class H(BaseHTTPRequestHandler):

    def out(self, status, data):
        body = json.dumps(data).encode()

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Requested-With")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.out(200, {"ok": True})

    def do_GET(self):
        if self.path != "/health":
            return self.out(404, {"detail": "Not found"})

        try:
            payload = health_status()
            status_code = 200 if payload["ok"] else 503
            self.out(status_code, payload)
        except Exception as exc:
            logger.exception("Unexpected /health failure")
            self.out(
                503,
                {
                    "ok": False,
                    "model": MODEL,
                    "available_models": [],
                    "status": "model_unavailable",
                    "message": f"Ollama is not running: {exc}",
                }
            )

    def do_POST(self):
        if self.path != "/optimize":
            return self.out(404, {"detail": "Not found"})

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            request_body = self.rfile.read(content_length)
            payload = json.loads(request_body or "{}")
            prompt = str(payload.get("prompt", "")).strip()

            if not prompt:
                logger.warning("Rejecting empty prompt request")
                return self.out(400, {"detail": "Prompt is empty", "error_code": "empty_prompt"})

            if len(prompt) > MAX_PROMPT_LENGTH:
                logger.warning("Rejecting oversized prompt length=%s", len(prompt))
                return self.out(
                    413,
                    {
                        "detail": f"Prompt exceeds {MAX_PROMPT_LENGTH} characters",
                        "error_code": "prompt_too_large"
                    }
                )

            original_tokens = est(prompt)

            if not fast_should_optimize(prompt):
                logger.info("Skipping optimization because prompt is already concise")
                self.out(
                    200,
                    {
                        "optimized": prompt,
                        "original_tokens": original_tokens,
                        "optimized_tokens": original_tokens,
                        "tokens_saved": 0,
                        "reduction_percent": 0,
                        "model": "none",
                        "validation_passed": True,
                        "optimization_skipped": True,
                        "reason": "Prompt is already concise. Ollama was not called.",
                        "error_code": "prompt_too_short"
                    }
                )
                return

            try:
                optimized = generate(prompt)
            except RuntimeError as exc:
                message = str(exc)
                logger.error("Optimization failed: %s", message)
                if "Model unavailable" in message or "unavailable model" in message:
                    return self.out(
                        503,
                        {
                            "detail": message,
                            "model": MODEL,
                            "error_code": "model_unavailable"
                        }
                    )
                return self.out(
                    503,
                    {
                        "detail": message,
                        "model": MODEL,
                        "error_code": "api_timeout"
                    }
                )

            if not optimized:
                raise RuntimeError("Local model returned an empty response")

            optimized_tokens = est(optimized)
            if optimized_tokens > original_tokens:
                optimized = prompt
                optimized_tokens = original_tokens

            tokens_saved = max(0, original_tokens - optimized_tokens)
            reduction_percent = ((tokens_saved / original_tokens) * 100) if original_tokens else 0
            validation_passed = valid(prompt, optimized)

            if not validation_passed:
                logger.warning("Validation failed for optimized prompt; preserving original prompt")
                optimized = prompt
                optimized_tokens = original_tokens
                tokens_saved = 0
                reduction_percent = 0

            self.out(
                200,
                {
                    "optimized": optimized,
                    "original_tokens": original_tokens,
                    "optimized_tokens": optimized_tokens,
                    "tokens_saved": tokens_saved,
                    "reduction_percent": round(reduction_percent, 1),
                    "model": MODEL,
                    "validation_passed": validation_passed,
                    "optimization_skipped": False,
                    "error_code": "validation_failed" if not validation_passed else "ok"
                }
            )

        except json.JSONDecodeError:
            logger.warning("Malformed JSON input")
            self.out(400, {"detail": "Request body must be valid JSON", "error_code": "invalid_json"})

        except urllib.error.URLError as exc:
            logger.exception("Cannot reach Ollama")
            self.out(
                503,
                {
                    "detail": f"Cannot reach Ollama. Start Ollama and install {MODEL}.",
                    "model": MODEL,
                    "error_code": "model_unavailable"
                }
            )

        except Exception as exc:
            logger.exception("Unhandled /optimize failure")
            self.out(500, {"detail": str(exc), "error_code": "internal_error"})


# ---------------------------------------------------------
# START SERVER
# ---------------------------------------------------------

if __name__ == "__main__":
    logger.info("Starting PromptSaver server on http://127.0.0.1:%s using model=%s", PORT, MODEL)
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()