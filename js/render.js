// Shared render logic for content page wrappers.
//
// Rendering strategy:
// - zero-md fetches the .md and turns it into HTML.
// - Mermaid code blocks are replaced with <img> tags pointing at
//   https://mermaid.ink, which server-side renders Mermaid to SVG.
//   This avoids the flaky local Mermaid.js parser and works
//   consistently across browsers.
// - The raw .md still contains ```mermaid ``` blocks — AI agents
//   and crawlers read the Mermaid source directly.
//
// Failure modes handled:
// - file:// origin: browser blocks fetch() of the .md.
// - HTTP fetch failure: zero-md-error or 5s timeout.
// - mermaid.ink network failure: onerror falls back to a <pre> of the source.

const host = document.querySelector("zero-md");

if (host) {
  const mdSrc = host.getAttribute("src") || "";

  const showError = (reason) => {
    const isFileOrigin = location.protocol === "file:";
    host.innerHTML = `
      <div class="doc-error">
        <strong>Could not load the Markdown source.</strong>
        ${isFileOrigin ? `
          <p>This page was opened via <code>file://</code>. Browsers block
             <code>fetch()</code> on <code>file://</code> origins, so
             <code>${mdSrc}</code> could not be loaded.</p>
          <p>Serve the project over HTTP instead:</p>
          <pre>cd /Users/abhisingh/Downloads/code/portfolio
python3 -m http.server 8000</pre>
          <p>Then open
             <a href="http://localhost:8000${location.pathname}">
             http://localhost:8000${location.pathname}</a>.</p>
        ` : `
          <p>Failed to fetch <code>${mdSrc}</code>${reason ? ` (${reason})` : ""}.
             View the raw source: <a href="${mdSrc}">${mdSrc}</a>.</p>
        `}
      </div>
    `;
  };

  // UTF-8 safe base64 for the mermaid.ink URL param.
  const toB64 = (s) => btoa(unescape(encodeURIComponent(s)));

  const renderMermaidBlocks = () => {
    const codes = host.querySelectorAll("pre > code.language-mermaid");
    codes.forEach((code) => {
      const source = code.textContent;
      const img = document.createElement("img");
      img.className = "mermaid-diagram";
      img.src = `https://mermaid.ink/svg/${toB64(source)}`;
      img.alt = "Mermaid diagram";
      img.loading = "lazy";
      img.onerror = () => {
        const pre = document.createElement("pre");
        pre.className = "mermaid-fallback";
        pre.textContent = source;
        img.replaceWith(pre);
      };
      code.parentElement.replaceWith(img);
    });
  };

  if (location.protocol === "file:") {
    showError("file:// origin");
  } else {
    let rendered = false;
    let mermaidDone = false;

    host.addEventListener("zero-md-rendered", () => {
      rendered = true;
      if (mermaidDone) return;
      mermaidDone = true;
      try {
        renderMermaidBlocks();
      } catch (e) {
        console.error("Mermaid block replacement failed:", e);
      }
    });

    host.addEventListener("zero-md-error", (ev) => {
      if (!rendered) showError(ev?.detail?.message || "fetch failed");
    });

    setTimeout(() => {
      if (!rendered) showError("timeout after 5s");
    }, 5000);
  }
}
