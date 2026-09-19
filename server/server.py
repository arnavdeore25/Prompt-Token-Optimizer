from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request


# =========================================================
# OPTIONAL TOKENIZER
# =========================================================

try:
    import tiktoken

    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False


# =========================================================
# CONFIGURATION
# =========================================================

MODEL = os.getenv("PROMPT_SAVER_MODEL", "qwen2.5:3b")

FALLBACK_MODELS = [
    item.strip()
    for item in os.getenv("PROMPT_SAVER_FALLBACK_MODELS", "").split(",")
    if item.strip()
]

OLLAMA_BASE = os.getenv(
    "PROMPT_SAVER_OLLAMA_URL",
    "http://127.0.0.1:11434"
).rstrip("/")

OLLAMA_GENERATE = f"{OLLAMA_BASE}/api/generate"
OLLAMA_TAGS = f"{OLLAMA_BASE}/api/tags"

PORT = int(os.getenv("PROMPT_SAVER_PORT", "8765"))

HEALTH_TIMEOUT = int(
    os.getenv("PROMPT_SAVER_HEALTH_TIMEOUT", "3")
)

REQUEST_TIMEOUT = int(
    os.getenv("PROMPT_SAVER_REQUEST_TIMEOUT", "180")
)

MAX_RETRIES = int(
    os.getenv("PROMPT_SAVER_RETRIES", "2")
)

MAX_PROMPT_LENGTH = int(
    os.getenv("PROMPT_SAVER_MAX_PROMPT_LENGTH", "30000")
)

TOKENIZER_ENCODING = os.getenv(
    "PROMPT_SAVER_TOKENIZER_ENCODING",
    "cl100k_base"
)

# Minimum reduction we would like the model to achieve.
# This is a target, NOT a hard requirement.
TARGET_REDUCTION_PERCENT = float(
    os.getenv("PROMPT_SAVER_TARGET_REDUCTION", "20")
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s"
)

logger = logging.getLogger("prompt_saver")


# =========================================================
# OPTIMIZATION PROMPTS
# =========================================================

SYSTEM = """You are PromptSaver, a prompt compression engine.

Your job is to rewrite the user's prompt into a significantly shorter,
clearer, more efficient prompt while preserving the complete meaning.

PRIMARY GOAL:
- Reduce unnecessary tokens.
- Remove filler and conversational language.
- Remove repetition.
- Combine related requirements.
- Reorganize scattered requirements into concise instructions.
- Preserve the actual task and every meaningful constraint.
- When the prompt contains removable verbosity, aim for at least 20% fewer
  tokens than the original.

REMOVE:
- Greetings such as "hey", "hi", "hello".
- Conversational filler.
- Repeated requests.
- Repeated explanations.
- Unnecessary personal context that does not affect the task.
- Phrases such as "can you please", "I want you to", "basically",
  "actually", "the thing is", etc.
- Redundant wording.

MUST PRESERVE:
- Every actual user requirement.
- Every important constraint.
- Negations such as NOT, DO NOT, NEVER, ONLY, WITHOUT, MUST NOT.
- Numbers that represent requirements.
- URLs.
- File names.
- Identifiers.
- Technical terms.
- Programming languages.
- Frameworks.
- Operating systems.
- Versions.
- Error messages.
- Requested output formats.
- Code blocks.

IMPORTANT:
- Do not invent requirements.
- Do not remove requirements just to achieve a smaller token count.
- Do not change the user's intended task.
- Do not answer the user's task.
- Do not explain your changes.
- Return ONLY the compressed prompt.
- Do not wrap the answer in quotation marks.
- Do not add headings such as "Optimized Prompt:".

CODE:
- Code blocks must be copied exactly.
- Do not modify code.
- Do not remove code.

If the prompt is genuinely already concise, it is acceptable to keep it
similar, but whenever meaningful redundancy or filler exists, remove it.
"""


