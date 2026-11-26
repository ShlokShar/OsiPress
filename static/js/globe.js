/* The homepage globe.

   An orthographic projection that turns slowly and marks the countries whose
   outlets covered the selected story, with an arc between them. Events carry
   no location of their own, so a marker sits on a covering country's capital
   and means "this country covered it", not "this is where it happened".

   Falls back to a still globe when the libraries or the atlas are missing,
   and when the reader asks for reduced motion. */
(function () {
  const svg = document.querySelector('[data-globe]');
  const payload = document.getElementById('osi-globe-data');
  if (!svg || !payload || !window.d3 || !window.topojson) return;

  const data = JSON.parse(payload.textContent);
  const events = data.events || [];
  const ATLAS = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';
  const SIZE = 620;
  const CENTRE = SIZE / 2;
  const SPIN = 3.2;
  // On desktop the card overlaps the globe's lower right, so the marked
  // countries are framed up and to the left of centre, and the spin swings
  // around that point instead of carrying them behind the card. SPIN is the
  // peak rate in degrees per second; it eases off towards each end of the
  // swing so the turn reads as drift rather than a metronome.
  const FOCUS_LON = 34;
  const FOCUS_LAT = 20;
  const SWING = 10;
  const overlapped = window.matchMedia('(min-width: 769px)');
  const FRAME = 1000 / 30;
  const NS = 'http://www.w3.org/2000/svg';
  const MINT = '#7FD1C8';
  const NEXT = '#2E7782';
  const LAND = '#14464E';

  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const projection = d3.geoOrthographic()
    .scale(SIZE / 2 - 6)
    .translate([CENTRE, CENTRE])
    .clipAngle(90);
  const path = d3.geoPath(projection);

  const view = { lon: 38, lat: 24 };
  let land = [];
  let hovering = false;
  let dragging = null;
  let selected = 0;
  let target = null;
  let focus = null;
  let direction = 1;
  let last = 0;

  function node(name, attrs) {
    const element = document.createElementNS(NS, name);
    Object.keys(attrs).forEach(function (key) {
      element.setAttribute(key, attrs[key]);
    });
    return element;
  }

  function current() {
    return events[selected] || null;
  }

  function coveringIds() {
    const event = current();
    if (!event) return [];
    return event.countries.map(function (country) { return country.atlas_id; });
  }

  function visible(point) {
    const rotation = projection.rotate();
    return d3.geoDistance(point, [-rotation[0], -rotation[1]]) < Math.PI / 2;
  }

  function colourFor(id) {
    if (coveringIds().indexOf(id) !== -1) return MINT;
    if (data.live.indexOf(id) !== -1) return '#3E8F8A';
    if (data.next.indexOf(id) !== -1) return NEXT;
    return LAND;
  }

  function draw() {
    projection.rotate([-view.lon, -view.lat]);
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    svg.appendChild(node('circle', {
      cx: CENTRE, cy: CENTRE, r: SIZE / 2 - 6, fill: '#0D3A42',
    }));
    svg.appendChild(node('path', {
      d: path(d3.geoGraticule10()) || '',
      fill: 'none', stroke: '#164A53', 'stroke-width': 0.6,
    }));

    land.forEach(function (feature) {
      // Skip the far side before projecting; it is most of the globe.
      if (feature.centroid && !visible(feature.centroid)) return;
      const d = path(feature.geometry);
      if (!d) return;
      svg.appendChild(node('path', {
        d: d,
        fill: colourFor(feature.id),
        stroke: '#0A2F36',
        'stroke-width': 0.5,
      }));
    });

    const event = current();
    if (!event) return;

    // One arc between each pair of covering capitals: the two newsrooms that
    // wrote about the same thing today.
    for (let i = 0; i < event.countries.length - 1; i += 1) {
      const from = event.countries[i].capital;
      const to = event.countries[i + 1].capital;
      if (!visible(from) && !visible(to)) continue;
      const d = path({ type: 'LineString', coordinates: [from, to] });
      if (!d) continue;
      svg.appendChild(node('path', {
        d: d,
        fill: 'none',
        stroke: MINT,
        'stroke-width': 1,
        'stroke-dasharray': '3 5',
        opacity: 0.6,
      }));
    }

    event.countries.forEach(function (country, order) {
      if (!visible(country.capital)) return;
      const point = projection(country.capital);
      if (!point) return;
      const lead = order === 0;
      const group = node('g', {
        transform: 'translate(' + point[0] + ',' + point[1] + ')',
      });
      group.appendChild(node('circle', {
        r: lead ? 17 : 14,
        fill: 'none',
        stroke: lead ? '#FFFFFF' : MINT,
        'stroke-width': 1.5,
        opacity: 0.55,
        class: 'osi-pin-ring',
      }));
      group.appendChild(node('circle', {
        r: lead ? 9 : 7,
        fill: lead ? '#FFFFFF' : MINT,
        stroke: '#0A2F36',
        'stroke-width': 1.5,
      }));
      group.appendChild(node('title', {})).textContent = country.name;
      svg.appendChild(group);
    });
  }

  function select(index) {
    if (!events[index]) return;
    selected = index;

    document.querySelectorAll('[data-event]').forEach(function (button) {
      button.setAttribute(
        'aria-pressed',
        Number(button.dataset.event) === index ? 'true' : 'false'
      );
    });
    document.querySelectorAll('[data-face]').forEach(function (face) {
      face.hidden = Number(face.dataset.face) !== index;
    });

    frame(index);

    if (reduced.matches) {
      view.lon = target.lon;
      view.lat = target.lat;
      target = null;
      draw();
    }
  }

  // Aim the globe so this event's countries sit clear of the card.
  function frame(index) {
    const capitals = events[index].countries.map(function (c) { return c.capital; });
    const lon = capitals.reduce(function (sum, c) { return sum + c[0]; }, 0) / capitals.length;
    const lat = capitals.reduce(function (sum, c) { return sum + c[1]; }, 0) / capitals.length;
    const offsetLon = overlapped.matches ? FOCUS_LON : 0;
    const offsetLat = overlapped.matches ? FOCUS_LAT : 0;
    focus = {
      lon: lon + offsetLon,
      lat: Math.max(-40, Math.min(40, lat - offsetLat)),
    };
    direction = 1;
    target = { lon: focus.lon, lat: focus.lat };
  }

  function tick(now) {
    if (now - last >= FRAME) {
      const elapsed = Math.min(now - last, 100);
      last = now;
      if (target) {
        const delta = ((target.lon - view.lon + 540) % 360) - 180;
        view.lon += delta * 0.12;
        view.lat += (target.lat - view.lat) * 0.12;
        if (Math.abs(delta) < 0.4) target = null;
      } else if (!hovering && !dragging) {
        if (focus) {
          const offset = (view.lon - focus.lon) / SWING;
          const eased = Math.sqrt(Math.max(0, 1 - offset * offset));
          view.lon += SPIN * (0.25 + 0.75 * eased) * direction * (elapsed / 1000);
          if (view.lon > focus.lon + SWING) direction = -1;
          if (view.lon < focus.lon - SWING) direction = 1;
        } else {
          view.lon += SPIN * (elapsed / 1000);
        }
      }
      draw();
    }
    window.requestAnimationFrame(tick);
  }

  svg.addEventListener('pointerenter', function () { hovering = true; });
  svg.addEventListener('pointerleave', function () {
    hovering = false;
    dragging = null;
  });
  svg.addEventListener('pointerdown', function (pointer) {
    dragging = { x: pointer.clientX, y: pointer.clientY, lon: view.lon, lat: view.lat };
    target = null;
  });
  svg.addEventListener('pointermove', function (pointer) {
    if (!dragging) return;
    view.lon = dragging.lon - (pointer.clientX - dragging.x) * 0.3;
    view.lat = Math.max(-60, Math.min(60, dragging.lat + (pointer.clientY - dragging.y) * 0.3));
    if (reduced.matches) draw();
  });
  svg.addEventListener('pointerup', function () { dragging = null; });

  document.querySelectorAll('[data-event]').forEach(function (button) {
    button.addEventListener('click', function () {
      select(Number(button.dataset.event));
    });
  });

  fetch(ATLAS)
    .then(function (response) { return response.json(); })
    .then(function (atlas) {
      const collection = topojson.feature(atlas, atlas.objects.countries);
      land = collection.features.map(function (feature) {
        return {
          id: String(feature.id),
          geometry: feature,
          centroid: d3.geoCentroid(feature),
        };
      });
      if (events.length) {
        frame(selected);
        view.lon = focus.lon;
        view.lat = focus.lat;
        target = null;
      }
      draw();
      if (!reduced.matches) window.requestAnimationFrame(tick);
    })
    .catch(function () {
      draw();
    });
})();
