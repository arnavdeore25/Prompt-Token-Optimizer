chrome.storage.local.get(["stats"], ({stats}) => {
  const s = stats || {prompts:0,saved:0,original:0,optimized:0};
  document.getElementById("saved").textContent = (s.saved || 0).toLocaleString();
  document.getElementById("prompts").textContent = (s.prompts || 0).toLocaleString();
  const reduction = s.original ? Math.max(0, ((s.original - s.optimized) / s.original) * 100) : 0;
  document.getElementById("reduction").textContent = `${reduction.toFixed(1)}%`;
  document.getElementById("bar").style.width = `${Math.min(100, reduction)}%`;
});