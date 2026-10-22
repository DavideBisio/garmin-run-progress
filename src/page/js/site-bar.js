/* Copied from site-kit v0.1.2 (DavideBisio/site-kit@ef6ed2586d40a45e27228d4734d5a2abe58575d2) src/elements/site-bar.js.
 * Do not edit: re-copy it together with vendor/tokens.css when upgrading site-kit (docs/deploy.md). */
/*
 * <site-bar>: the shared top bar for pages that are not built with Astro (the vanilla
 * apps). Same look, owner link and theme switch as the Astro Header.
 *
 *   <script src="site-bar.js"></script>   (classic or type="module", or inlined)
 *   <site-bar project="Run Progress Lab" home="../" repo="https://github.com/DavideBisio/garmin-run-progress">
 *     <a slot="links" href="../docs/">Docs</a>
 *   </site-bar>
 *
 * Attributes
 *   project      project name (links to `home`)
 *   home         URL of the project site's landing page (default "./")
 *   owner        owner name (default "Davide Bisio")
 *   owner-href   hub URL (default "https://davidebisio.github.io/")
 *   repo         repository URL; adds a "Source" link
 *   no-theme     hide the theme switch, for apps that only follow the OS setting
 *   wide         use the 72rem container instead of 48rem
 *
 * Self-contained: no imports, no network, and styles go through a constructable
 * stylesheet, so it runs under a strict CSP (script-src 'self'; style-src 'self';
 * connect-src 'none') and can be inlined into a single-file build. Colors read the
 * --sk-* tokens when tokens.css is on the page and fall back to the same values when not.
 * Theme choice is shared with the Astro sites through localStorage "theme".
 */
