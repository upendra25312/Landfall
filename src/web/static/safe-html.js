/* Sanitize every dashboard HTML sink before insertion; styles are assigned by
   trusted external code so the page needs no unsafe-inline CSP exception. */
function safeSetHTML(element, markup) {
  element.innerHTML = DOMPurify.sanitize(String(markup), {
    FORBID_TAGS: ['iframe', 'object', 'embed', 'form', 'input'],
    FORBID_ATTR: ['style'],
    ADD_ATTR: ['data-layout']
  });
  element.querySelectorAll('[data-layout]').forEach(node => {
    const declaration = node.getAttribute('data-layout') || '';
    node.removeAttribute('data-layout');
    if (/url\s*\(|expression|javascript|@|\\/i.test(declaration)) return;
    declaration.split(';').forEach(part => {
      const split = part.indexOf(':');
      if (split < 0) return;
      const property = part.slice(0, split).trim();
      const value = part.slice(split + 1).trim();
      if (/^(display|gap|align-items|justify-content|flex|flex-wrap|width|min-width|height|min-height|font-size|font-weight|color|background|border|border-top|border-width|border-radius|margin|margin-top|margin-bottom|margin-right|padding|padding-top|padding-left|opacity|overflow|text-overflow|white-space|text-align|text-transform|letter-spacing)$/.test(property)) {
        node.style.setProperty(property, value);
      }
    });
  });
}
