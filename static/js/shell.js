(function () {
  const button = document.querySelector('[data-menu-button]');
  const nav = document.getElementById('osi-mobile-nav');
  if (!button || !nav) return;

  button.addEventListener('click', function () {
    const open = nav.dataset.open === 'true';
    nav.dataset.open = open ? 'false' : 'true';
    button.setAttribute('aria-expanded', open ? 'false' : 'true');
    button.setAttribute('aria-label', open ? 'Open menu' : 'Close menu');
  });
})();
