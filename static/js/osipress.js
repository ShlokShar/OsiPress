function normalizeLean(label){
  const s = (label || '').toLowerCase();
  if (s.includes('left')) return 'left';
  if (s.includes('right')) return 'right';
  if (s.includes('center') || s.includes('centre')) return 'center';
  return 'unknown';
}

const SCRIPT_LABEL = {
  'Iran':   { name: 'Persian', native: 'فارسی' },
  'Israel': { name: 'Hebrew',  native: 'עברית' },
};

const TAG_ORDER = ['Conflict', 'Diplomacy', 'Sanctions', 'Domestic', 'Economy', 'International'];
const articleTags = story => (Array.isArray(story.tags) ? story.tags : []);

function loadData(){
  const node = document.getElementById('osipress-data');
  try {
    const parsed = JSON.parse(node.textContent);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) return parsed;
  } catch (e) {}
  return {};
}
const DATA = loadData();

const NARROW_QUERY = '(max-width:700px)';
const isNarrowViewport = () => window.matchMedia(NARROW_QUERY).matches;
const isTouch = window.matchMedia('(pointer: coarse)').matches;

const countries = Object.keys(DATA);
const state = {
  selected: countries.slice(0, isNarrowViewport() ? 1 : 2),
  order: {},
  expanded: {},
  translated: {},
  selectedTags: new Set(),
};
countries.forEach(c => { state.order[c] = Object.keys(DATA[c]); });

const presentTags = (() => {
  const seen = new Set();
  countries.forEach(c => Object.keys(DATA[c]).forEach(o =>
    ((DATA[c][o] || {}).articles || []).forEach(s =>
      articleTags(s).forEach(t => seen.add(t)))));
  return TAG_ORDER.filter(t => seen.has(t));
})();

function passesTagFilter(story){
  if (!state.selectedTags.size) return true;
  const tags = articleTags(story);
  for (const t of state.selectedTags){ if (!tags.includes(t)) return false; }
  return true;
}

