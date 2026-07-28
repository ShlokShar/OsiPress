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


// ---------------------------------------------------------------------------
// Filters
//
// Country, outlet and sort all run against the rows already on the page, so no
// request is made and main.py never sees them. Controls mirror the Countries
// chips and Topics dropdown on today/archive (see renderChips /
// renderTopicOptions in osipress.js) so the existing styles apply unchanged.
// ---------------------------------------------------------------------------

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const resultList = document.querySelector('.results:not([aria-hidden="true"])');
const rows = resultList ? Array.from(resultList.querySelectorAll(':scope > .story')) : [];

const filters = { countries: new Set(), outlets: new Set(), sort: 'relevance' };

const SORTS = [
  { id: 'relevance', label: 'Relevance' },
  { id: 'newest', label: 'Newest first' },
  { id: 'oldest', label: 'Oldest first' },
];

// data-published is a display string ("20 Jun 2026") because that is what the
// result dict carries. Date.parse of that format is implementation-defined, so
// pick it apart by hand.
function publishedAt(row){
  const parts = (row.dataset.published || '').split(' ');
  if (parts.length !== 3) return 0;
  const month = MONTHS.indexOf(parts[1]);
  if (month < 0) return 0;
  return Date.UTC(Number(parts[2]), month, Number(parts[0]));
}

function distinct(attribute){
  return [...new Set(rows.map(row => row.dataset[attribute]).filter(Boolean))].sort();
}

function matches(row){
  if (filters.countries.size && !filters.countries.has(row.dataset.country)) return false;
  if (filters.outlets.size && !filters.outlets.has(row.dataset.outlet)) return false;
  return true;
}

function applyFilters(){
  const visible = [];
  rows.forEach(row => {
    const show = matches(row);
    row.hidden = !show;
    row.classList.remove('first-visible');
    if (show) visible.push(row);
  });

  const ordered = visible.slice();
  if (filters.sort === 'relevance'){
    ordered.sort((a, b) => Number(a.dataset.rank) - Number(b.dataset.rank));
  } else {
    const direction = filters.sort === 'newest' ? -1 : 1;
    ordered.sort((a, b) => (publishedAt(a) - publishedAt(b)) * direction);
  }
  // Move nodes rather than using CSS order: `.story + .story` draws the
  // separator from DOM order, so visual-only reordering misplaces it.
  ordered.forEach(row => resultList.appendChild(row));

  // A hidden first row would otherwise leave its separator on the row below.
  if (ordered.length) ordered[0].classList.add('first-visible');

  const emptyNote = document.getElementById('filter-empty');
  if (emptyNote) emptyNote.hidden = ordered.length > 0;

  syncControls();
  syncUrl();
}

function syncUrl(){
  const params = new URLSearchParams(window.location.search);
  const set = (key, value) => value ? params.set(key, value) : params.delete(key);

  set('country', [...filters.countries].join(','));
  set('outlet', [...filters.outlets].join(','));
  set('sort', filters.sort === 'relevance' ? '' : filters.sort);

  const query = params.toString();
  window.history.replaceState(null, '',
    window.location.pathname + (query ? '?' + query : ''));

  // Keep the filters through "Show more", which is a real navigation.
  const more = document.querySelector('.more a');
  if (more) more.search = new URLSearchParams({
    ...Object.fromEntries(new URLSearchParams(more.search)),
    ...Object.fromEntries(params),
  }).toString();
}

function readUrl(){
  const params = new URLSearchParams(window.location.search);
  const load = (key, target) => (params.get(key) || '')
    .split(',').filter(Boolean).forEach(value => target.add(value));

  load('country', filters.countries);
  load('outlet', filters.outlets);
  const sort = params.get('sort');
  if (SORTS.some(option => option.id === sort)) filters.sort = sort;
}

function buildChips(container, values, selected){
  container.innerHTML = '';
  values.forEach(value => {
    const chip = document.createElement('button');
    chip.type = 'button';
    chip.className = 'chip';
    chip.textContent = value;
    chip.dataset.value = value;
    chip.setAttribute('aria-pressed', selected.has(value) ? 'true' : 'false');
    chip.addEventListener('click', () => {
      if (selected.has(value)) selected.delete(value);
      else selected.add(value);
      applyFilters();
    });
    container.appendChild(chip);
  });
}

