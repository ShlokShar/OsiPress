/* Segmented controls, country pickers and the originals switch.
   Each control writes its state into the URL and lets the server re-render,
   so a comparison can be shared or reloaded. */
(function () {
  const MAX_COUNTRIES = 3;

  function go(params) {
    window.location.search = params.toString();
  }

  /* Collapse or expand every country and outlet block on the page, and put
     the button into the opposite state. */
  function setCollapsed(collapsed) {
    document.querySelectorAll('details.osi-collapse').forEach(function (block) {
      block.open = !collapsed;
    });
    const button = document.querySelector('[data-action="collapse"]');
    if (button) {
      button.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
      button.textContent = collapsed ? 'Expand all' : 'Collapse all';
    }
  }

  function currentCountries(params) {
    const raw = params.get('countries');
    return raw ? raw.split(',').filter(Boolean) : Array.from(
      document.querySelectorAll('[data-action="country"][aria-pressed="true"]'),
      button => button.dataset.country
    );
  }

  document.addEventListener('click', function (event) {
    const target = event.target.closest('[data-action]');
    if (!target || target.disabled) return;

    const action = target.dataset.action;
    const params = new URLSearchParams(window.location.search);

    if (action === 'originals') {
      const hidden = document.body.classList.toggle('osi-no-originals');
      target.setAttribute('aria-pressed', hidden ? 'true' : 'false');
      target.textContent = hidden ? 'Show originals' : 'Hide originals';
      try {
        window.localStorage.setItem('osi-no-originals', hidden ? '1' : '0');
      } catch (error) {
        /* Private browsing: the switch still works for this page view. */
      }
      return;
    }

    if (action === 'collapse') {
      const collapsed = target.getAttribute('aria-pressed') !== 'true';
      setCollapsed(collapsed);
      try {
        window.localStorage.setItem('osi-collapsed', collapsed ? '1' : '0');
      } catch (error) {
        /* Private browsing: the button still works for this page view. */
      }
      return;
    }

    if (action === 'view' || action === 'stories' || action === 'range' || action === 'sort' || action === 'mode') {
      params.set(action === 'view' ? 'view' : action, target.dataset.value);
      go(params);
      return;
    }

    if (action === 'country') {
      const key = target.dataset.country;
      const picked = currentCountries(params);
      const index = picked.indexOf(key);
      if (index === -1) {
        if (picked.length >= MAX_COUNTRIES) return;
        picked.push(key);
      } else if (picked.length > 1) {
        picked.splice(index, 1);
      } else {
        return;
      }
      params.set('countries', picked.join(','));
      go(params);
      return;
    }

    if (action === 'topic' || action === 'day') {
      const value = target.dataset.value;
      if (params.get(action) === value) {
        params.delete(action);
      } else {
        params.set(action, value);
      }
      go(params);
    }
  });

  try {
    if (window.localStorage.getItem('osi-no-originals') === '1') {
      document.body.classList.add('osi-no-originals');
      const toggle = document.querySelector('[data-action="originals"]');
      if (toggle) {
        toggle.setAttribute('aria-pressed', 'true');
        toggle.textContent = 'Show originals';
      }
    }
  } catch (error) {
    /* No stored preference is available; originals stay visible. */
  }

  try {
    if (window.localStorage.getItem('osi-collapsed') === '1'
        && document.querySelector('[data-action="collapse"]')) {
      setCollapsed(true);
    }
  } catch (error) {
    /* No stored preference is available; blocks stay expanded. */
  }
})();
