/* V2 — puts the character's art behind the grader.
 *
 * app.js fires `relicgrader:character` with {id, name} whenever a character is
 * picked or a relic is scored (including re-scoring for another character), so
 * this stays a pure observer and app.js needs no knowledge of the art.
 *
 * Two layers are kept stacked and cross-faded, so changing character dissolves
 * rather than flashing. The server decides what art exists — it 404s with a hint
 * when the art has never been fetched, and the UI degrades to the scarlet glow.
 */
(() => {
  'use strict';

  const A = document.getElementById('artA');
  const B = document.getElementById('artB');
  const blur = document.getElementById('artBlur');
  const credit = document.getElementById('artCredit');
  if (!A || !B) return;

  let front = 0;                 // index of the layer currently visible
  let shown = '';                // url on screen
  let missing = false;           // art folder empty -> say so once
  const resolved = new Map();    // query -> url | null

  function paint(url) {
    if (!url || url === shown) return;
    const back = 1 - front;
    const probe = new Image();
    probe.onload = () => {
      const target = [A, B][back];
      target.style.backgroundImage = `url("${url}")`;
      target.classList.add('on');
      [A, B][front].classList.remove('on');
      if (blur) {
        blur.style.backgroundImage = `url("${url}")`;
        blur.classList.add('on');
      }
      front = back;
      shown = url;
    };
    probe.src = url;
  }

  function noteMissing() {
    if (missing || !credit) return;
    missing = true;
    credit.innerHTML = 'No character art yet — run <code>python tools/fetch_character_art.py</code> '
      + '&middot; <a href="/" style="color:inherit">plain layout</a>';
  }

  async function show(detail) {
    if (!detail) return;
    const query = detail.id
      ? `id=${encodeURIComponent(detail.id)}`
      : (detail.name ? `character=${encodeURIComponent(detail.name)}` : '');
    if (!query) return;
    if (resolved.has(query)) {
      const cached = resolved.get(query);
      if (cached) paint(cached); else noteMissing();
      return;
    }
    try {
      const res = await fetch(`/api/art?${query}`);
      if (res.ok) {
        const data = await res.json();
        resolved.set(query, data.url);
        paint(data.url);
      } else {
        resolved.set(query, null);
        noteMissing();
      }
    } catch (_) {
      /* offline or server gone: keep whatever is showing */
    }
  }

  window.addEventListener('relicgrader:character', (e) => show(e.detail));

  /* Show something on load: the first character in the list, dimmed, so the
     page never looks empty before a choice is made. */
  window.addEventListener('relicgrader:ready', (e) => show(e.detail));
})();
