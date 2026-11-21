const EVENT_VISIT_KEY = 'osipress-events-last-visit';
const previousVisit = localStorage.getItem(EVENT_VISIT_KEY);

document.querySelectorAll('[data-last-seen]').forEach(card => {
  const isNew = previousVisit && card.dataset.lastSeen > previousVisit;
  const badge = card.querySelector('.event-new');
  if (isNew && badge) badge.hidden = false;
});

localStorage.setItem(EVENT_VISIT_KEY, new Date().toISOString());
