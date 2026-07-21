function initSticky(){
  const stickies = Array.from(document.querySelectorAll('[data-sticky]'));
  if (!stickies.length) return;
  const apply = () => {
    const wide = window.innerWidth >= 780;
    stickies.forEach((el) => {
      el.style.position = wide ? 'sticky' : '';
      el.style.top = wide ? '84px' : '';
    });
  };
  apply();
  window.addEventListener('resize', apply);
}

function initReveal(){
  const els = Array.from(document.querySelectorAll('[data-reveal]'));
  if (!els.length) return;

  const reveal = (el, delay) => {
    el.style.transitionDelay = (delay || 0) + 'ms';
    el.style.opacity = '1';
    el.style.transform = 'none';
  };

  const reduce = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce || !('IntersectionObserver' in window)) { els.forEach((el) => reveal(el)); return; }

  els.forEach((el) => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(24px)';
    el.style.transition = 'opacity .7s cubic-bezier(.16,.84,.44,1), transform .7s cubic-bezier(.16,.84,.44,1)';
    el.style.willChange = 'opacity, transform';
  });

  const inView = (el) => {
    const r = el.getBoundingClientRect();
    const vh = window.innerHeight || document.documentElement.clientHeight;
    return r.top < vh * 0.92 && r.bottom > 0;
  };

  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) { reveal(e.target); io.unobserve(e.target); }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });

  let started = false;
  const start = () => {
    if (started) return;
    started = true;
    requestAnimationFrame(() => {
      let i = 0;
      els.forEach((el) => {
        if (inView(el)) { reveal(el, (i++) * 90); io.unobserve(el); }
        else io.observe(el);
      });
    });
  };

  if (document.fonts && document.fonts.ready) document.fonts.ready.then(start);
  setTimeout(start, 900);
}

initSticky();
requestAnimationFrame(initReveal);