const keyOf = (country, outlet, i) => country + '|' + outlet + '|' + i;
const APOLOGY = /^(i can'?t|no content|the provided article content is empty)/i;
const cleanSummary = s => (s && s.trim() && !APOLOGY.test(s.trim())) ? s.trim() : '';

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
function safeHttpUrl(url){
  try {
    const parsed = new URL(url);
    return (parsed.protocol === 'http:' || parsed.protocol === 'https:')
      ? parsed.href
      : null;
  } catch (e) { return null; }
}

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

  const storyTags = TAG_ORDER.filter(t => articleTags(story).includes(t));
  if (storyTags.length){
    const topics = el('div', 'topics');
    storyTags.forEach(t => {
      const pill = el('button', 'topic', t);
      pill.dataset.tag = t;
      pill.classList.toggle('active', state.selectedTags.has(t));
      pill.setAttribute('aria-label', 'Filter by ' + t);
      pill.addEventListener('click', e => { e.stopPropagation(); toggleTag(t); });
      topics.appendChild(pill);
    });
    main.appendChild(topics);
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

  const safeLink = safeHttpUrl(story.link);
  if (safeLink){
    const a = el('a', 'readlink', 'Read at ' + hostOf(safeLink) + ' \u2197');
    a.href = safeLink; a.target = '_blank'; a.rel = 'noopener';
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
  return { wrap, tags: articleTags(story) };
}

function buildCard(country, outlet){
  const card = el('article', 'card');
  card.dataset.outlet = outlet;

  const head = el('div', 'card-head');
  let handle = null;
  if (!isTouch){
    card.setAttribute('draggable', 'true');
    handle = el('span', 'handle', '\u2847');
    handle.title = 'Drag to reorder';
    handle.setAttribute('aria-label', 'Drag to reorder');
    head.appendChild(handle);
  }
  head.appendChild(el('span', 'outlet-name', outlet));
  const leaning = (DATA[country][outlet] || {}).political_leaning;
  if (leaning) head.appendChild(el('span', 'tag ' + normalizeLean(leaning), leaning));
  card.appendChild(head);

  const stories = el('div', 'stories');
  card._stories = [];
  ((DATA[country][outlet] || {}).articles || []).forEach((s, i) => {
    const { wrap, tags } = buildStory(country, outlet, s, i);
    stories.appendChild(wrap);
    card._stories.push({ el: wrap, tags });
  });
  card.appendChild(stories);

  if (handle) wireDrag(card, handle, country);
  return card;
}

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
    const singleColGrid = board.dataset.mode === 'single';
    const rect = card.getBoundingClientRect();
    const before = singleColGrid
      ? (e.clientX < rect.left + rect.width / 2)
      : (e.clientY < rect.top + rect.height / 2);
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

const board = document.getElementById('board');
const emptyNote = document.getElementById('empty');
const headerEls = {};
const cardEls = {};

function render(){
  board.innerHTML = '';
  if (!countries.length){
    if (emptyNote) emptyNote.hidden = false;
    return;
  }
  countries.forEach(country => {
    const h = el('div', 'col-header');
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

function applyStoryFilter(card){
  let anyVisible = false;
  (card._stories || []).forEach(({ el, tags }) => {
    const show = passesTagFilter({ tags });
    el.style.display = show ? 'flex' : 'none';
    if (show) anyVisible = true;
  });
  return anyVisible;
}

function relayout(){
  const sel = state.selected.filter(c => countries.includes(c));
  const narrow = isNarrowViewport();
  const compare = sel.length === 2 && !narrow;
  const stacked = sel.length === 2 && narrow;
  board.dataset.mode = compare ? 'compare' : (stacked ? 'stacked' : 'single');

  const filtering = state.selectedTags.size > 0;
  const visibleOutlets = {};
  let totalVisibleCards = 0;
  countries.forEach(country => {
    const shown = sel.includes(country);
    visibleOutlets[country] = [];
    state.order[country].forEach(outlet => {
      const c = cardEls[country][outlet];
      if (!c) return;
      if (!shown){ c.style.display = 'none'; return; }
      const anyVisible = applyStoryFilter(c);
      const cardShown = filtering ? anyVisible : true;
      c.style.display = cardShown ? 'flex' : 'none';
      if (cardShown){ visibleOutlets[country].push(outlet); totalVisibleCards++; }
    });
    const headerShown = shown && (!filtering || visibleOutlets[country].length > 0);
    if (headerEls[country]) headerEls[country].style.display = headerShown ? 'flex' : 'none';
  });

  if (compare){
    sel.forEach((country, colIdx) => {
      const col = colIdx + 1;
      const h = headerEls[country];
      h.style.gridColumn = String(col); h.style.gridRow = '1'; h.style.order = '';
      visibleOutlets[country].forEach((outlet, i) => {
        const c = cardEls[country][outlet];
        c.style.gridColumn = String(col); c.style.gridRow = String(i + 2); c.style.order = '';
      });
    });
  } else if (stacked){
    let ord = 0;
    sel.forEach(country => {
      const h = headerEls[country];
      h.style.gridColumn = '1 / -1'; h.style.gridRow = ''; h.style.order = String(ord++);
      visibleOutlets[country].forEach(outlet => {
        const c = cardEls[country][outlet];
        c.style.gridColumn = ''; c.style.gridRow = ''; c.style.order = String(ord++);
      });
    });
  } else if (sel.length === 1){
    const country = sel[0];
    const h = headerEls[country];
    h.style.gridColumn = '1 / -1'; h.style.gridRow = ''; h.style.order = '0';
    visibleOutlets[country].forEach((outlet, i) => {
      const c = cardEls[country][outlet];
      c.style.gridColumn = ''; c.style.gridRow = ''; c.style.order = String(i + 1);
    });
  }

  if (emptyNote){
    if (filtering && totalVisibleCards === 0){
      emptyNote.textContent = 'No articles match the selected topics.';
      emptyNote.hidden = false;
    } else {
      emptyNote.hidden = true;
    }
  }
}

let resizeRAF = null;
window.addEventListener('resize', () => {
  if (resizeRAF) cancelAnimationFrame(resizeRAF);
  resizeRAF = requestAnimationFrame(relayout);
});

const chipsWrap = document.getElementById('chips');
function renderChips(){
  chipsWrap.innerHTML = '';
  countries.forEach(country => {
    const b = el('button', 'chip', country);
    b.setAttribute('aria-pressed', state.selected.includes(country) ? 'true' : 'false');
    b.addEventListener('click', () => {
      const isOn = state.selected.includes(country);
      let next = isOn ? state.selected.filter(c => c !== country) : [...state.selected, country];
      if (next.length === 0) return;
      if (next.length > 2) next = next.slice(-2);
      state.selected = countries.filter(c => next.includes(c));
      renderChips();
      relayout();
    });
    chipsWrap.appendChild(b);
  });
}

const topicsPicker = document.getElementById('topics-picker');
const topicsToggle = document.getElementById('topics-toggle');
const topicsPanel  = document.getElementById('topics-panel');
const topicsCount  = document.getElementById('topics-count');

function renderTopicOptions(){
  if (!topicsPanel) return;
  if (!presentTags.length){
    if (topicsPicker) topicsPicker.style.display = 'none';
    return;
  }
  topicsPanel.innerHTML = '';
  presentTags.forEach(tag => {
    const opt = el('button', 'dd-opt');
    opt.type = 'button';
    opt.dataset.tag = tag;
    opt.setAttribute('role', 'menuitemcheckbox');
    opt.setAttribute('aria-checked', state.selectedTags.has(tag) ? 'true' : 'false');
    opt.appendChild(el('span', 'dd-box'));
    opt.appendChild(el('span', 'dd-opt-lbl', tag));
    opt.addEventListener('click', () => toggleTag(tag));
    topicsPanel.appendChild(opt);
  });
}

function syncTopicControl(){
  if (topicsPanel){
    Array.from(topicsPanel.children).forEach(opt => {
      opt.setAttribute('aria-checked', state.selectedTags.has(opt.dataset.tag) ? 'true' : 'false');
    });
  }
  const n = state.selectedTags.size;
  if (topicsCount) topicsCount.textContent = n === 0 ? 'All' : n + ' selected';
  if (topicsToggle) topicsToggle.classList.toggle('has-selection', n > 0);
}

function openTopics(open){
  if (!topicsPanel || !topicsToggle) return;
  topicsPanel.hidden = !open;
  topicsToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
}

if (topicsToggle){
  topicsToggle.addEventListener('click', e => {
    e.stopPropagation();
    openTopics(topicsPanel.hidden);
  });
}
document.addEventListener('click', e => {
  if (topicsPicker && topicsPanel && !topicsPanel.hidden && !topicsPicker.contains(e.target)){
    openTopics(false);
  }
});

function toggleTag(tag){
  if (state.selectedTags.has(tag)) state.selectedTags.delete(tag);
  else state.selectedTags.add(tag);
  syncTopicControl();
  syncTagPills();
  relayout();
}

function syncTagPills(){
  document.querySelectorAll('.topic').forEach(pill => {
    pill.classList.toggle('active', state.selectedTags.has(pill.dataset.tag));
  });
}

function editionCount(){
  const node = document.getElementById('edition-count');
  if (!node) return;
  if (!countries.length){ node.textContent = 'no data'; return; }
  let stories = 0, outlets = 0;
  countries.forEach(c => Object.keys(DATA[c]).forEach(o => { outlets++; stories += ((DATA[c][o] || {}).articles || []).length; }));
  node.textContent = stories + ' stories \u00b7 ' + outlets + ' outlets \u00b7 ' + countries.length + ' countries';
}

render();
renderChips();
renderTopicOptions();
syncTopicControl();
editionCount();
