(function () {
  const MIN_DATE = '2026-07-09';

  function yesterdayStr() {
    const d = new Date();
    d.setDate(d.getDate() - 1);
    return d.toISOString().slice(0, 10);
  }

  function inRange(dateStr) {
    return !!dateStr && dateStr >= MIN_DATE && dateStr <= yesterdayStr();
  }

  function formatLabel(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  }

  function currentDate() {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('date');
    return inRange(fromUrl) ? fromUrl : yesterdayStr();
  }

  function syncUrl(dateStr) {
    const params = new URLSearchParams(window.location.search);
    params.set('date', dateStr);
    window.history.replaceState(null, '', window.location.pathname + '?' + params.toString());
  }

  function navigateTo(dateStr) {
    const params = new URLSearchParams(window.location.search);
    params.set('date', dateStr);
    window.location.search = params.toString();
  }

  const input = document.getElementById('date-input');
  const label = document.getElementById('date-label');
  if (!input || !label) return;

  const date = currentDate();
  input.max = yesterdayStr();
  input.min = MIN_DATE;
  input.value = date;
  label.textContent = formatLabel(date);
  syncUrl(date);

  input.addEventListener('click', () => {
    if (typeof input.showPicker === 'function') {
      try { input.showPicker(); } catch (e) {}
    }
  });

  input.addEventListener('change', () => {
    const next = input.value;
    if (!inRange(next)) { input.value = date; return; }
    navigateTo(next);
  });
})();
