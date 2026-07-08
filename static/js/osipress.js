/* ------------------------------------------------------------------ *
 * OsiPress front-page board
 * Data source: <script id="osipress-data"> populated by Flask via
 *   {{ data | tojson }}. Shape:
 *   { "<Country>": { "<Outlet>": [ story, ... ], ... }, ... }
 *   story = { id, source_id, headline, translated_headline, link,
 *             summary, references_original[], references_translated[] }
 * ------------------------------------------------------------------ */

/* Political-spectrum lookup by outlet name (left = red, center = grey-purple,
   right = blue). Outlets not listed simply render without a tag. */
const LEAN = {
  'Kayhan':           { label: 'hardline',      lean: 'right'  },
  'Hamshahri':        { label: 'centrist',      lean: 'center' },
  'Shargh':           { label: 'reformist',     lean: 'left'   },
  'Haaretz':          { label: 'left-leaning',  lean: 'left'   },
  'Yedioth Ahronoth': { label: 'centrist',      lean: 'center' },
  'Israel Hayom':     { label: 'right-leaning', lean: 'right'  },
};

/* Native-script label shown next to each country header. */
const SCRIPT_LABEL = {
  'Iran':   { name: 'Persian', native: 'فارسی' },
  'Israel': { name: 'Hebrew',  native: 'עברית' },
};

/* ---------- load Flask-injected data ---------- */
function loadData(){
  const node = document.getElementById('osipress-data');
  try {
    const parsed = JSON.parse(node.textContent);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
  } catch (e) { /* not rendered through Flask */ }
  return {};
}
const DATA = loadData();

/* ---------- state ---------- */
const countries = Object.keys(DATA);
const state = {
  selected: countries.slice(0, 2),                       // default: compare first two
  order: {},                                             // country -> [outlet names]
  expanded: {},                                          // key -> bool
  translated: {},                                        // key -> bool
};
countries.forEach(c => { state.order[c] = Object.keys(DATA[c]); });

