const S = "http://127.0.0.1:8765";
fetch(S + "/health")
  .then((r) => r.json())
  .then((d) => {
    document.getElementById("dot").style.background = d.ok
      ? "#10b981"
      : "#f59e0b";
    document.getElementById("status").textContent = d.ok
      ? "Local model ready"
      : "Model not installed";
    document.getElementById("model").textContent = d.model || "Ollama";
  })
  .catch(() => {
    document.getElementById("dot").style.background = "#ef4444";
    document.getElementById("status").textContent = "Local server offline";
    document.getElementById("model").textContent = "Start local_server/run.bat";
  });
chrome.storage.local.get(["stats"], ({ stats: s }) => {
  s = s || { prompts: 0, saved: 0, original: 0, optimized: 0 };
  document.getElementById("saved").textContent = s.saved.toLocaleString();
  document.getElementById("prompts").textContent = s.prompts.toLocaleString();
  let r = s.original
    ? Math.max(0, ((s.original - s.optimized) / s.original) * 100)
    : 0;
  document.getElementById("reduction").textContent = r.toFixed(1) + "%";
  document.getElementById("bar").style.width = Math.min(100, r) + "%";
});