function buildOptions(panel, values, onPick, isChecked, role){
  panel.innerHTML = '';
  values.forEach(value => {
    const option = document.createElement('button');
    option.type = 'button';
    option.className = 'dd-opt';
    option.dataset.value = value.id || value;
    option.setAttribute('role', role);
    option.setAttribute('aria-checked', isChecked(value) ? 'true' : 'false');

    const box = document.createElement('span');
    box.className = 'dd-box';
    const label = document.createElement('span');
    label.textContent = value.label || value;

    option.append(box, label);
    option.addEventListener('click', () => { onPick(value); applyFilters(); });
    panel.appendChild(option);
  });
}

// Every dropdown registers here so opening one can close the rest. A
// per-dropdown outside-click listener is not enough: the toggle stops
// propagation, so its click never reaches the other dropdown's listener and
// both panels stay open.
const dropdowns = [];

function setDropdown(entry, open){
  entry.panel.hidden = !open;
  entry.toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}

function closeDropdowns(except){
  dropdowns.forEach(entry => { if (entry !== except) setDropdown(entry, false); });
}

function wireDropdown(picker, toggle, panel){
  const entry = { picker, toggle, panel };
  dropdowns.push(entry);
  toggle.addEventListener('click', event => {
    event.stopPropagation();
    const open = panel.hidden;
    closeDropdowns(entry);
    setDropdown(entry, open);
  });
}

// One shared listener: a click inside a panel keeps that panel open (outlet is
// multi-select), anything else closes them all.
document.addEventListener('click', event => {
  closeDropdowns(dropdowns.find(entry => entry.picker.contains(event.target)));
});

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeDropdowns(null);
});

function syncControls(){
  document.querySelectorAll('#country-chips .chip').forEach(chip => {
    chip.setAttribute('aria-pressed',
      filters.countries.has(chip.dataset.value) ? 'true' : 'false');
  });

  const outletPanel = document.getElementById('outlet-panel');
  const outletValue = document.getElementById('outlet-value');
  const outletToggle = document.getElementById('outlet-toggle');
  if (outletPanel){
    Array.from(outletPanel.children).forEach(option => {
      option.setAttribute('aria-checked',
        filters.outlets.has(option.dataset.value) ? 'true' : 'false');
    });
    const count = filters.outlets.size;
    outletValue.textContent = count === 0 ? 'All' : count + ' selected';
    outletToggle.classList.toggle('has-selection', count > 0);
  }

  const sortPanel = document.getElementById('sort-panel');
  const sortValue = document.getElementById('sort-value');
  const sortToggle = document.getElementById('sort-toggle');
  if (sortPanel){
    Array.from(sortPanel.children).forEach(option => {
      option.setAttribute('aria-checked',
        option.dataset.value === filters.sort ? 'true' : 'false');
    });
    const active = SORTS.find(option => option.id === filters.sort);
    sortValue.textContent = active ? active.label : 'Relevance';
    sortToggle.classList.toggle('has-selection', filters.sort !== 'relevance');
  }
}

if (rows.length){
  readUrl();

  const countries = distinct('country');
  const outlets = distinct('outlet');

  // Same rule as renderTopicOptions(): a picker with nothing to choose between
  // is hidden rather than shown as a dead control.
  const countryPicker = document.getElementById('country-picker');
  if (countries.length < 2) countryPicker.hidden = true;
  else buildChips(document.getElementById('country-chips'), countries, filters.countries);

  const outletPicker = document.getElementById('outlet-picker');
  if (outlets.length < 2) outletPicker.hidden = true;
  else {
    const panel = document.getElementById('outlet-panel');
    buildOptions(panel, outlets,
      value => {
        if (filters.outlets.has(value)) filters.outlets.delete(value);
        else filters.outlets.add(value);
      },
      value => filters.outlets.has(value), 'menuitemcheckbox');
    wireDropdown(outletPicker, document.getElementById('outlet-toggle'), panel);
  }

  const sortPicker = document.getElementById('sort-picker');
  const sortPanel = document.getElementById('sort-panel');
  buildOptions(sortPanel, SORTS,
    option => { filters.sort = option.id; sortPanel.hidden = true;
                document.getElementById('sort-toggle')
                  .setAttribute('aria-expanded', 'false'); },
    option => option.id === filters.sort, 'menuitemradio');
  wireDropdown(sortPicker, document.getElementById('sort-toggle'), sortPanel);

  applyFilters();
}
