const form = document.getElementById("lookup-form");
const input = document.getElementById("url");
const error = document.getElementById("error");
const progress = document.getElementById("search-progress");
const status = document.getElementById("search-status");

form.addEventListener("submit", (e) => {
  error.textContent = "";
  try {
    const u = new URL(input.value.trim());
    if (u.protocol !== "http:" && u.protocol !== "https:") throw new Error();
  } catch {
    e.preventDefault();
    error.textContent = "Please enter a valid http(s) URL.";
    return;
  }
  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "Searching…";
  // The browser stays on this page until the comparison finishes (or the pending page loads),
  // so show that the search is running. A new search replaces any earlier pending status.
  progress.hidden = false;
  if (status) status.hidden = true;
});

// Coming back with the Back button can restore this page from the cache mid-search: reset it.
window.addEventListener("pageshow", () => {
  const button = form.querySelector("button");
  button.disabled = false;
  button.textContent = "Look up";
  progress.hidden = true;
  if (status) status.hidden = false;
});

if (status) {
  const text = document.getElementById("search-status-text");
  const show = (message, busy) => {
    text.textContent = message;
    status.classList.toggle("stopped", !busy);
  };
  const poll = async () => {
    try {
      const response = await fetch(status.dataset.statusUrl);
      if (!response.ok) throw new Error();
      const job = await response.json();
      if (job.status === "complete") {
        window.location.replace(status.dataset.resultUrl);
        return;
      }
      if (job.status === "failed") {
        show(job.error, false);
        return;
      }
      setTimeout(poll, 2000);
    } catch {
      show("Waiting for the comparison service to reconnect…", true);
      setTimeout(poll, 5000);
    }
  };
  setTimeout(poll, 1000);
}
