// Relative URL: resolves under the App's prefix, whatever it is.
fetch("api/whoami")
  .then((r) => r.json())
  .then((body) => { document.getElementById("whoami").textContent = JSON.stringify(body); });
