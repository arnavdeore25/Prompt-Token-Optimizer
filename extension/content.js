(() => {
  "use strict";

  const SERVER = "http://127.0.0.1:8765";

  const SUPPORTED_HOSTS = [
    "chatgpt.com",
    "chat.openai.com",
    "claude.ai",
    "gemini.google.com",
  ];

  if (!SUPPORTED_HOSTS.some((host) => location.hostname.includes(host))) {
    return;
  }

  let composer = null;
  let optimizeButton = null;
  let observerStarted = false;
  let attaching = false;

  const est = (text) =>
    Math.max(0, Math.ceil((text || "").trim().length / 4));

  // ------------------------------------------------------------
  // Find the active AI composer
  // ------------------------------------------------------------

  function getComposer() {
    const host = location.hostname;

    let selectors = [];

    if (
      host.includes("chatgpt.com") ||
      host.includes("chat.openai.com")
    ) {
      selectors = [
        'textarea[data-id="root"]',
        'textarea[placeholder*="Message"]',
        'textarea[placeholder*="message" i]',
        'div[contenteditable="true"][data-placeholder*="Message"]',
        'div[contenteditable="true"][role="textbox"]',
      ];
    }

    if (host.includes("claude.ai")) {
      selectors = [
        'div[contenteditable="true"][role="textbox"]',
        'div[contenteditable="true"]',
        'textarea[placeholder*="Reply"]',
        'textarea[placeholder*="message" i]',
      ];
    }

    if (host.includes("gemini.google.com")) {
      selectors = [
        'rich-textarea[aria-label*="prompt" i]',
        "rich-textarea",
        'textarea[placeholder*="prompt" i]',
        'textarea[aria-label*="prompt" i]',
        'div[contenteditable="true"][aria-label*="prompt" i]',
        'div[contenteditable="true"][role="textbox"]',
      ];
    }

    const elements = [
      ...document.querySelectorAll(selectors.join(",")),
    ].filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);

      return (
        rect.width > 150 &&
        rect.height > 30 &&
        rect.bottom > 0 &&
        rect.top < window.innerHeight &&
        style.display !== "none" &&
        style.visibility !== "hidden" &&
        style.opacity !== "0"
      );
    });

    if (!elements.length) {
      return null;
    }

    // Prefer the largest visible composer
    elements.sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();

      return br.width * br.height - ar.width * ar.height;
    });

    return elements[0];
  }

  // ------------------------------------------------------------
  // Read composer
  // ------------------------------------------------------------

  function readComposer(element) {
    if (!element) return "";

    if ("value" in element) {
      return element.value || "";
    }

    return (
      element.innerText ||
      element.textContent ||
      ""
    );
  }

  // ------------------------------------------------------------
  // Write optimized prompt back into composer
  // ------------------------------------------------------------

  function setComposer(element, value) {
    if (!element) return;

    element.focus();

    if ("value" in element) {
      const prototype =
        element.tagName === "TEXTAREA"
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;

      const setter =
        Object.getOwnPropertyDescriptor(
          prototype,
          "value"
        )?.set;

      if (setter) {
        setter.call(element, value);
      } else {
        element.value = value;
      }

      element.dispatchEvent(
        new Event("input", { bubbles: true })
      );

      element.dispatchEvent(
        new Event("change", { bubbles: true })
      );

      return;
    }

    // contenteditable / rich-textarea
    element.innerHTML = "";

    const textNode = document.createTextNode(value);

    element.appendChild(textNode);

    element.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        inputType: "insertText",
        data: value,
      })
    );
  }

  // ------------------------------------------------------------
  // Escape HTML
  // ------------------------------------------------------------

  function esc(value) {
    return String(value).replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[char]
    );
  }

  // ------------------------------------------------------------
  // Ask background service worker to optimize
  // ------------------------------------------------------------

  function optimizePrompt(prompt) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        {
          type: "OPTIMIZE_PROMPT",
          prompt,
        },
        (response) => {
          if (chrome.runtime.lastError) {
            reject(
              new Error(
                chrome.runtime.lastError.message
              )
            );
            return;
          }

          if (!response?.ok) {
            reject(
              new Error(
                response?.error ||
                  "Local optimization failed"
              )
            );
            return;
          }

          resolve(response.data);
        }
      );
    });
  }

  // ------------------------------------------------------------
  // Show optimized prompt modal
  // ------------------------------------------------------------

  function showModal(original, result) {
    document
      .getElementById("ps-modal")
      ?.remove();

    const before =
      result.original_tokens ?? est(original);

    const after =
      result.optimized_tokens ??
      est(result.optimized);

    const saved = Math.max(0, before - after);

    const percentage =
      before > 0
        ? (saved / before) * 100
        : 0;

    const modal = document.createElement("div");

    modal.id = "ps-modal";

    modal.innerHTML = `
      <div class="ps-backdrop"></div>

      <div class="ps-card">

        <div class="ps-head">

          <div>
            <small>LOCAL MODEL OPTIMIZER</small>
            <h2>Optimized prompt</h2>
          </div>

          <button id="ps-close">×</button>

        </div>

        <div class="ps-stats">

          <div>
            <small>Original</small>
            <b>${before.toLocaleString()}</b>
            <span>est. tokens</span>
          </div>

          <div>
            <small>Optimized</small>
            <b>${after.toLocaleString()}</b>
            <span>est. tokens</span>
          </div>

          <div class="green">
            <small>Saved</small>
            <b>${saved.toLocaleString()}</b>
            <span>${percentage.toFixed(1)}% less</span>
          </div>

        </div>

        <div class="cols">

          <section>
            <label>Original</label>
            <pre>${esc(original)}</pre>
          </section>

          <section>
            <label>Optimized</label>
            <pre class="opt">${esc(
              result.optimized || ""
            )}</pre>
          </section>

        </div>

        <p class="meta">
          <b>Model:</b>
          ${esc(result.model || "local")}
          &nbsp;•&nbsp;
          ${
            result.validation_passed
              ? "✓ preservation checks passed"
              : "⚠ review carefully"
          }
        </p>

        <div class="actions">

          <button id="ps-copy">
            Copy optimized
          </button>

          <button id="ps-use">
            Use optimized prompt
          </button>

        </div>

      </div>
    `;

    document.body.appendChild(modal);

    modal.querySelector("#ps-close").onclick =
      () => modal.remove();

    modal
      .querySelector(".ps-backdrop")
      .onclick = () => modal.remove();

    modal.querySelector("#ps-copy").onclick =
      async () => {
        try {
          await navigator.clipboard.writeText(
            result.optimized
          );

          const button =
            modal.querySelector("#ps-copy");

          button.textContent = "Copied ✓";

          setTimeout(() => {
            if (button) {
              button.textContent =
                "Copy optimized";
            }
          }, 1500);
        } catch (error) {
          console.error(
            "Copy failed:",
            error
          );
        }
      };

    modal.querySelector("#ps-use").onclick =
      () => {
        if (composer) {
          setComposer(
            composer,
            result.optimized
          );
        }

        modal.remove();
      };

    // Save statistics
    chrome.storage.local.get(
      ["stats"],
      ({ stats }) => {
        const s = stats || {
          prompts: 0,
          saved: 0,
          original: 0,
          optimized: 0,
        };

        chrome.storage.local.set({
          stats: {
            prompts: s.prompts + 1,
            saved: s.saved + saved,
            original: s.original + before,
            optimized:
              s.optimized + after,
          },
        });
      }
    );
  }

  // ------------------------------------------------------------
  // Create Optimize button
  // ------------------------------------------------------------

  function createOptimizeButton() {
    if (optimizeButton) {
      return optimizeButton;
    }

    const button =
      document.createElement("button");

    button.id = "ps-optimize";

    button.type = "button";

    button.textContent =
      "⚡ Optimize";

    button.title =
      "Optimize this prompt with your local model";

    button.addEventListener(
      "click",
      async (event) => {
        event.preventDefault();
        event.stopPropagation();

        if (!composer) {
          composer = getComposer();
        }

        if (!composer) {
          return;
        }

        const prompt =
          readComposer(composer).trim();

        if (!prompt) {
          button.textContent =
            "⚠ Enter a prompt";

          setTimeout(() => {
            if (button) {
              button.textContent =
                "⚡ Optimize";
            }
          }, 1500);

          return;
        }

        button.disabled = true;

        button.textContent =
          "⏳ Optimizing...";

        try {
          const result =
            await optimizePrompt(prompt);

          if (
            !result ||
            !result.optimized
          ) {
            throw new Error(
              "The local model returned no optimized prompt."
            );
          }

          showModal(
            prompt,
            result
          );

          button.textContent =
            "⚡ Optimize";
        } catch (error) {
          console.error(
            "Prompt optimization failed:",
            error
          );

          button.textContent =
            "❌ Failed";

          setTimeout(() => {
            if (button) {
              button.textContent =
                "⚡ Optimize";
            }
          }, 2000);
        } finally {
          button.disabled = false;
        }
      }
    );

    document.body.appendChild(button);

    optimizeButton = button;

    return button;
  }

  // ------------------------------------------------------------
  // Position button near composer
  // ------------------------------------------------------------

  function positionButton() {
    if (!composer || !optimizeButton) {
      return;
    }

    const rect =
      composer.getBoundingClientRect();

    const buttonRect =
      optimizeButton.getBoundingClientRect();

    let top =
      rect.top - buttonRect.height - 10;

    let left =
      rect.right - buttonRect.width;

    // If there isn't enough room above,
    // put it below the composer.
    if (top < 8) {
      top =
        rect.bottom + 10;
    }

    // Keep inside viewport
    left = Math.max(
      8,
      Math.min(
        left,
        window.innerWidth -
          buttonRect.width -
          8
      )
    );

    top = Math.max(8, top);

    optimizeButton.style.left =
      `${left}px`;

    optimizeButton.style.top =
      `${top}px`;
  }

  // ------------------------------------------------------------
  // Main attachment logic
  // ------------------------------------------------------------

  function attach() {
    if (attaching) return;

    attaching = true;

    try {
      const found =
        getComposer();

      if (!found) {
        composer = null;

        if (optimizeButton) {
          optimizeButton.remove();
          optimizeButton = null;
        }

        return;
      }

      composer = found;

      createOptimizeButton();

      positionButton();
    } finally {
      attaching = false;
    }
  }

  // ------------------------------------------------------------
  // Start once
  // ------------------------------------------------------------

  function startObserver() {
    if (observerStarted) {
      return;
    }

    observerStarted = true;

    const observer =
      new MutationObserver(() => {
        attach();
      });

    observer.observe(
      document.documentElement,
      {
        childList: true,
        subtree: true,
      }
    );

    window.addEventListener(
      "resize",
      positionButton,
      { passive: true }
    );

    window.addEventListener(
      "scroll",
      positionButton,
      {
        passive: true,
        capture: true,
      }
    );
  }

  // Initial load
  attach();

  startObserver();

  // AI websites frequently rebuild
  // their composer dynamically.
  setTimeout(attach, 500);
  setTimeout(attach, 1500);
  setTimeout(attach, 3000);
})();