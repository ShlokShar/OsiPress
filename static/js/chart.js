/* The archive chart's hover tooltip. Selecting a day is a link-style URL
   change handled in controls.js, so a selected day survives a reload. */
(function () {
  const chart = document.querySelector('[data-chart]');
  const tip = document.querySelector('[data-chart-tip]');
  if (!chart || !tip) return;

  const NAMES = { ir: 'Iran', il: 'Israel', ru: 'Russia', ua: 'Ukraine' };
  const date = tip.querySelector('[data-tip-date]');
  const counts = tip.querySelector('[data-tip-counts]');
  const top = tip.querySelector('[data-tip-top]');
  const plot = chart.querySelector('.osi-chart-plot');

  function show(day) {
    date.textContent = day.dataset.long;
    counts.textContent = (day.dataset.counts || '')
      .split(',')
      .filter(Boolean)
      .map(function (pair) {
        const parts = pair.split(':');
        return (NAMES[parts[0]] || parts[0]) + ' ' + parts[1];
      })
      .join(' · ');

    const more = Number(day.dataset.more || 0);
    top.textContent = day.dataset.top
      ? day.dataset.top + (more ? ' and ' + more + ' more' : '')
      : 'No events for this filter';

    const bounds = plot.getBoundingClientRect();
    const box = day.getBoundingClientRect();
    const centre = box.left - bounds.left + box.width / 2;
    const percent = (centre / bounds.width) * 100;
    tip.style.left = percent + '%';
    tip.style.transform =
      'translateX(' + (percent > 75 ? '-100%' : percent < 25 ? '0%' : '-50%') + ')';
    tip.hidden = false;
  }

  chart.querySelectorAll('.osi-chart-day').forEach(function (day) {
    day.addEventListener('mouseenter', function () { show(day); });
    day.addEventListener('focus', function () { show(day); });
  });
  plot.addEventListener('mouseleave', function () { tip.hidden = true; });
})();