AGGRESSIVE_SYSTEM = """You are PromptSaver in aggressive compression mode.

Compress the user's prompt as much as possible while preserving ALL
meaningful requirements and constraints.

The output must be substantially shorter whenever the original contains
redundancy, filler, repetition, or unnecessary conversational wording.

TARGET:
- Prefer at least 25% token reduction when safely possible.
- Be concise and direct.
- Do not preserve conversational style when it does not affect meaning.

REMOVE:
- Greetings.
- Filler.
- Repeated ideas.
- Repeated requirements.
- Unnecessary conversational phrases.
- Personal explanations that do not change the requested task.
- Verbose transitions.
- Redundant wording.

COMBINE:
- Related requirements into one concise instruction.
- Multiple sentences expressing the same idea.
- Lists of related requirements where safe.

MUST PRESERVE:
- The actual task.
- Every meaningful requirement.
- Every constraint.
- Every negation.
- DO NOT / NOT / NEVER / ONLY / WITHOUT / MUST NOT.
- Numbers representing requirements.
- URLs.
- File names.
- Identifiers.
- Technical terminology.
- Programming languages.
- Frameworks.
- Platforms.
- Operating systems.
- Versions.
- Error messages.
- Output formats.
- Code blocks.

STRICT RULES:
- Never invent information.
- Never change the requested task.
- Never silently remove a requirement.
- Never modify code blocks.
- Never explain the optimization.
- Return ONLY the optimized prompt.
"""


# =========================================================
# TOKEN ESTIMATE
# =========================================================

_encoder = None
_encoder_load_attempted = False


def _get_encoder():
    global _encoder
    global _encoder_load_attempted

    if _encoder_load_attempted:
        return _encoder

    _encoder_load_attempted = True

    if not TIKTOKEN_AVAILABLE:
        logger.warning(
            "tiktoken not installed; falling back to char/4 token estimate. "
            "Install it with: pip install tiktoken"
        )
        return None

    try:
        _encoder = tiktoken.get_encoding(
            TOKENIZER_ENCODING
        )
    except Exception as exc:
        logger.warning(
            "Failed to load tiktoken encoding '%s': %s. "
            "Falling back to char/4 estimate.",
            TOKENIZER_ENCODING,
            exc
        )
        _encoder = None

    return _encoder


def est(text):
    """
    Estimate token count.

    Uses tiktoken when available.
    Falls back to approximately characters / 4.
    """

    text = (text or "").strip()

    if not text:
        return 0

    encoder = _get_encoder()

    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception as exc:
            logger.warning(
                "tiktoken encode failed, using char/4 estimate: %s",
                exc
            )

    return max(
        0,
        (len(text) + 3) // 4
    )


# =========================================================
# MODEL DISCOVERY / HEALTH
# =========================================================

def list_available_models():
    """
    Return the models currently installed in Ollama.
    """

    try:
        with urllib.request.urlopen(
            OLLAMA_TAGS,
            timeout=HEALTH_TIMEOUT
        ) as response:
            data = json.load(response)

    except Exception as exc:
        logger.warning(
            "Model discovery failed: %s",
            exc
        )
        return []

    models = data.get("models", [])

    names = []

    for model in models:
        name = model.get("name", "")

        if name:
            names.append(name)

    return names


def resolve_model(preferred_model=None):
    """
    Select the preferred model or a fallback model.

    Returns:
        (selected_model, is_available)
    """

    preferred = preferred_model or MODEL

    candidates = [preferred]
    candidates.extend(FALLBACK_MODELS)

    available = list_available_models()

    if not available:
        return preferred, False

    # Exact / prefix matching first.
    for candidate in candidates:
        for name in available:
            if (
                name == candidate
                or name.startswith(candidate + ":")
            ):
                return candidate, True

    # If preferred models aren't found, use the first available model.
    if available:
        return available[0], False

    return preferred, False


def health_status():
    available = list_available_models()

    selected_model, is_available = resolve_model()

    ok = bool(
        available
        and is_available
    )

    tokenizer_active = (
        _get_encoder() is not None
    )

    return {
        "ok": ok,
        "model": selected_model,
        "available_models": available,
        "status": "ok" if ok else "model_unavailable",
        "message": (
            ""
            if ok
            else f"Run: ollama pull {selected_model}"
        ),
        "tokenizer": (
            TOKENIZER_ENCODING
            if tokenizer_active
            else "char_estimate_fallback"
        ),
        "tokenizer_accurate": tokenizer_active
    }


# =========================================================
# FAST LOCAL CHECK
# =========================================================

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
    "hey hi",
    "hello ai",
]


