const form = document.getElementById("lookup-form");
const input = document.getElementById("url");
const error = document.getElementById("error");

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
});

window.addEventListener("pageshow", () => {
  const button = form.querySelector("button");
  button.disabled = false;
  button.textContent = "Look up";
});

const status = document.getElementById("search-status");
if (status) {
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
        status.textContent = job.error;
        return;
      }
      setTimeout(poll, 2000);
    } catch {
      status.textContent = "Waiting for the comparison service to reconnect…";
      setTimeout(poll, 5000);
    }
  };
  setTimeout(poll, 1000);
}
