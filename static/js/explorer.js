/* The homepage spectrum explorer: country tabs switch panels in place and
   picking an outlet shows its card. The tabs stay real links, so the page
   still works without JavaScript; here we swap panels instead of loading. */
(function () {
  const explorer = document.getElementById('spectrum');
  if (!explorer) return;

  const tabs = explorer.querySelectorAll('[data-tab]');
  const panels = explorer.querySelectorAll('[data-panel]');

  function selectCountry(key) {
    tabs.forEach(function (tab) {
      tab.setAttribute('aria-selected', tab.dataset.tab === key ? 'true' : 'false');
    });
    panels.forEach(function (panel) {
      panel.hidden = panel.dataset.panel !== key;
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener('click', function (event) {
      if (event.metaKey || event.ctrlKey || event.shiftKey) return;
      event.preventDefault();
      selectCountry(tab.dataset.tab);
      try {
        const url = new URL(window.location.href);
        url.searchParams.set('spectrum', tab.dataset.tab);
        url.hash = '';
        window.history.replaceState({}, '', url);
      } catch (error) {
        /* An unparsable URL only costs the shareable state. */
      }
    });
  });

  explorer.addEventListener('click', handleOutlet);
  explorer.addEventListener('mouseover', handleOutlet);
  explorer.addEventListener('focusin', handleOutlet);

  function handleOutlet(event) {
    const button = event.target.closest('[data-outlet]');
    if (!button) return;
    const panel = button.closest('[data-panel]');
    if (!panel) return;

    const index = button.dataset.outlet;
    panel.querySelectorAll('[data-outlet]').forEach(function (other) {
      other.setAttribute('aria-pressed', other === button ? 'true' : 'false');
    });
    panel.querySelectorAll('[data-outlet-card]').forEach(function (card) {
      card.hidden = card.dataset.outletCard !== index;
    });
  }
})();
