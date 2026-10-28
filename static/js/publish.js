const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(url, data) {
  const r = await fetch(url, data === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const j = await r.json().catch(() => ({error: 'HTTP ' + r.status}));
  if (!r.ok) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}

const DEFAULT_CHANNEL = document.body.dataset.defaultChannel || '';
const TEST_MODE = document.body.dataset.testMode === 'true';

function openItem(item, published = false) {
  const params = new URLSearchParams({
    job: item.job,
    kind: item.kind,
    channel: item.channel || DEFAULT_CHANNEL
  });
  if (published) params.set('published', '1');
  window.open('/player?' + params.toString(), 'pubplayer', 'width=1200,height=850');
}

function kindLabel(types) {
  if (types && types.long && types.short) return 'Explainer + Short';
  if (types && types.long) return 'Explainer';
  if (types && types.short) return 'Short';
  return 'Unknown';
}

function makeRotator(container, items, render) {
  let idx = 0;

  function paint() {
    container.replaceChildren();
    if (!items.length) {
      container.innerHTML = '<div class="card muted">Nothing here.</div>';
      return;
    }

    const item = items[idx];
    const card = document.createElement('div');
    card.className = 'rotator-card card';
    card.innerHTML = `
      <div class="rotator-top">
        <div class="tags muted">${render.tags ? esc(render.tags(item)) : ''}</div>
        <span class="counter">${idx + 1} of ${items.length}</span>
      </div>
      <div class="field-head">
        <h3>${esc(render.title(item))}</h3>
        <button class="primary open-btn" data-action="open">Open ↗</button>
      </div>
      <p class="muted">${esc(render.subtitle(item))}</p>`;

    card.querySelector('[data-action="open"]').onclick = () => render.open(item);
    container.append(card);

    if (items.length > 1) {
      const nav = document.createElement('div');
      nav.className = 'nav';

      const prev = document.createElement('button');
      prev.type = 'button';
      prev.className = 'secondary';
      prev.textContent = '← Prev';
      prev.onclick = () => { idx = (idx - 1 + items.length) % items.length; paint(); };

      const next = document.createElement('button');
      next.type = 'button';
      next.className = 'secondary';
      next.textContent = 'Next →';
      next.onclick = () => { idx = (idx + 1) % items.length; paint(); };

      nav.append(prev, next);
      container.append(nav);
    }
  }

  paint();
}

async function load() {
  try {
    const [jobs, published] = await Promise.all([
      api('/api/jobs'),
      api('/api/published')
    ]);

    const jobItems = jobs.map(j => ({
      job: j.id,
      kind: j.types && j.types.long ? 'long' : (j.types && j.types.short ? 'short' : 'long'),
      channel: j.channel || DEFAULT_CHANNEL,
      title: j.title || j.id,
      types: j.types || {}
    }));

    makeRotator($('ready'), jobItems, {
      tags: item => kindLabel(item.types),
      title: item => item.title,
      subtitle: item => `${item.channel || 'unknown channel'} · ${kindLabel(item.types)}`,
      open: item => openItem(item, false)
    });

    const pubItems = published.map(r => ({
      job: r.job,
      kind: r.kind === 'short' ? 'short' : 'long',
      channel: r.channel || DEFAULT_CHANNEL,
      title: r.title || r.job,
      video_id: r.video_id || ''
    }));

    makeRotator($('published'), pubItems, {
      tags: item => item.kind === 'short' ? 'Short' : 'Explainer',
      title: item => item.title,
      subtitle: item => `${item.channel || 'unknown channel'} · ${item.kind === 'short' ? 'Short' : 'Explainer'}${item.video_id ? ' · ' + item.video_id : ''}`,
      open: item => openItem(item, true)
    });
  } catch (e) {
    $('ready').innerHTML = `<div class="error">${esc(e.message)}</div>`;
    $('published').innerHTML = `<div class="error">${esc(e.message)}</div>`;
  }
}

window.addEventListener('message', e => {
  if (e.data && e.data.type === 'pub-action') load();
});

document.addEventListener('DOMContentLoaded', load);
