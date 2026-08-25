(() => {
  const HOSTS = /chatgpt\.com|chat\.openai\.com|claude\.ai|gemini\.google\.com/;
  if (!HOSTS.test(location.hostname)) return;

  const state = { composer: null };

  const estimateTokens = text => Math.max(0, Math.ceil((text || "").trim().length / 4));

  // MVP optimizer: designed for messy/vague prompts.
  // It improves structure and removes filler without sending user data anywhere.
  function optimizePrompt(input) {
    let text = input.trim();
    if (!text) return { optimized: "", changes: [], score: 0 };

    const changes = [];
    const original = text;

    // Protect code blocks.
    const codeBlocks = [];
    text = text.replace(/```[\s\S]*?```/g, block => {
      const key = `__PS_CODE_${codeBlocks.length}__`;
      codeBlocks.push(block);
      return key;
    });

    // Normalize whitespace.
    text = text.replace(/\r/g, "").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n");

    // Remove conversational filler.
    const fillerRules = [
      [/\bhey[,! ]*/gi, ""],
      [/\bhi[,! ]*/gi, ""],
      [/\bhello[,! ]*/gi, ""],
      [/\bbasically\b/gi, ""],
      [/\bactually\b/gi, ""],
      [/\bjust\b/gi, ""],
      [/\bkind of\b/gi, ""],
      [/\bsort of\b/gi, ""],
      [/\bsomething like\b/gi, ""],
      [/\byou know\b/gi, ""],
      [/\bI mean\b/gi, ""],
      [/\bI think\b/gi, ""],
      [/\bI feel like\b/gi, ""],
      [/\bmaybe\b/gi, ""],
      [/\bperhaps\b/gi, ""],
      [/\bfor me\b/gi, ""],
      [/\bI would like you to\b/gi, ""],
      [/\bI want you to\b/gi, ""],
      [/\bI need you to\b/gi, ""],
      [/\bCould you please\b/gi, ""],
      [/\bCan you please\b/gi, ""],
      [/\bPlease kindly\b/gi, ""],
      [/\bif possible\b/gi, ""]
    ];

    let fillerCount = 0;
    for (const [re, replacement] of fillerRules) {
      const before = text;
      text = text.replace(re, replacement);
      if (text !== before) fillerCount++;
    }
    if (fillerCount) changes.push("Removed conversational filler");

    // Compact common wordy phrases.
    const phraseRules = [
      [/\bin order to\b/gi, "to"],
      [/\bdue to the fact that\b/gi, "because"],
      [/\bat this point in time\b/gi, "now"],
      [/\bwith regard to\b/gi, "regarding"],
      [/\bfor the purpose of\b/gi, "for"],
      [/\bin the event that\b/gi, "if"],
      [/\ba large number of\b/gi, "many"],
      [/\bmake sure that\b/gi, "ensure"],
      [/\bmake sure to\b/gi, "ensure"],
      [/\bI am currently working on\b/gi, "Working on"],
      [/\bI am trying to\b/gi, "I need to"],
      [/\bI would like to\b/gi, "I want to"]
    ];

    let phraseCount = 0;
    for (const [re, replacement] of phraseRules) {
      const before = text;
      text = text.replace(re, replacement);
      if (text !== before) phraseCount++;
    }
    if (phraseCount) changes.push("Simplified wordy phrases");

    // Turn rambling connectors into clearer separators.
    text = text.replace(/\s+and\s+also\s+/gi, " and ");
    text = text.replace(/\s+also\s+I\s+/gi, " I ");
    text = text.replace(/\s+then\s+also\s+/gi, " then ");

    // Normalize informal requirement language.
    const requirementRules = [
      [/\band I don't want\b/gi, ". Do not"],
      [/\band I do not want\b/gi, ". Do not"],
      [/\band don't\b/gi, ". Do not"],
      [/\bbut don't\b/gi, ". Do not"],
      [/\bI want\b/gi, "I need"],
      [/\bI wanna\b/gi, "I need to"],
      [/\bmake it\b/gi, "Make it"]
    ];

    let requirementCount = 0;
    for (const [re, replacement] of requirementRules) {
      const before = text;
      text = text.replace(re, replacement);
      if (text !== before) requirementCount++;
    }
    if (requirementCount) changes.push("Made requirements more explicit");

    // Deduplicate repeated sentences/lines while preserving order.
    const lines = text.split("\n");
    const seen = new Set();
    const kept = [];
    let duplicates = 0;
    for (const line of lines) {
      const clean = line.trim();
      const normalized = clean.toLowerCase().replace(/\s+/g, " ");
      if (normalized.length > 20 && seen.has(normalized)) {
        duplicates++;
        continue;
      }
      if (normalized.length > 20) seen.add(normalized);
      kept.push(line);
    }
    text = kept.join("\n");
    if (duplicates) changes.push("Removed repeated content");

    // If a single rambling paragraph contains many "and" connectors,
    // make the requirements easier to scan. This is intentionally conservative.
    const sentences = text.split(/(?<=[.!?])\s+/).filter(Boolean);
    if (sentences.length === 1 && (text.match(/\band\b/gi) || []).length >= 4) {
      const parts = text.split(/\s+and\s+/i).map(s => s.trim()).filter(Boolean);
      if (parts.length >= 4 && parts.every(p => p.length > 10)) {
        text = parts.map((p, i) => `${i === 0 ? "Task" : "-"} ${p.replace(/[.!?]+$/, "")}`).join("\n");
        changes.push("Structured rambling requirements");
      }
    }

    // Restore code blocks exactly.
    codeBlocks.forEach((block, i) => {
      text = text.replace(`__PS_CODE_${i}__`, block);
    });

    text = text
      .replace(/[ \t]+([,.;:!?])/g, "$1")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n[ \t]+/g, "\n")
      .trim();

    // Never claim a compression if the result got longer.
    if (estimateTokens(text) > estimateTokens(original)) {
      text = original;
      changes.length = 0;
      changes.push("Prompt was already concise; kept original");
    }

    const originalTokens = estimateTokens(original);
    const optimizedTokens = estimateTokens(text);
    const saved = Math.max(0, originalTokens - optimizedTokens);
    const reduction = originalTokens ? (saved / originalTokens) * 100 : 0;

    return {
      optimized: text,
      originalTokens,
      optimizedTokens,
      saved,
      reduction,
      changes
    };
  }

  function getComposer() {
    const selectors = [
      "textarea",
      '[contenteditable="true"]',
      '[role="textbox"]'
    ];
    return [...document.querySelectorAll(selectors.join(","))]
      .filter(el => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 120 && r.height > 25 && s.display !== "none" && s.visibility !== "hidden";
      })
      .sort((a, b) => {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        return br.width * br.height - ar.width * ar.height;
      })[0] || null;
  }

  function getText(el) {
    if (!el) return "";
    if ("value" in el) return el.value || "";
    return el.innerText || el.textContent || "";
  }

  function setText(el, value) {
    el.focus();
    if ("value" in el) {
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value")?.set;
      if (setter) setter.call(el, value); else el.value = value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      el.innerHTML = "";
      el.appendChild(document.createTextNode(value));
      el.dispatchEvent(new InputEvent("input", {
        bubbles: true, inputType: "insertText", data: value
      }));
    }
  }

  function showModal(result) {
    document.getElementById("ps-modal")?.remove();

    const modal = document.createElement("div");
    modal.id = "ps-modal";
    modal.innerHTML = `
      <div class="ps-backdrop"></div>
      <div class="ps-modal-card">
        <div class="ps-modal-head">
          <div>
            <div class="ps-kicker">PROMPT OPTIMIZER</div>
            <h2>Your prompt, cleaned up.</h2>
          </div>
          <button class="ps-x" id="ps-close">×</button>
        </div>

        <div class="ps-stats">
          <div><small>Original</small><strong>${result.originalTokens.toLocaleString()}</strong><span>est. tokens</span></div>
          <div><small>Optimized</small><strong>${result.optimizedTokens.toLocaleString()}</strong><span>est. tokens</span></div>
          <div class="ps-saving"><small>Saved</small><strong>${result.saved.toLocaleString()}</strong><span>${result.reduction.toFixed(1)}% less</span></div>
        </div>

        <div class="ps-columns">
          <section><label>Original</label><div class="ps-text">${escapeHtml(result.original)}</div></section>
          <section><label>Optimized</label><div class="ps-text ps-optimized">${escapeHtml(result.optimized)}</div></section>
        </div>

        <div class="ps-changes">
          <b>What changed</b>
          <ul>${result.changes.map(c => `<li>${escapeHtml(c)}</li>`).join("") || "<li>No changes needed</li>"}</ul>
        </div>

        <div class="ps-warning">Review the optimized prompt before sending. This MVP uses local rules and does not send your prompt to a server.</div>

        <div class="ps-modal-actions">
          <button class="ps-secondary" id="ps-copy">Copy optimized</button>
          <button class="ps-primary" id="ps-use">Use optimized prompt</button>
        </div>
      </div>
    `;
    document.body.appendChild(modal);

    modal.querySelector("#ps-close").onclick = () => modal.remove();
    modal.querySelector(".ps-backdrop").onclick = () => modal.remove();
    modal.querySelector("#ps-copy").onclick = async () => {
      await navigator.clipboard.writeText(result.optimized);
      const b = modal.querySelector("#ps-copy");
      b.textContent = "Copied";
      setTimeout(() => b.textContent = "Copy optimized", 1200);
    };
    modal.querySelector("#ps-use").onclick = () => {
      if (state.composer) setText(state.composer, result.optimized);
      modal.remove();
    };
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
    }[c]));
  }

  function addButton() {
    const composer = getComposer();
    if (!composer) return;

    state.composer = composer;
    let button = document.getElementById("ps-optimize");
    if (!button) {
      button = document.createElement("button");
      button.id = "ps-optimize";
      button.type = "button";
      button.innerHTML = "⚡ Optimize Prompt";
      button.addEventListener("click", e => {
        e.preventDefault();
        e.stopPropagation();
        const original = getText(state.composer).trim();
        if (!original) {
          button.textContent = "Type something first";
          setTimeout(() => button.innerHTML = "⚡ Optimize Prompt", 1300);
          return;
        }
        const result = optimizePrompt(original);
        result.original = original;
        showModal(result);

        chrome.storage.local.get(["stats"], ({stats}) => {
          const old = stats || {prompts:0, saved:0, original:0, optimized:0};
          chrome.storage.local.set({
            stats: {
              prompts: old.prompts + 1,
              saved: old.saved + result.saved,
              original: old.original + result.originalTokens,
              optimized: old.optimized + result.optimizedTokens
            }
          });
        });
      });
      document.body.appendChild(button);
    }

    const r = composer.getBoundingClientRect();
    button.style.left = `${Math.max(8, Math.min(window.innerWidth - 170, r.right - 160))}px`;
    button.style.top = `${Math.max(8, r.top - 45)}px`;
  }

  const observer = new MutationObserver(addButton);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("resize", addButton);
  setInterval(addButton, 1200);
  addButton();
})();