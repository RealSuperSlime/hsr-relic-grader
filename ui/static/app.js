/* HSR Relic Grader — front end. Talks to the local Python server only. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const combo = $('combo'), comboInput = $('comboInput'), comboList = $('comboList');
  const drop = $('drop'), file = $('file'), thumb = $('thumb');
  const gradeBtn = $('grade'), status = $('status'), charHint = $('charHint');

  let CHARACTERS = [];
  let selected = null;       // {id, name}
  let imageData = null;      // data URL of the pasted screenshot
  let lastRelic = null;      // parsed relic, for re-scoring without OCR
  let activeIndex = -1;

  const GRADE_COLORS = {
    'S+': ['#fff4d1', '#d8a12b', 'rgba(216,161,43,.22)'],
    'S':  ['#ffe7ea', '#ff4757', 'rgba(255,71,87,.20)'],
    'A':  ['#ffe4d4', '#ff7a45', 'rgba(255,122,69,.18)'],
    'B':  ['#e8dcff', '#9a7bff', 'rgba(154,123,255,.18)'],
    'C':  ['#d9ecff', '#4aa8ff', 'rgba(74,168,255,.16)'],
    'D':  ['#d8e2e8', '#7d93a3', 'rgba(125,147,163,.14)'],
    'F':  ['#cfd4d7', '#6b7479', 'rgba(107,116,121,.12)'],
  };

  /* ------------------------------------------------------------------ */
  /* character combobox                                                   */
  /* ------------------------------------------------------------------ */
  function normalize(s) {
    return (s || '').toLowerCase().replace(/[^a-z0-9 ]/g, '');
  }

  function filtered(query) {
    const q = normalize(query).trim();
    if (!q) return CHARACTERS.slice(0, 80);
    const starts = [], contains = [];
    for (const c of CHARACTERS) {
      const n = normalize(c.name);
      if (n.startsWith(q)) starts.push(c);
      else if (n.includes(q)) contains.push(c);
    }
    return starts.concat(contains).slice(0, 80);
  }

  function renderList(query) {
    const items = filtered(query);
    comboList.innerHTML = '';
    activeIndex = -1;
    if (!items.length) {
      const d = document.createElement('div');
      d.className = 'none';
      d.textContent = 'No character matches.';
      comboList.appendChild(d);
      return;
    }
    for (const c of items) {
      const row = document.createElement('div');
      row.setAttribute('role', 'option');
      row.dataset.id = c.id;
      row.dataset.name = c.name;
      if (selected && selected.name === c.name) row.classList.add('selected');
      const label = document.createElement('b');
      label.textContent = c.name;
      const meta = document.createElement('span');
      meta.textContent = [c.element, c.path].filter(Boolean).join(' · ');
      row.append(label, meta);
      row.addEventListener('mousedown', (ev) => { ev.preventDefault(); choose(c); });
      comboList.appendChild(row);
    }
  }

  function openList() {
    renderList(comboInput.value);
    comboList.classList.add('open');
    comboInput.setAttribute('aria-expanded', 'true');
  }

  function closeList() {
    comboList.classList.remove('open');
    comboInput.setAttribute('aria-expanded', 'false');
    activeIndex = -1;
  }

  function announceCharacter(id, name) {
    // V2 swaps the background art on this; the plain UI ignores it.
    window.dispatchEvent(new CustomEvent('relicgrader:character', { detail: { id, name } }));
  }

  function choose(c) {
    selected = { id: c.id, name: c.name };
    comboInput.value = c.name;
    closeList();
    charHint.textContent = `Scoring as ${c.name}${c.element ? ' · ' + c.element : ''}`;
    charHint.classList.remove('error');
    refreshButton();
    announceCharacter(c.id, c.name);
    if (lastRelic) runRescore();
  }

  function moveActive(delta) {
    const rows = [...comboList.querySelectorAll('[role="option"]')];
    if (!rows.length) return;
    activeIndex = (activeIndex + delta + rows.length) % rows.length;
    rows.forEach((r, i) => r.classList.toggle('active', i === activeIndex));
    rows[activeIndex].scrollIntoView({ block: 'nearest' });
  }

  comboInput.addEventListener('focus', openList);
  comboInput.addEventListener('input', () => { selected = null; openList(); refreshButton(); });
  comboInput.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); if (!comboList.classList.contains('open')) openList(); moveActive(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); moveActive(-1); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      const rows = [...comboList.querySelectorAll('[role="option"]')];
      const row = activeIndex >= 0 ? rows[activeIndex]
        : (rows.length === 1 ? rows[0] : null);
      if (row) choose({ id: row.dataset.id, name: row.dataset.name });
      else if (comboInput.value.trim()) choose({ id: '', name: comboInput.value.trim() });
    } else if (e.key === 'Escape') { closeList(); }
  });
  document.addEventListener('click', (e) => { if (!combo.contains(e.target)) closeList(); });
  $('comboToggle').addEventListener('click', () => {
    if (comboList.classList.contains('open')) closeList(); else { comboInput.focus(); openList(); }
  });

  /* ------------------------------------------------------------------ */
  /* image input: paste / drop / browse                                   */
  /* ------------------------------------------------------------------ */
  function setImage(dataUrl) {
    imageData = dataUrl;
    thumb.src = dataUrl;
    drop.classList.add('filled');
    refreshButton();
  }

  function clearImage() {
    imageData = null;
    thumb.removeAttribute('src');
    drop.classList.remove('filled');
    refreshButton();
  }

  function readFile(f) {
    if (!f || !f.type.startsWith('image/')) { setStatus('That file is not an image.', true); return; }
    const r = new FileReader();
    r.onload = () => setImage(r.result);
    r.readAsDataURL(f);
  }

  drop.addEventListener('click', () => file.click());
  drop.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); file.click(); }
  });
  file.addEventListener('change', () => readFile(file.files[0]));
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => {
    e.preventDefault(); drop.classList.add('over');
  }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => {
    e.preventDefault(); drop.classList.remove('over');
  }));
  drop.addEventListener('drop', (e) => {
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
    readFile(f);
  });
  window.addEventListener('paste', (e) => {
    const items = (e.clipboardData || {}).items || [];
    for (const it of items) {
      if (it.type && it.type.startsWith('image/')) {
        const f = it.getAsFile();
        if (f) { readFile(f); e.preventDefault(); return; }
      }
    }
    // some browsers only expose a pasted URL
    const text = (e.clipboardData || {}).getData && e.clipboardData.getData('text');
    if (text && /^https?:\/\/.+\.(png|jpe?g|webp)$/i.test(text.trim())) {
      setStatus('Pasted a link — save the image and drop it here instead.', true);
    }
  });

  /* ------------------------------------------------------------------ */
  /* grading                                                             */
  /* ------------------------------------------------------------------ */
  function setStatus(msg, isError) {
    status.textContent = msg || '\u00a0';
    status.classList.toggle('error', !!isError);
  }

  function refreshButton() {
    gradeBtn.disabled = !(imageData && (selected || comboInput.value.trim()));
  }

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({ error: 'server returned no JSON' }));
    if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  async function runGrade() {
    if (!imageData) return;
    const character = selected ? selected.id : comboInput.value.trim();
    if (!character) { charHint.textContent = 'Pick a character first.'; charHint.classList.add('error'); return; }
    document.body.classList.add('busy');
    gradeBtn.textContent = 'Reading screenshot\u2026';
    setStatus('Running OCR\u2026');
    try {
      const data = await postJSON('/api/score', { character, image: imageData });
      lastRelic = data.relic;
      render(data);
      setStatus(`Scored for ${data.character.name} \u00b7 ${data.relic.substats.length} substats read`);
    } catch (err) {
      setStatus(String(err.message || err), true);
    } finally {
      document.body.classList.remove('busy');
      gradeBtn.textContent = 'Grade relic';
      refreshButton();
    }
  }

  async function runRescore() {
    if (!lastRelic || !selected) return;
    try {
      const data = await postJSON('/api/rescore', { character: selected.id, relic: lastRelic });
      render(data, true);
      setStatus(`Re-scored for ${data.character.name}`);
    } catch (err) { setStatus(String(err.message || err), true); }
  }

  gradeBtn.addEventListener('click', runGrade);

  /* ------------------------------------------------------------------ */
  /* rendering                                                           */
  /* ------------------------------------------------------------------ */
  const esc = (s) => String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

  function render(data, keepCompare) {
    $('empty').hidden = true;
    $('resultBody').hidden = false;

    const s = data.score;
    announceCharacter(data.character.id, data.character.name);
    $('scoreChar').textContent = data.character.name;
    $('scoreValue').textContent = s.value.toFixed(1);
    $('scoreSub').textContent = s.correctMain ? 'main stat matches the character' : 'main stat is off-meta';

    const chip = $('gradeChip');
    const cols = GRADE_COLORS[s.grade] || GRADE_COLORS['F'];
    chip.textContent = s.grade;
    chip.style.color = cols[1];
    chip.style.background = `linear-gradient(150deg, ${cols[2]}, rgba(0,0,0,.35))`;
    chip.style.borderColor = cols[1] + '66';
    chip.style.textShadow = `0 0 28px ${cols[1]}55`;

    const r = data.relic;
    const parts = String(r.piece || '').split(' - ');
    $('relicPiece').textContent = parts.slice(1).join(' - ') || r.piece || 'Unknown piece';
    $('relicSet').textContent = parts[0] || '';
    $('relicSlot').textContent = r.part || '?';
    $('relicStars').textContent = (r.grade || '?') + '\u2605';
    $('relicLevel').textContent = '+' + (r.level ?? 15);
    $('relicMain').textContent = `${r.mainStat} ${fmt(r.mainValue)}`;

    const body = $('subsBody');
    body.innerHTML = '';
    for (const sub of data.substats) {
      const tr = document.createElement('tr');
      const zero = !sub.weight || sub.weight <= 0;
      tr.innerHTML =
        `<td class="${zero ? 'zero' : ''}">${esc(sub.stat)}</td>` +
        `<td class="num">${esc(fmt(sub.shown))}</td>` +
        `<td class="num">${sub.badge ? '×' + sub.badge : '—'}</td>` +
        `<td class="num">${esc(fmtExact(sub.exact, sub.stat))}</td>` +
        `<td class="num ${zero ? 'zero' : ''}">${sub.weight ? sub.weight.toFixed(2) : '\u2014'}</td>` +
        `<td class="num ${zero ? 'zero' : ''}">${sub.weighted.toFixed(2)}</td>` +
        `<td class="bar-col"><div class="bar"><i style="width:${(sub.share * 100).toFixed(1)}%"></i></div></td>`;
      body.appendChild(tr);
    }

    $('bdRaw').textContent = s.raw.toFixed(2);
    $('bdIdeal').textContent = s.ideal.toFixed(2);

    const wl = $('warnings');
    wl.innerHTML = '';
    for (const w of (r.warnings || [])) {
      const li = document.createElement('li');
      li.textContent = w;
      wl.appendChild(li);
    }

    const dbg = $('debugPre');
    dbg.textContent = (r.lines || []).map((l) => {
      const v = l.value == null ? '?' : l.value;
      return `${(l.stat || '?').padEnd(20)} ${String(v).padStart(7)}  ${l.stat ? '' : l.raw || ''}`;
    }).join('\n');

    if (!keepCompare) {
      const sel = $('compare');
      sel.innerHTML = '<option value="">compare \u2026</option>';
      for (const c of CHARACTERS) {
        const o = document.createElement('option');
        o.value = c.id; o.textContent = c.name;
        sel.appendChild(o);
      }
      sel.onchange = async () => {
        if (!sel.value) return;
        try {
          const d = await postJSON('/api/rescore', { character: sel.value, relic: lastRelic });
          sel.value = '';
          render(d, true);
          setStatus(`Re-scored for ${d.character.name}`);
        } catch (err) { setStatus(String(err.message || err), true); }
      };
    }
  }

  function fmt(v) {
    if (v == null) return '?';
    const stat = arguments[1];
    if (typeof v !== 'number') return v;
    return v.toFixed(v % 1 === 0 ? 0 : 1) + '';
  }

  function fmtExact(v, stat) {
    if (v == null) return '?';
    const pct = /%$/.test(stat) || /Rate|DMG|Effect|RES|Break|Outgoing|Healing|ATK|DEF|HP/i.test(stat);
    const num = pct ? v.toFixed(2) + '%' : String(Math.round(v * 10) / 10);
    return num;
  }

  /* ------------------------------------------------------------------ */
  /* boot                                                                */
  /* ------------------------------------------------------------------ */
  fetch('/api/characters')
    .then((r) => r.json())
    .then((data) => {
      CHARACTERS = data.characters || [];
      $('charCount').textContent = `${CHARACTERS.length} characters \u00b7 grades F \u2192 AEON`;
      setStatus('Ready.');
      // V2 shows the first character's art so the page is never empty.
      const first = CHARACTERS[0];
      if (first) {
        window.dispatchEvent(new CustomEvent('relicgrader:ready',
          { detail: { id: first.id, name: first.name } }));
      }
    })
    .catch(() => setStatus('Could not load character list.', true));
})();