def fast_should_optimize(prompt):
    """
    Lightweight local heuristic.

    Returns:
        True  -> send prompt to Ollama
        False -> return original immediately
    """

    text = prompt.strip()

    if not text:
        return False

    token_estimate = est(text)

    # Very short prompts are not worth sending to Ollama.
    if token_estimate < 35:
        return False

    score = 0

    # Longer prompts are more likely to benefit.
    if token_estimate >= 80:
        score += 2

    if token_estimate >= 150:
        score += 2

    lower = text.lower()

    filler_count = sum(
        lower.count(phrase)
        for phrase in FILLER_PHRASES
    )

    score += min(
        filler_count,
        3
    )

    # Detect repeated sentences.
    sentences = [
        s.strip().lower()
        for s in re.split(
            r"[.!?]+",
            text
        )
        if s.strip()
    ]

    unique_sentences = set(sentences)

    if (
        len(sentences) >= 4
        and len(unique_sentences) < len(sentences)
    ):
        score += 3

    # Excessive whitespace.
    if re.search(r"\s{3,}", text):
        score += 1

    # Long sentences are often compressible.
    long_sentences = [
        s
        for s in sentences
        if len(s.split()) > 40
    ]

    if long_sentences:
        score += 1

    word_count = len(text.split())

    if word_count >= 100:
        score += 2

    return score >= 3


# =========================================================
# VALIDATION
# =========================================================

_CONTRACTION_MAP = {
    "don't": "do not",
    "doesn't": "does not",
    "didn't": "did not",
    "can't": "cannot",
    "won't": "will not",
    "isn't": "is not",
    "aren't": "are not",
    "wasn't": "was not",
    "weren't": "were not",
    "shouldn't": "should not",
    "wouldn't": "would not",
    "couldn't": "could not",
    "mustn't": "must not",
}


def _normalize_negations(text):
    lower = text.lower()

    for contraction, expanded in _CONTRACTION_MAP.items():
        lower = lower.replace(
            contraction,
            expanded
        )

    return lower


def _extract_critical_items(original):
    """
    Extract items that should not disappear from the optimized prompt.

    These include:
    - code blocks
    - URLs
    - numbers
    """

    return re.findall(
        r"```[\s\S]*?```|https?://\S+|\b\d+(?:\.\d+)?%?\b",
        original
    )


def valid(original, optimized):
    """
    Validate that important prompt information wasn't lost.

    Returns a dict rather than a simple boolean.
    """

    failed_critical = []
    failed_soft = []

    # -----------------------------------------------------
    # Critical items
    # -----------------------------------------------------

    important_items = _extract_critical_items(
        original
    )

    for item in important_items:

        if item not in optimized:
            failed_critical.append(
                f"missing: {item}"
            )

    # -----------------------------------------------------
    # Negations
    # -----------------------------------------------------

    normalized_original = _normalize_negations(
        original
    )

    normalized_optimized = _normalize_negations(
        optimized
    )

    negations = [
        "do not",
        "never",
        "only",
        "without",
        "must not",
    ]

    for phrase in negations:

        pattern = (
            r"\b"
            + re.escape(phrase)
            + r"\b"
        )

        if re.search(
            pattern,
            normalized_original,
            re.I
        ):

            if not re.search(
                pattern,
                normalized_optimized,
                re.I
            ):

                failed_soft.append(
                    f"possible dropped constraint: '{phrase}'"
                )

    return {
        "passed": (
            not failed_critical
            and not failed_soft
        ),
        "critical_ok": not failed_critical,
        "failed_checks": (
            failed_critical
            + failed_soft
        )
    }


# =========================================================
# OLLAMA REQUESTS
# =========================================================

