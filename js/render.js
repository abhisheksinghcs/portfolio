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

  // Rewrite same-origin `.md` links to `.html` so the human view lands on
  // rendered pages. The raw `.md` files still contain `.md` links, which is
  // what AI agents want when they follow /llms.txt.
  //
  // Note: zero-md resolves relative URLs during rendering and writes them
  // back as absolute URLs (e.g. `/content/foo.md` becomes
  // `http://localhost:8000/content/foo.md`). We therefore check by origin,
  // not by whether the href starts with `http://` — otherwise same-origin
  // absolute URLs get skipped.
  const rewriteMdLinks = () => {
    const links = host.querySelectorAll('a[href$=".md"]');
    links.forEach((a) => {
      const href = a.getAttribute("href");
      if (!href) return;
      try {
        const url = new URL(href, location.href);
        if (url.origin !== location.origin) return; // external link
        url.pathname = url.pathname.replace(/\.md$/, ".html");
        a.setAttribute("href", url.href);
      } catch {
        /* malformed href — leave it alone */
      }
    });
  };

  if (location.protocol === "file:") {
    showError("file:// origin");
  } else {
    let rendered = false;
    let mermaidDone = false;

    host.addEventListener("zero-md-rendered", () => {
      rendered = true;
      try {
        // Mermaid must run exactly once. Re-processing a rendered SVG makes
        // mermaid.run read the SVG string as source and emit UnknownDiagramError.
        if (!mermaidDone) {
          mermaidDone = true;
          renderMermaidBlocks();
        }
        // Link rewrite is idempotent (regex only matches .md endings), so it's
        // safe to run on every re-render. Zero-md occasionally re-injects
        // content after its first event; this catches that case.
        rewriteMdLinks();
      } catch (e) {
        console.error("Post-render pass failed:", e);
      }
    });

    // Defense in depth: if the href attribute is never rewritten for any
    // reason (async re-injection, timing, cache), intercept the click and
    // redirect at navigation time. This guarantees the human view lands on
    // .html even when the visible href still says .md.
    host.addEventListener("click", (ev) => {
      const a = ev.target.closest && ev.target.closest('a[href$=".md"]');
      if (!a) return;
      const href = a.getAttribute("href");
      if (!href) return;
      try {
        const url = new URL(href, location.href);
        if (url.origin !== location.origin) return; // external link
        url.pathname = url.pathname.replace(/\.md$/, ".html");
        ev.preventDefault();
        location.href = url.href;
      } catch {
        /* malformed href — let the browser handle it */
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
