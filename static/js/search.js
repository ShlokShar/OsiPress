// Search is a plain form GET, so the server has no chance to render a loading
// state: it blocks inside hybrid_search (an embedding call plus two queries)
// and then returns the finished page. This swaps in the skeleton the moment a
// search is triggered, so the wait is filled rather than blank.

const form = document.querySelector('.searchbar');
const main = document.querySelector('main');
const skeleton = document.getElementById('search-skeleton');

// Frames are throttled in background tabs, so never let a missed frame swallow
// the navigation itself.
const PAINT_TIMEOUT_MS = 120;

let injected = null;
let concealed = [];

function queryOf(href){
  const match = /[?&]q=([^&]*)/.exec(href);
  if (!match) return '';
  try { return decodeURIComponent(match[1].replace(/\+/g, ' ')); }
  catch (e) { return ''; }
}

// Submitting a form starts the navigation immediately and the browser stops
// painting a document it is about to discard, so the skeleton would be built
// and never shown. Waiting two frames guarantees it has been painted before
// the page is torn down.
function navigateAfterPaint(go){
  let navigated = false;
  const once = () => {
    if (navigated) return;
    navigated = true;
    go();
  };
  requestAnimationFrame(() => requestAnimationFrame(once));
  setTimeout(once, PAINT_TIMEOUT_MS);
}

function showLoading(query){
  if (injected) return;

  const frag = skeleton.content.cloneNode(true);
  const status = frag.querySelector('[data-loading-status]');
  if (status && query) status.textContent = 'Searching for “' + query + '”…';

  // Conceal rather than discard: a page restored from the back/forward cache
  // needs its real content back, and there is nothing to re-render it from.
  // The inline fallback matters because `hidden` only takes effect through a
  // user-agent rule, which any author `display` declaration outranks.
  concealed = Array.from(main.children).filter(node => !node.hidden);
  concealed.forEach(node => {
    node.hidden = true;
    if (getComputedStyle(node).display !== 'none') node.style.display = 'none';
  });

  injected = document.createElement('div');
  injected.appendChild(frag);
  main.appendChild(injected);
  main.setAttribute('aria-busy', 'true');

  // Concealing the results shortens the page sharply, and "Show more results"
  // sits at the bottom of a long list, so the skeleton can land off-screen.
  window.scrollTo(0, 0);

  const button = form.querySelector('button');
  if (button) button.disabled = true;
}

function clearLoading(){
  if (!injected) return;
  injected.remove();
  injected = null;
  concealed.forEach(node => { node.hidden = false; node.style.display = ''; });
  concealed = [];
  main.removeAttribute('aria-busy');
  const button = form.querySelector('button');
  if (button) button.disabled = false;
}

if (form && main && skeleton){
  form.addEventListener('submit', event => {
    const input = form.querySelector('input[name="q"]');
    const query = input ? input.value.trim() : '';
    if (!query) return;

    event.preventDefault();
    showLoading(query);
    // form.submit() does not re-fire this handler, so there is no loop.
    navigateAfterPaint(() => form.submit());
  });

  // Topic pills, "Show more results" and the suggestion chips all navigate to
  // a fresh search, so they get the same treatment. The nav link carries no
  // query and is left alone.
  document.addEventListener('click', event => {
    if (event.defaultPrevented) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (event.button) return;

    const link = event.target && event.target.closest
      ? event.target.closest('a[href]')
      : null;
    if (!link || link.target === '_blank') return;

    const href = link.getAttribute('href') || '';
    if (!href.includes('q=') || !href.includes('search')) return;

    const destination = link.href;
    event.preventDefault();
    showLoading(queryOf(href));
    navigateAfterPaint(() => { window.location.href = destination; });
  });

  window.addEventListener('pageshow', event => {
    if (event.persisted) clearLoading();
  });
}