(function () {
  'use strict';
  if (typeof window === 'undefined' || !window.customElements || customElements.get('site-bar')) return;

  var KEY = 'theme';

  function storedTheme() {
    try {
      var t = localStorage.getItem(KEY);
      return t === 'light' || t === 'dark' ? t : null;
    } catch (e) {
      return null;
    }
  }

  function currentTheme() {
    var t = document.documentElement.dataset.theme;
    if (t === 'light' || t === 'dark') return t;
    return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  var CSS = [
    ':host{',
    '  --bar-ink:var(--sk-ink,#1e232a);--bar-muted:var(--sk-muted,#45556c);--bar-link:var(--sk-link,#b8443b);',
    '  --bar-line:var(--sk-line,#e2e8f0);--bar-bg:var(--sk-bg,#f2ede4);',
    '  display:block;background:var(--bar-bg);color:var(--bar-ink);border-bottom:1px solid var(--bar-line);',
    "  font:var(--sk-text-md,1rem)/1.5 var(--sk-font-sans,'Inter Variable','Inter',ui-sans-serif,system-ui,-apple-system,'Segoe UI',sans-serif);",
    '}',
    ':host([data-theme=dark]){',
    '  --bar-ink:var(--sk-ink,#f2ede4);--bar-muted:var(--sk-muted,#62a6a5);--bar-link:var(--sk-link,#f9a23e);',
    '  --bar-line:var(--sk-line,#4c908f);--bar-bg:var(--sk-bg,#1e232a);',
    '}',
    '*{box-sizing:border-box}',
    'nav{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:.5rem 1.5rem;',
    '  max-width:var(--sk-width-narrow,48rem);margin:0 auto;padding:1rem var(--sk-gutter,1rem)}',
    ':host([wide]) nav{max-width:var(--sk-width-wide,72rem)}',
    '.brand{display:flex;align-items:center;gap:.75rem;min-width:0;font-weight:600;letter-spacing:-.01em}',
    '.brand a{color:inherit;text-decoration:none}',
    '.brand a:hover{color:var(--bar-link)}',
    '.owner{color:var(--bar-muted)!important;font-weight:500}',
    '.sep{color:var(--bar-muted)}',
    '.links{display:flex;flex-wrap:wrap;align-items:center;gap:.25rem 1.5rem;font-size:var(--sk-text-sm,.875rem)}',
    '.links a,::slotted(a){color:var(--bar-muted);text-decoration:none;padding:.5rem 0}',
    '.links a:hover,::slotted(a:hover){color:var(--bar-link)}',
    'a:focus-visible,button:focus-visible{outline:2px solid var(--sk-focus,#f9a23e);outline-offset:2px;border-radius:4px}',
    'button{display:inline-grid;place-items:center;width:2.25rem;height:2.25rem;padding:0;border:0;border-radius:.5rem;',
    '  background:none;color:var(--bar-muted);cursor:pointer}',
    'button:hover{color:var(--bar-link)}',
    'svg{width:1.1rem;height:1.1rem}',
    '.sun{display:none}',
    ':host([data-theme=dark]) .sun{display:block}',
    ':host([data-theme=dark]) .moon{display:none}',
    '[hidden]{display:none!important}',
  ].join('\n');

  var sheet = null;
  function applyStyles(root) {
    try {
      if (!sheet) {
        sheet = new CSSStyleSheet();
        sheet.replaceSync(CSS);
      }
      root.adoptedStyleSheets = [sheet];
    } catch (e) {
      // Older browsers: a <style> element (blocked by a strict style-src, but those
      // browsers predate the CSP rule anyway).
      var style = document.createElement('style');
      style.textContent = CSS;
      root.appendChild(style);
    }
  }

  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    for (var k in attrs) if (attrs[k] != null) node.setAttribute(k, attrs[k]);
    if (text) node.textContent = text;
    return node;
  }

  var SUN =
    '<svg class="sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"></path></svg>';
  var MOON =
    '<svg class="moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"></path></svg>';

  class SiteBar extends HTMLElement {
    static get observedAttributes() {
      return ['project', 'home', 'owner', 'owner-href', 'repo', 'no-theme'];
    }

    constructor() {
      super();
      this.attachShadow({ mode: 'open' });
      applyStyles(this.shadowRoot);
      this._onTheme = this._syncTheme.bind(this);
    }

    connectedCallback() {
      // Apply a stored choice before the app paints much (apps that understand
      // data-theme follow it; others ignore it).
      if (!this.hasAttribute('no-theme')) {
        var stored = storedTheme();
        if (stored && !document.documentElement.dataset.theme) document.documentElement.dataset.theme = stored;
      }
      this._render();
      this._observer = new MutationObserver(this._onTheme);
      this._observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
      if (window.matchMedia) {
        this._mq = matchMedia('(prefers-color-scheme: dark)');
        this._mq.addEventListener && this._mq.addEventListener('change', this._onTheme);
      }
    }

    disconnectedCallback() {
      if (this._observer) this._observer.disconnect();
      if (this._mq && this._mq.removeEventListener) this._mq.removeEventListener('change', this._onTheme);
    }

    attributeChangedCallback() {
      if (this.isConnected) this._render();
    }

    _render() {
      var root = this.shadowRoot;
      var keep = root.adoptedStyleSheets;
      root.replaceChildren();
      if (!keep || !keep.length) applyStyles(root);

      var nav = el('nav', { 'aria-label': 'Site' });
      var brand = el('div', { class: 'brand' });
      var project = this.getAttribute('project');
      var owner = el('a', { class: 'owner', href: this.getAttribute('owner-href') || 'https://davidebisio.github.io/' }, this.getAttribute('owner') || 'Davide Bisio');
      brand.appendChild(owner);
      if (project) {
        brand.appendChild(el('span', { class: 'sep', 'aria-hidden': 'true' }, '/'));
        brand.appendChild(el('a', { href: this.getAttribute('home') || './' }, project));
      }

      var links = el('div', { class: 'links' });
      links.appendChild(el('slot', { name: 'links' }));
      var repo = this.getAttribute('repo');
      if (repo && /^https:\/\//.test(repo)) links.appendChild(el('a', { href: repo, target: '_blank', rel: 'noopener noreferrer' }, 'Source'));

      var button = el('button', { type: 'button' });
      button.innerHTML = SUN + MOON; // static markup above, no user input
      button.hidden = this.hasAttribute('no-theme');
      button.addEventListener('click', function () {
        var next = currentTheme() === 'dark' ? 'light' : 'dark';
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem(KEY, next);
        } catch (e) {}
      });
      links.appendChild(button);
      this._button = button;

      nav.appendChild(brand);
      nav.appendChild(links);
      root.appendChild(nav);
      this._syncTheme();
    }

    _syncTheme() {
      var theme = this.hasAttribute('no-theme')
        ? window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches
          ? 'dark'
          : 'light'
        : currentTheme();
      this.setAttribute('data-theme', theme);
      if (this._button) this._button.setAttribute('aria-label', theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme');
    }
  }

  customElements.define('site-bar', SiteBar);
})();
