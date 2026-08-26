(() => {
  const SERVER = "http://127.0.0.1:8765";
  if (
    !/chatgpt\.com|chat\.openai\.com|claude\.ai|gemini\.google\.com/.test(
      location.hostname,
    )
  )
    return;
  let composer = null;
  const est = (t) => Math.max(0, Math.ceil((t || "").trim().length / 4));
function get() {
  const host = location.hostname;
  let selectors = [];

  if (host.includes("chatgpt.com") || host.includes("chat.openai.com")) {
    selectors = [
      'textarea[data-id="root"]',
      'textarea[placeholder*="Message"]',
      'div[contenteditable="true"][data-placeholder*="Message"]',
      'div[contenteditable="true"][role="textbox"]'
    ];
  } else if (host.includes("claude.ai")) {
    selectors = [
      'div[contenteditable="true"][role="textbox"]',
      'textarea[placeholder*="Reply"]',
      'textarea[placeholder*="message" i]'
    ];
  } else if (host.includes("gemini.google.com")) {
    selectors = [
      'rich-textarea[aria-label*="prompt" i]',
      'rich-textarea',
      'textarea[placeholder*="prompt" i]',
      'div[contenteditable="true"][aria-label*="prompt" i]',
      'div[contenteditable="true"][role="textbox"]'
    ];
  }

  const candidates = [...document.querySelectorAll(selectors.join(","))]
    .filter((e) => {
      const r = e.getBoundingClientRect();
      const s = getComputedStyle(e);

      return (
        r.width > 180 &&
        r.height > 35 &&
        r.bottom > 0 &&
        r.top < innerHeight &&
        s.display !== "none" &&
        s.visibility !== "hidden"
      );
    });

  return (
    candidates.sort((a, b) => {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();

      return (
        br.width * br.height -
        ar.width * ar.height
      );
    })[0] || null
  );
}
  function read(e) {
    return "value" in e ? e.value || "" : e.innerText || e.textContent || "";
  }
  function set(e, v) {
    e.focus();
    if ("value" in e) {
      let p =
          e.tagName === "TEXTAREA"
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype,
        s = Object.getOwnPropertyDescriptor(p, "value")?.set;
      s ? s.call(e, v) : (e.value = v);
      e.dispatchEvent(new Event("input", { bubbles: true }));
      e.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      e.innerHTML = "";
      e.appendChild(document.createTextNode(v));
      e.dispatchEvent(
        new InputEvent("input", {
          bubbles: true,
          inputType: "insertText",
          data: v,
        }),
      );
    }
  }
  function esc(s) {
    return String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  }
  function optimize(prompt) {
    return new Promise((resolve, reject) => {
      chrome.runtime.sendMessage(
        { type: "OPTIMIZE_PROMPT", prompt },
        (response) => {
          if (chrome.runtime.lastError)
            return reject(Error(chrome.runtime.lastError.message));
          if (!response?.ok)
            return reject(
              Error(response?.error || "Local optimization failed"),
            );
          resolve(response.data);
        },
      );
    });
  }
  function modal(original, x) {
    document.getElementById("ps-modal")?.remove();
    let before = x.original_tokens ?? est(original),
      after = x.optimized_tokens ?? est(x.optimized),
      saved = Math.max(0, before - after),
      pct = before ? (saved / before) * 100 : 0,
      m = document.createElement("div");
    m.id = "ps-modal";
    m.innerHTML = `<div class="ps-backdrop"></div><div class="ps-card"><div class="ps-head"><div><small>LOCAL MODEL OPTIMIZER</small><h2>Optimized prompt</h2></div><button id="ps-close">×</button></div><div class="ps-stats"><div><small>Original</small><b>${before.toLocaleString()}</b><span>est. tokens</span></div><div><small>Optimized</small><b>${after.toLocaleString()}</b><span>est. tokens</span></div><div class="green"><small>Saved</small><b>${saved.toLocaleString()}</b><span>${pct.toFixed(1)}% less</span></div></div><div class="cols"><section><label>Original</label><pre>${esc(original)}</pre></section><section><label>Optimized</label><pre class="opt">${esc(x.optimized)}</pre></section></div><p class="meta"><b>Model:</b> ${esc(x.model || "local")} &nbsp;•&nbsp; ${x.validation_passed ? "✓ preservation checks passed" : "⚠ review carefully"}</p><div class="actions"><button id="copy">Copy optimized</button><button id="use">Use optimized prompt</button></div></div>`;
    document.body.appendChild(m);
    m.querySelector("#ps-close").onclick = () => m.remove();
    m.querySelector(".ps-backdrop").onclick = () => m.remove();
    m.querySelector("#copy").onclick = async () => {
      await navigator.clipboard.writeText(x.optimized);
      m.querySelector("#copy").textContent = "Copied";
    };
    m.querySelector("#use").onclick = () => {
      if (composer) set(composer, x.optimized);
      m.remove();
    };
    chrome.storage.local.get(["stats"], ({ stats: s }) => {
      s = s || { prompts: 0, saved: 0, original: 0, optimized: 0 };
      chrome.storage.local.set({
        stats: {
          prompts: s.prompts + 1,
          saved: s.saved + saved,
          original: s.original + before,
          optimized: s.optimized + after,
        },
      });
    });
  }
function attach() {
  const allowed =
    /chatgpt\.com|chat\.openai\.com|claude\.ai|gemini\.google\.com/.test(
      location.hostname
    );

  const c = allowed ? get() : null;
  const existing = document.getElementById("ps-optimize");

  if (!c) {
    if (existing) existing.remove();
    composer = null;
    return;
  }

  composer = c;
  new MutationObserver(attach).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
  addEventListener("resize", attach);
  setInterval(attach, 1500);
  attach();
}
})();
