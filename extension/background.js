const SERVER = "http://127.0.0.1:8765";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "OPTIMIZE_PROMPT") return;

  fetch(`${SERVER}/optimize`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({prompt: message.prompt || ""})
  })
    .then(async response => {
      let data = {};
      try { data = await response.json(); } catch {}
      if (!response.ok) throw new Error(data.detail || `Local server error (${response.status})`);
      sendResponse({ok: true, data});
    })
    .catch(error => sendResponse({
      ok: false,
      error: `${error.message}. Make sure python server.py is running on 127.0.0.1:8765.`
    }));

  return true;
});