def call_ollama(
    prompt,
    model_name,
    system_prompt
):
    """
    Make one Ollama generation request.
    """

    body = json.dumps({
        "model": model_name,
        "system": system_prompt,
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
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(
        req,
        timeout=REQUEST_TIMEOUT
    ) as response:

        payload = json.loads(
            response.read()
        )

        result = payload.get(
            "response",
            ""
        )

        return result.strip()


def generate(
    prompt,
    aggressive=False
):
    """
    Generate an optimized prompt.

    aggressive=False:
        Normal compression.

    aggressive=True:
        Stronger compression attempt.
    """

    selected_model, is_available = resolve_model()

    if not is_available:
        raise RuntimeError(
            f"Model unavailable: {selected_model}"
        )

    system_prompt = (
        AGGRESSIVE_SYSTEM
        if aggressive
        else SYSTEM
    )

    mode = (
        "aggressive"
        if aggressive
        else "normal"
    )

    for attempt in range(
        1,
        MAX_RETRIES + 2
    ):

        try:

            logger.info(
                "Optimizing prompt "
                "model=%s mode=%s attempt=%s chars=%s",
                selected_model,
                mode,
                attempt,
                len(prompt)
            )

            return call_ollama(
                prompt,
                selected_model,
                system_prompt
            )

        except urllib.error.URLError as exc:

            logger.warning(
                "Ollama request failed "
                "model=%s mode=%s attempt=%s error=%s",
                selected_model,
                mode,
                attempt,
                exc
            )

            if attempt > MAX_RETRIES:
                raise RuntimeError(
                    "API timeout or unavailable "
                    f"model: {selected_model}"
                )

            time.sleep(
                min(
                    2 ** attempt,
                    6
                )
            )

        except Exception as exc:

            logger.error(
                "Generation failed "
                "model=%s mode=%s: %s",
                selected_model,
                mode,
                exc
            )

            raise

    raise RuntimeError(
        "Unable to optimize prompt using model: "
        f"{selected_model}"
    )


# =========================================================
# OPTIMIZATION PIPELINE
# =========================================================

def optimize_prompt(prompt):
    """
    Complete optimization pipeline.

    Flow:

        Original
            |
            v
        Fast local check
            |
            v
        Normal Ollama optimization
            |
            +---- shorter ----> validate
            |
            +---- same/longer
                         |
                         v
                  Aggressive Ollama
                         |
                         +---- shorter ----> validate
                         |
                         +---- same/longer
                                      |
                                      v
                                  original

    Returns a result dictionary.
    """

    original_tokens = est(prompt)

    # -----------------------------------------------------
    # Fast local check
    # -----------------------------------------------------

    if not fast_should_optimize(prompt):

        logger.info(
            "Skipping optimization because "
            "prompt is already concise"
        )

        return {
            "optimized": prompt,
            "original_tokens": original_tokens,
            "optimized_tokens": original_tokens,
            "tokens_saved": 0,
            "reduction_percent": 0,
            "model": "none",
            "validation_passed": True,
            "failed_checks": [],
            "optimization_skipped": True,
            "reason": (
                "Prompt is already concise. "
                "Ollama was not called."
            ),
            "error_code": "prompt_too_short"
        }

    # -----------------------------------------------------
    # Resolve model
    # -----------------------------------------------------

    selected_model, is_available = resolve_model()

    if not is_available:

        raise RuntimeError(
            f"Model unavailable: {selected_model}"
        )

    # -----------------------------------------------------
    # PASS 1: NORMAL OPTIMIZATION
    # -----------------------------------------------------

    try:

        optimized = generate(
            prompt,
            aggressive=False
        )

    except RuntimeError:
        raise

    if not optimized:

        raise RuntimeError(
            "Local model returned an empty response"
        )

    optimized_tokens = est(
        optimized
    )

    logger.info(
        "Normal optimization result: "
        "%s -> %s tokens",
        original_tokens,
        optimized_tokens
    )

    # -----------------------------------------------------
    # PASS 2: AGGRESSIVE OPTIMIZATION
    #
    # This is the major fix for your current problem.
    #
    # If Qwen returns:
    #
    #     245 -> 245
    #
    # we do NOT immediately accept it.
    #
    # We try again with a stronger compression prompt.
    # -----------------------------------------------------

    if optimized_tokens >= original_tokens:

        logger.info(
            "Normal optimization produced no token savings "
            "(%s -> %s). Starting aggressive retry.",
            original_tokens,
            optimized_tokens
        )

        try:

            aggressive_result = generate(
                prompt,
                aggressive=True
            )

            if aggressive_result:

                aggressive_tokens = est(
                    aggressive_result
                )

                logger.info(
                    "Aggressive optimization result: "
                    "%s -> %s tokens",
                    original_tokens,
                    aggressive_tokens
                )

                # Only use aggressive result if it is
                # genuinely shorter.
                if aggressive_tokens < optimized_tokens:

                    optimized = aggressive_result
                    optimized_tokens = aggressive_tokens

        except Exception as exc:

            logger.warning(
                "Aggressive optimization failed: %s",
                exc
            )

    # -----------------------------------------------------
    # NO REDUCTION
    # -----------------------------------------------------

    if optimized_tokens >= original_tokens:

        logger.info(
            "No meaningful optimization found: "
            "%s -> %s tokens",
            original_tokens,
            optimized_tokens
        )

        return {
            "optimized": prompt,
            "original_tokens": original_tokens,
            "optimized_tokens": original_tokens,
            "tokens_saved": 0,
            "reduction_percent": 0,
            "model": selected_model,
            "validation_passed": True,
            "failed_checks": [],
            "optimization_skipped": True,
            "reason": (
                "No meaningful token reduction was "
                "found by the local model."
            ),
            "error_code": "no_reduction"
        }

    # -----------------------------------------------------
    # VALIDATE
    # -----------------------------------------------------

    validation = valid(
        prompt,
        optimized
    )

    # -----------------------------------------------------
    # CRITICAL VALIDATION FAILURE
    # -----------------------------------------------------

    if not validation["critical_ok"]:

        logger.warning(
            "Critical validation failure, "
            "reverting to original: %s",
            validation["failed_checks"]
        )

        return {
            "optimized": prompt,
            "original_tokens": original_tokens,
            "optimized_tokens": original_tokens,
            "tokens_saved": 0,
            "reduction_percent": 0,
            "model": selected_model,
            "validation_passed": False,
            "failed_checks": validation["failed_checks"],
            "optimization_skipped": True,
            "reason": (
                "Optimization removed a critical item "
                "such as a number, URL, or code block."
            ),
            "error_code": "validation_failed"
        }

    # -----------------------------------------------------
    # SOFT VALIDATION FAILURE
    # -----------------------------------------------------

    if not validation["passed"]:

        logger.info(
            "Soft validation warning: %s",
            validation["failed_checks"]
        )

        validation_passed = False
        error_code = "unverified"

    else:

        validation_passed = True
        error_code = "ok"

    # -----------------------------------------------------
    # FINAL TOKEN CALCULATION
    # -----------------------------------------------------

    tokens_saved = max(
        0,
        original_tokens - optimized_tokens
    )

    reduction_percent = (
        (
            tokens_saved
            / original_tokens
        ) * 100
        if original_tokens
        else 0
    )

    logger.info(
        "Final optimization: "
        "%s -> %s tokens, saved=%s, reduction=%.1f%%",
        original_tokens,
        optimized_tokens,
        tokens_saved,
        reduction_percent
    )

    # -----------------------------------------------------
    # RETURN
    # -----------------------------------------------------

    return {
        "optimized": optimized,
        "original_tokens": original_tokens,
        "optimized_tokens": optimized_tokens,
        "tokens_saved": tokens_saved,
        "reduction_percent": round(
            reduction_percent,
            1
        ),
        "model": selected_model,
        "validation_passed": validation_passed,
        "failed_checks": validation["failed_checks"],
        "optimization_skipped": False,
        "reason": (
            "Prompt successfully optimized."
            if tokens_saved > 0
            else "No meaningful reduction found."
        ),
        "error_code": error_code
    }


# =========================================================
# HTTP SERVER
# =========================================================

class H(BaseHTTPRequestHandler):

    # -----------------------------------------------------
    # JSON RESPONSE
    # -----------------------------------------------------

    def out(
        self,
        status,
        data
    ):
        body = json.dumps(
            data
        ).encode()

        self.send_response(
            status
        )

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

        self.wfile.write(
            body
        )

    # -----------------------------------------------------
    # OPTIONS
    # -----------------------------------------------------

    def do_OPTIONS(self):

        self.out(
            200,
            {
                "ok": True
            }
        )

    # -----------------------------------------------------
    # GET /health
    # -----------------------------------------------------

    def do_GET(self):

        if self.path != "/health":

            return self.out(
                404,
                {
                    "detail": "Not found"
                }
            )

        try:

            payload = health_status()

            status_code = (
                200
                if payload["ok"]
                else 503
            )

            self.out(
                status_code,
                payload
            )

        except Exception as exc:

            logger.exception(
                "Unexpected /health failure"
            )

            self.out(
                503,
                {
                    "ok": False,
                    "model": MODEL,
                    "available_models": [],
                    "status": "model_unavailable",
                    "message": (
                        "Ollama is not running: "
                        f"{exc}"
                    )
                }
            )

    # -----------------------------------------------------
    # POST /optimize
    # -----------------------------------------------------

    def do_POST(self):

        if self.path != "/optimize":

            return self.out(
                404,
                {
                    "detail": "Not found"
                }
            )

        try:

            # -------------------------------------------------
            # READ REQUEST
            # -------------------------------------------------

            content_length = int(
                self.headers.get(
                    "Content-Length",
                    "0"
                )
            )

            request_body = self.rfile.read(
                content_length
            )

            payload = json.loads(
                request_body or "{}"
            )

            prompt = str(
                payload.get(
                    "prompt",
                    ""
                )
            ).strip()

            # -------------------------------------------------
            # EMPTY PROMPT
            # -------------------------------------------------

            if not prompt:

                logger.warning(
                    "Rejecting empty prompt request"
                )

                return self.out(
                    400,
                    {
                        "detail": "Prompt is empty",
                        "error_code": "empty_prompt"
                    }
                )

            # -------------------------------------------------
            # MAX LENGTH
            # -------------------------------------------------

            if len(prompt) > MAX_PROMPT_LENGTH:

                logger.warning(
                    "Rejecting oversized prompt "
                    "length=%s",
                    len(prompt)
                )

                return self.out(
                    413,
                    {
                        "detail": (
                            f"Prompt exceeds "
                            f"{MAX_PROMPT_LENGTH} characters"
                        ),
                        "error_code": "prompt_too_large"
                    }
                )

            # -------------------------------------------------
            # OPTIMIZE
            # -------------------------------------------------

            result = optimize_prompt(
                prompt
            )

            # -------------------------------------------------
            # RETURN RESULT
            # -------------------------------------------------

            return self.out(
                200,
                result
            )

        # -----------------------------------------------------
        # INVALID JSON
        # -----------------------------------------------------

        except json.JSONDecodeError:

            logger.warning(
                "Malformed JSON input"
            )

            self.out(
                400,
                {
                    "detail": (
                        "Request body must be valid JSON"
                    ),
                    "error_code": "invalid_json"
                }
            )

        # -----------------------------------------------------
        # OLLAMA CONNECTION ERROR
        # -----------------------------------------------------

        except urllib.error.URLError as exc:

            logger.exception(
                "Cannot reach Ollama"
            )

            self.out(
                503,
                {
                    "detail": (
                        "Cannot reach Ollama. "
                        f"Start Ollama and install {MODEL}."
                    ),
                    "model": MODEL,
                    "error_code": "model_unavailable"
                }
            )

        # -----------------------------------------------------
        # MODEL UNAVAILABLE
        # -----------------------------------------------------

        except RuntimeError as exc:

            message = str(exc)

            logger.error(
                "Optimization failed: %s",
                message
            )

            if (
                "Model unavailable" in message
                or "unavailable model" in message
            ):

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
                    "error_code": "optimization_failed"
                }
            )

        # -----------------------------------------------------
        # UNKNOWN ERROR
        # -----------------------------------------------------

        except Exception as exc:

            logger.exception(
                "Unhandled /optimize failure"
            )

            self.out(
                500,
                {
                    "detail": str(exc),
                    "error_code": "internal_error"
                }
            )


# =========================================================
# SERVER START
# =========================================================

if __name__ == "__main__":

    logger.info(
        "Starting PromptSaver server on "
        "http://127.0.0.1:%s using model=%s",
        PORT,
        MODEL
    )

    logger.info(
        "Target reduction: %.1f%%",
        TARGET_REDUCTION_PERCENT
    )

    logger.info(
        "Ollama URL: %s",
        OLLAMA_BASE
    )

    logger.info(
        "Tokenizer: %s",
        (
            TOKENIZER_ENCODING
            if TIKTOKEN_AVAILABLE
            else "char/4 fallback"
        )
    )

    HTTPServer(
        ("127.0.0.1", PORT),
        H
    ).serve_forever()