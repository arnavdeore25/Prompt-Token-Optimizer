from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import urllib.request
import urllib.error
import os
import re

MODEL = os.getenv("PROMPT_SAVER_MODEL", "qwen2.5:3b")
OLLAMA = "http://127.0.0.1:11434/api/generate"


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

    # Very short prompts are usually not worth optimizing.
    token_estimate = est(text)

    if token_estimate < 35:
        return False

    score = 0

    # Long prompt = more opportunity for compression.
    if token_estimate >= 80:
        score += 2

    if token_estimate >= 150:
        score += 2

    # Detect filler language.
    lower = text.lower()

    filler_count = sum(
        lower.count(phrase)
        for phrase in FILLER_PHRASES
    )

    score += min(filler_count, 3)

    # Detect repeated sentences.
    sentences = [
        s.strip().lower()
        for s in re.split(r"[.!?]+", text)
        if s.strip()
    ]

    unique_sentences = set(sentences)

    if len(sentences) >= 4 and len(unique_sentences) < len(sentences):
        score += 3

    # Excessive whitespace / formatting often means there
    # is something that can be cleaned up.
    if re.search(r"\s{3,}", text):
        score += 1

    # Very long sentences are often candidates for compression.
    long_sentences = [
        s for s in sentences
        if len(s.split()) > 40
    ]

    if long_sentences:
        score += 1

    # If the prompt contains a lot of words, favor optimization.
    word_count = len(text.split())

    if word_count >= 100:
        score += 2

    # Threshold.
    return score >= 3


# ---------------------------------------------------------
# VALIDATION
# ---------------------------------------------------------

def valid(original, optimized):
    checks = []

    # Preserve code blocks, URLs and numbers.
    important_items = re.findall(
        r"```[\s\S]*?```|https?://\S+|\b\d+(?:\.\d+)?%?\b",
        original
    )

    for item in important_items:
        checks.append(item in optimized)

    # Preserve important negations.
    negations = [
        "do not",
        "don't",
        "never",
        "only",
        "without",
        "must not",
    ]

    for phrase in negations:
        if re.search(
            r"\b" + re.escape(phrase) + r"\b",
            original,
            re.I
        ):
            checks.append(
                bool(
                    re.search(
                        r"\b" + re.escape(phrase) + r"\b",
                        optimized,
                        re.I
                    )
                )
            )

    return all(checks) if checks else True


# ---------------------------------------------------------
# OLLAMA
# ---------------------------------------------------------

def generate(prompt):

    body = json.dumps({
        "model": MODEL,
        "system": SYSTEM,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9
        }
    }).encode()

    req = urllib.request.Request(
        OLLAMA,
        data=body,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=180) as response:
        return json.loads(
            response.read()
        )["response"].strip()


# ---------------------------------------------------------
# HTTP SERVER
# ---------------------------------------------------------

class H(BaseHTTPRequestHandler):

    def out(self, status, data):

        body = json.dumps(data).encode()

        self.send_response(status)

        self.send_header(
            "Content-Type",
            "application/json"
        )

        self.send_header(
            "Access-Control-Allow-Origin",
            "*"
        )

        self.send_header(
            "Access-Control-Allow-Headers",
            "Content-Type, X-Requested-With"
        )

        self.send_header(
            "Access-Control-Allow-Methods",
            "GET,POST,OPTIONS"
        )

        self.send_header(
            "Access-Control-Allow-Private-Network",
            "true"
        )

        self.end_headers()

        self.wfile.write(body)

    # -----------------------------------------------------
    # OPTIONS
    # -----------------------------------------------------

    def do_OPTIONS(self):

        self.out(
            200,
            {"ok": True}
        )

    # -----------------------------------------------------
    # HEALTH
    # -----------------------------------------------------

    def do_GET(self):

        if self.path != "/health":

            return self.out(
                404,
                {"detail": "Not found"}
            )

        try:

            with urllib.request.urlopen(
                "http://127.0.0.1:11434/api/tags",
                timeout=3
            ) as response:

                data = json.load(response)

            names = [
                model.get("name", "")
                for model in data.get("models", [])
            ]

            ok = any(
                name == MODEL or
                name.startswith(MODEL + ":")
                for name in names
            )

            self.out(
                200,
                {
                    "ok": ok,
                    "model": MODEL,
                    "message":
                        "" if ok
                        else f"Run: ollama pull {MODEL}"
                }
            )

        except Exception:

            self.out(
                503,
                {
                    "ok": False,
                    "model": MODEL,
                    "message": "Ollama is not running"
                }
            )

    # -----------------------------------------------------
    # OPTIMIZE
    # -----------------------------------------------------

    def do_POST(self):

        if self.path != "/optimize":

            return self.out(
                404,
                {"detail": "Not found"}
            )

        try:

            # Read request.
            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            request_body = self.rfile.read(
                content_length
            )

            prompt = json.loads(
                request_body
            ).get(
                "prompt",
                ""
            ).strip()

            # Empty prompt.
            if not prompt:

                return self.out(
                    400,
                    {"detail": "Prompt is empty"}
                )

            # Maximum prompt size.
            if len(prompt) > 30000:

                return self.out(
                    413,
                    {
                        "detail":
                        "Prompt exceeds 30,000 characters"
                    }
                )

            original_tokens = est(prompt)

            # -------------------------------------------------
            # FAST CHECK
            # -------------------------------------------------

            should_optimize = fast_should_optimize(
                prompt
            )

            # If prompt is already concise,
            # DO NOT call Ollama.
            if not should_optimize:

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
                        "reason":
                            "Prompt is already concise. "
                            "Ollama was not called."
                    }
                )

                return

            # -------------------------------------------------
            # OLLAMA OPTIMIZATION
            # -------------------------------------------------

            optimized = generate(prompt)

            if not optimized:

                raise RuntimeError(
                    "Local model returned an empty response"
                )

            optimized_tokens = est(
                optimized
            )

            # Never accept a longer prompt.
            if optimized_tokens > original_tokens:

                optimized = prompt
                optimized_tokens = original_tokens

            tokens_saved = max(
                0,
                original_tokens - optimized_tokens
            )

            reduction_percent = (
                (tokens_saved / original_tokens) * 100
                if original_tokens
                else 0
            )

            validation_passed = valid(
                prompt,
                optimized
            )

            self.out(
                200,
                {
                    "optimized": optimized,
                    "original_tokens": original_tokens,
                    "optimized_tokens": optimized_tokens,
                    "tokens_saved": tokens_saved,
                    "reduction_percent":
                        round(reduction_percent, 1),
                    "model": MODEL,
                    "validation_passed":
                        validation_passed,
                    "optimization_skipped": False
                }
            )

        except urllib.error.URLError:

            self.out(
                503,
                {
                    "detail":
                    f"Cannot reach Ollama. "
                    f"Start Ollama and install {MODEL}."
                }
            )

        except Exception as error:

            self.out(
                500,
                {
                    "detail": str(error)
                }
            )


# ---------------------------------------------------------
# START SERVER
# ---------------------------------------------------------

if __name__ == "__main__":

    print(
        f"PromptSaver server on "
        f"http://127.0.0.1:8765 "
        f"using {MODEL}"
    )

    HTTPServer(
        ("127.0.0.1", 8765),
        H
    ).serve_forever()