const keyOf = (country, outlet, i) => country + '|' + outlet + '|' + i;
const APOLOGY = /^(i can'?t|no content|the provided article content is empty)/i;
const cleanSummary = s => (s && s.trim() && !APOLOGY.test(s.trim())) ? s.trim() : '';

/* ---------- element helpers ---------- */
function el(tag, cls, txt){
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (txt != null) n.textContent = txt;
  return n;
}
function hostOf(url){
  try { return new URL(url).hostname.replace(/^www\./, ''); }
  catch (e) { return 'source'; }
}

/* ---------- story ---------- */
function buildStory(country, outlet, story, i){
  const key = keyOf(country, outlet, i);
  const wrap = el('div', 'story');

  const row = el('div', 'story-row');
  row.setAttribute('role', 'button');
  const num = el('span', 'num', String(i + 1).padStart(2, '0'));
  const main = el('div', 'story-main');
  main.appendChild(el('h3', null, story.translated_headline || ''));

  const orig = (story.headline || '').trim();
  const trans = (story.translated_headline || '').trim();
  if (orig && orig !== trans){
    const ol = el('div', 'orig-line');
    ol.appendChild(el('span', 'orig-label', 'Original'));
    const o = el('span', 'orig', story.headline);
    o.setAttribute('dir', 'auto');
    ol.appendChild(o);
    main.appendChild(ol);
  }
  const chev = el('span', 'chev');
  row.appendChild(num); row.appendChild(main); row.appendChild(chev);

  const detail = el('div', 'story-detail');

  const sum = cleanSummary(story.summary);
  if (sum){
    const p = el('p', 'summary', sum);
    p.setAttribute('dir', 'auto');
    detail.appendChild(p);
  }

  const refsO = story.references_original || [];
  const refsT = story.references_translated || [];
  if (refsO.length || refsT.length){
    const block = el('div', 'refs-block');
    const head = el('div', 'refs-head');
    head.appendChild(el('span', 'cap', 'Quoted from the article'));
    const identical = JSON.stringify(refsO) === JSON.stringify(refsT);
    let btn = null;
    if (!identical && refsT.length){
      btn = el('button', 'translate', 'Show translation');
    }
    if (btn) head.appendChild(btn);
    block.appendChild(head);

    const list = el('div', 'ref-list');
    const paint = () => {
      const showT = !!state.translated[key];
      const arr = (showT && refsT.length) ? refsT : refsO;
      list.innerHTML = '';
      arr.forEach(t => {
        const p = el('p', 'ref', t);
        p.setAttribute('dir', 'auto');
        list.appendChild(p);
      });
      if (btn) btn.textContent = showT ? 'Show original' : 'Show translation';
    };
    if (btn){
      btn.addEventListener('click', e => {
        e.stopPropagation();
        state.translated[key] = !state.translated[key];
        paint();
      });
    }
    paint();
    block.appendChild(list);
    detail.appendChild(block);
  }

  if (story.link){
    const a = el('a', 'readlink', 'Read at ' + hostOf(story.link) + ' \u2197');
    a.href = story.link; a.target = '_blank'; a.rel = 'noopener';
    a.addEventListener('click', e => e.stopPropagation());
    detail.appendChild(a);
  }

  const setOpen = (open) => {
    state.expanded[key] = open;
    detail.classList.toggle('hidden', !open);
    chev.textContent = open ? '\u25be' : '\u25b8';
  };
  row.addEventListener('click', () => setOpen(!state.expanded[key]));
  setOpen(state.expanded[key] ?? false);

  wrap.appendChild(row);
  wrap.appendChild(detail);
  return wrap;
}

/* ---------- outlet card ---------- */
function buildCard(country, outlet){
  const card = el('article', 'card');
  card.dataset.country = country;
  card.dataset.outlet = outlet;
  card.setAttribute('draggable', 'true');

  const head = el('div', 'card-head');
  const handle = el('span', 'handle', '\u2847');
  handle.title = 'Drag to reorder';
  handle.setAttribute('aria-label', 'Drag to reorder');
  head.appendChild(handle);
  head.appendChild(el('span', 'outlet-name', outlet));
  const lean = LEAN[outlet];
  if (lean) head.appendChild(el('span', 'tag ' + lean.lean, lean.label));
  card.appendChild(head);

  const stories = el('div', 'stories');
  (DATA[country][outlet] || []).forEach((s, i) => stories.appendChild(buildStory(country, outlet, s, i)));
  card.appendChild(stories);

  wireDrag(card, handle, country);
  return card;
}

/* ---------- drag reorder (within a country) ---------- */
let armed = false, dragCountry = null, draggingEl = null;
function wireDrag(card, handle, country){
  handle.addEventListener('mousedown', () => { armed = true; });
  card.addEventListener('dragstart', e => {
    if (!armed){ e.preventDefault(); return; }
    dragCountry = country; draggingEl = card;
    e.dataTransfer.effectAllowed = 'move';
    try { e.dataTransfer.setData('text/plain', card.dataset.outlet); } catch (_) {}
    setTimeout(() => card.classList.add('dragging'), 0);
  });
  card.addEventListener('dragover', e => {
    if (!draggingEl || dragCountry !== country) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    if (card === draggingEl) return;
    const compare = board.dataset.mode === 'compare';
    const rect = card.getBoundingClientRect();
    const before = compare
      ? (e.clientY < rect.top + rect.height / 2)
      : (e.clientX < rect.left + rect.width / 2);
    const cur = state.order[country];
    const dragName = draggingEl.dataset.outlet;
    const targetName = card.dataset.outlet;
    const without = cur.filter(x => x !== dragName);
    let idx = without.indexOf(targetName);
    if (!before) idx += 1;
    const next = [...without.slice(0, idx), dragName, ...without.slice(idx)];
    if (next.join() !== cur.join()){ state.order[country] = next; relayout(); }
  });
  card.addEventListener('drop', e => e.preventDefault());
  card.addEventListener('dragend', () => {
    card.classList.remove('dragging');
    armed = false; dragCountry = null; draggingEl = null;
  });
}

/* ---------- render skeleton (headers + all cards) ---------- */
const board = document.getElementById('board');
const emptyNote = document.getElementById('empty');
const headerEls = {};   // country -> header el
const cardEls = {};     // country -> { outlet -> card el }

function render(){
  board.innerHTML = '';
  if (!countries.length){
    if (emptyNote) emptyNote.hidden = false;
    return;
  }
  countries.forEach(country => {
    const h = el('div', 'col-header');
    h.dataset.country = country;
    h.appendChild(el('h2', null, country));
    const sl = SCRIPT_LABEL[country];
    if (sl){
      const sub = el('span', 'sub');
      sub.appendChild(document.createTextNode(sl.name + ' \u00b7 '));
      const nat = el('span', null, sl.native);
      nat.setAttribute('dir', 'auto');
      sub.appendChild(nat);
      h.appendChild(sub);
    }
    headerEls[country] = h;
    board.appendChild(h);

    cardEls[country] = {};
    Object.keys(DATA[country]).forEach(outlet => {
      const c = buildCard(country, outlet);
      cardEls[country][outlet] = c;
      board.appendChild(c);
    });
  });
  relayout();
}

/* ---------- layout: selected countries side by side, or one wide ---------- */
function relayout(){
  const sel = state.selected.filter(c => countries.includes(c));
  const compare = sel.length === 2;
  board.dataset.mode = compare ? 'compare' : 'single';

  countries.forEach(country => {
    const shown = sel.includes(country);
    if (headerEls[country]) headerEls[country].style.display = shown ? 'flex' : 'none';
    Object.values(cardEls[country] || {}).forEach(c => { c.style.display = shown ? 'flex' : 'none'; });
  });

  if (compare){
    sel.forEach((country, colIdx) => {
      const col = colIdx + 1;
      const h = headerEls[country];
      h.style.gridColumn = String(col); h.style.gridRow = '1'; h.style.order = '';
      state.order[country].forEach((outlet, i) => {
        const c = cardEls[country][outlet];
        c.style.gridColumn = String(col); c.style.gridRow = String(i + 2); c.style.order = '';
      });
    });
  } else if (sel.length === 1){
    const country = sel[0];
    const h = headerEls[country];
    h.style.gridColumn = '1 / -1'; h.style.gridRow = ''; h.style.order = '0';
    state.order[country].forEach((outlet, i) => {
      const c = cardEls[country][outlet];
      c.style.gridColumn = ''; c.style.gridRow = ''; c.style.order = String(i + 1);
    });
  }
}

/* ---------- country chips ---------- */
const chipsWrap = document.getElementById('chips');
function renderChips(){
  chipsWrap.innerHTML = '';
  countries.forEach(country => {
    const b = el('button', 'chip', country);
    b.setAttribute('aria-pressed', state.selected.includes(country) ? 'true' : 'false');
    b.addEventListener('click', () => {
      const isOn = state.selected.includes(country);
      let next = isOn ? state.selected.filter(c => c !== country) : [...state.selected, country];
      if (next.length === 0) return;               // keep at least one
      if (next.length > 2) next = next.slice(-2);  // cap at two for comparison
      state.selected = countries.filter(c => next.includes(c)); // canonical order
      renderChips();
      relayout();
    });
    chipsWrap.appendChild(b);
  });
}

/* ---------- edition summary ---------- */
function editionCount(){
  const node = document.getElementById('edition-count');
  if (!node) return;
  if (!countries.length){ node.textContent = 'no data'; return; }
  let stories = 0, outlets = 0;
  countries.forEach(c => Object.keys(DATA[c]).forEach(o => { outlets++; stories += (DATA[c][o] || []).length; }));
  node.textContent = stories + ' stories \u00b7 ' + outlets + ' outlets \u00b7 ' + countries.length + ' countries';
}

/* ---------- init ---------- */
render();
renderChips();
editionCount();
