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
  }
});
