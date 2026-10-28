const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

let jobs = [], records = [], kind = window.PLAYER_KIND || 'long', tags = [], thumb = '';
let currentTask = null, generation = 0, busy = false;
let shown = 0, pairNext = null;

const TEST_MODE = document.body.dataset.testMode === 'true';
const DEFAULT_CHANNEL = document.body.dataset.defaultChannel || '';
const PUBLISHED_VIEW = window.PLAYER_PUBLISHED === true;

async function api(url, data, method = 'POST') {
  const r = await fetch(url, data === undefined ? {} : {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
  const j = await r.json().catch(() => ({error: 'HTTP ' + r.status}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}

function message(text, error = false) {
  const el = $('form-message');
  if (!el) return;
  el.textContent = text;
  el.className = error ? 'error' : 'success';
}

function renderTags() {
  $('tags').replaceChildren();
  tags.forEach((tag, i) => {
    const s = document.createElement('span');
    s.className = 'chip';
    s.append(document.createTextNode(tag));
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = '×';
    b.onclick = () => { tags.splice(i, 1); renderTags(); };
    s.append(b);
    $('tags').append(s);
  });
  $('tags-count').textContent = (tags.reduce((n, t) => n + t.length + (t.includes(' ') ? 2 : 0), 0) + Math.max(tags.length - 1, 0)) + ' / 500';
}

function chapter(seconds = 0, title = '') {
  const row = document.createElement('div');
  row.className = 'chapter-row';

  const stamp = document.createElement('input');
  stamp.value = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
  stamp.placeholder = '0:00';
  stamp.setAttribute('aria-label', 'Chapter timestamp');

  const name = document.createElement('input');
  name.value = title;
  name.placeholder = 'Chapter title';
  name.setAttribute('aria-label', 'Chapter title');

  const remove = document.createElement('button');
  remove.type = 'button';
  remove.className = 'secondary';
  remove.textContent = '×';
  remove.onclick = () => row.remove();

  row.append(stamp, name, remove);
  $('chapters').append(row);
}

function form() {
  const chapters = [...$('chapters').children].map(r => {
    const [stamp, title] = r.querySelectorAll('input');
    if (!/^\d+:[0-5]\d(?::[0-5]\d)?$/.test(stamp.value)) throw Error('Use valid chapter timestamps, such as 0:00.');
    return {seconds: stamp.value.split(':').reduce((a, n) => a * 60 + Number(n), 0), title: title.value};
  });
  return {
    job: $('job').value,
    kind,
    channel: $('channel').value,
    title: $('title').value,
    description: $('description').value,
    tags,
    category: $('category').value,
    visibility: document.querySelector('[name=visibility]:checked').value,
    made_for_kids: document.querySelector('[name=kids]:checked').value === 'yes',
    language: $('language').value,
    chapters: kind === 'long' ? chapters : [],
    thumbnail: thumb,
    link_target: $('link-target').value
  };
}

function counts() {
  $('title-count').textContent = $('title').value.length + ' / 100';
  $('description-count').textContent = $('description').value.length + ' / 5000';
  $('hook-preview').textContent = $('description').value.split('\n').slice(0, 3).join('\n');
}

function previewThumb() {
  $('thumbnail').src = thumb ? `/api/thumbnail/${$('channel').value}/${$('job').value}/${kind}/${thumb}?v=${Date.now()}` : '';
  $('thumbnail').style.aspectRatio = kind === 'short' ? '9/16' : '16/9';
}

function linkOptions() {
  const search = $('link-search').value.toLowerCase();
  const selected = $('link-target').value;
  $('link-target').replaceChildren(new Option('None — publish without a link', ''));
  records
    .filter(r => !(String(r.job) === String($('job').value) && r.kind === kind && r.channel === $('channel').value) &&
      `${r.title} ${r.channel} ${r.video_id}`.toLowerCase().includes(search))
    .forEach(r => $('link-target').add(new Option(`${r.title} · ${r.channel} · ${r.video_id}`, r.video_id)));
  $('link-target').value = selected;
}

function applyTestMode() {
  if (!TEST_MODE) return;
  document.querySelectorAll('.js-action').forEach(b => {
    b.disabled = true;
    if (!b.dataset.testTitled) {
      b.dataset.testTitled = '1';
      b.title = b.title ? b.title + ' — TEST copy: actions are disabled' : 'TEST copy: actions are disabled';
    }
  });
  const file = $('custom-file');
  if (file) file.disabled = true;
}

function publishedLink(record) {
  const href = record.url || (record.video_id ? 'https://youtu.be/' + encodeURIComponent(String(record.video_id)) : '');
  const label = (record.kind === 'short' ? 'Short' : 'Explainer') + (record.title ? ': ' + record.title : '');
  return href
    ? `<div class="row"><a href="${esc(href)}" target="_blank" rel="noopener">${esc(label)} ↗</a></div>`
    : `<div class="muted">${esc(label)} (no link recorded)</div>`;
}

function renderPublishedLinks() {
  const job = String($('job').value || '');
  const channel = String($('channel').value || '');
  const matches = records.filter(r =>
    String(r.job || '') === job &&
    String(r.channel || '') === channel &&
    String(r.kind || 'long') === kind
  );
  const links = matches.map(publishedLink).join('');
  $('published-links').innerHTML = '<h2>Published on YouTube</h2>' +
    (links || '<p class="muted">No published link was recorded for this job/channel/kind.</p>');
}

async function load() {
  $('publish-button').disabled = true;
  const seq = ++generation;
  const job = jobs.find(j => j.id === $('job').value);
  $('job-error').textContent = '';

  for (const k of ['short', 'long']) {
    $('tab-' + k).disabled = !job?.types[k];
    $('tab-' + k).classList.toggle('active', kind === k);
    $('tab-' + k).setAttribute('aria-selected', kind === k);
  }

  if (!job || !Object.keys(job.types).length) {
    $('job-error').textContent = 'No video found in this job folder.';
    $('publish-button').disabled = true;
    $('player').removeAttribute('src');
    $('player').load();
    $('thumbnail').removeAttribute('src');
    $('filename').textContent = 'No video found in this job folder.';
    $('file-info').textContent = '';
    applyTestMode();
    return;
  }

  if (!job.types[kind]) {
    kind = job.types.long ? 'long' : 'short';
    return load();
  }

  try {
    const j = await api(`/api/defaults/${job.id}/${kind}/${$('channel').value}`);
    if (seq !== generation) return;

    const d = j.data;
    $('title').value = d.title;
    $('description').value = d.description;
    tags = d.tags;
    thumb = d.thumbnail;
    $('category').value = d.category;
    $('language').value = d.language;
    document.querySelector('[name=visibility][value=Private]').checked = true;
    document.querySelector('[name=kids][value=no]').checked = true;
    $('chapters').replaceChildren();
    d.chapters.forEach(c => chapter(c.seconds, c.title));
    $('chapter-section').hidden = kind === 'short';
    $('link-label').textContent = kind === 'short' ? 'Link this Short to (optional):' : 'End screen link (optional):';
    $('link-target').value = '';
    $('player').src = `/api/video/${job.id}/${kind}`;
    $('player').classList.toggle('short', kind === 'short');
    $('preview-kind').textContent = kind === 'short' ? 'SHORT · 9:16' : 'EXPLAINER · 16:9';
    $('filename').textContent = j.media.filename;
    const m = j.media;
    $('file-info').textContent = `${(m.size / 1024 / 1024).toFixed(1)} MB · ${Math.floor(m.duration / 60)}:${String(Math.floor(m.duration % 60)).padStart(2, '0')} · ${m.width} × ${m.height} · ${m.fps} fps`;

    renderTags();
    previewThumb();
    counts();
    linkOptions();
    $('publish-button').disabled = busy;
    $('publish-both').hidden = !(job.types.long && job.types.short);
    $('publish-both').disabled = busy;
    applyTestMode();
  } catch (e) {
    message(e.message, true);
    applyTestMode();
  }
}

async function start(mode = 'new') {
  if (TEST_MODE) throw Error('TEST copy: actions are disabled');
  try {
    const data = form();
    if (!data.thumbnail || !data.title.trim() || !data.description.trim()) throw Error('Choose a thumbnail and fill title and description.');
    if (mode === 'restart') {
      if (!confirm('An existing upload may already exist. Restart can create a duplicate. Check Studio first. Continue?')) return;
      data.confirm_restart = true;
    }
    data.mode = mode;
    const result = await api('/publish', data);
    currentTask = result.task_id;
    localStorage.setItem('publisherTask', currentTask);
    busy = true;
    $('publish-button').disabled = true;
    $('recovery').hidden = true;
    $('progress-empty').hidden = true;
    $('progress-log').replaceChildren();
    message('Publishing started.');
    applyTestMode();
    poll();
  } catch (e) {
    message(e.message, true);
    $('recovery').hidden = false;
    applyTestMode();
  }
}

async function startPair() {
  if (TEST_MODE) throw Error('TEST copy: actions are disabled');
  try {
    const job = $('job').value, ch = $('channel').value, cur = form();
    if (!cur.thumbnail || !cur.title.trim() || !cur.description.trim()) throw Error('Choose a thumbnail and fill title and description.');
    const other = kind === 'long' ? 'short' : 'long';
    const o = (await api(`/api/defaults/${job}/${other}/${ch}`)).data;
    const body = {};
    body[kind] = cur;
    body[other] = o;
    if (!confirm('Publish the explainer first, then the Short with the explainer link (both Private unless chosen otherwise)?')) return;

    const r = await api('/publish/pair', body);
    currentTask = r.long_task;
    pairNext = r.short_task;
    localStorage.setItem('publisherTask', currentTask);
    busy = true;
    $('publish-button').disabled = true;
    $('publish-both').disabled = true;
    $('progress-empty').hidden = true;
    $('progress-log').replaceChildren();
    message('Publishing the explainer, then the Short.');
    applyTestMode();
    poll();
  } catch (e) {
    message(e.message, true);
    applyTestMode();
  }
}

async function poll() {
  try {
    const t = await api('/publish/status/' + currentTask);
    $('task-status').textContent = t.status.toUpperCase();
    if (shown > $('progress-log').childElementCount) shown = 0;
    t.events.slice(shown).forEach(e => {
      const div = document.createElement('div');
      div.className = 'event';
      const time = document.createElement('time');
      time.textContent = e.time;
      div.append(time, document.createTextNode(e.message));
      if (e.screenshot) {
        const img = document.createElement('img');
        img.loading = 'lazy';
        img.alt = e.message;
        img.src = `/publish/screenshot/${currentTask}/${e.screenshot}`;
        div.append(img);
      }
      $('progress-log').append(div);
    });
    shown = t.events.length;

    if (t.status === 'complete' && pairNext) {
      const nx = pairNext;
      pairNext = null;
      currentTask = nx;
      shown = 0;
      localStorage.setItem('publisherTask', nx);
      $('progress-log').replaceChildren();
      message('Explainer done: ' + t.result.url + ' — publishing the Short.');
      setTimeout(poll, 1000);
      return;
    }

    if (t.status === 'complete') {
      $('result').replaceChildren();
      const a = document.createElement('a');
      a.href = t.result.url;
      a.target = '_blank';
      a.rel = 'noopener';
      a.textContent = 'Open on YouTube ↗';
      $('result').append(a);
      if (t.result.link_error) {
        const p = document.createElement('p');
        p.className = 'error';
        p.textContent = t.result.link_error;
        $('result').append(p);
        $('recovery').hidden = false;
      }
      records = await api('/api/published');
      linkOptions();
      busy = false;
      $('publish-button').disabled = false;
      applyTestMode();
      message('Published. Closing…');
      try {
        if (window.opener && !window.opener.closed) {
          window.opener.postMessage({type:'pub-action', action:'publish'}, '*');
        }
      } catch (e) {}
      setTimeout(() => window.close(), 900);
    } else if (['error', 'cancelled'].includes(t.status)) {
      message(t.error || 'Cancelled', true);
      $('recovery').hidden = false;
      busy = false;
      $('publish-button').disabled = false;
      applyTestMode();
    } else {
      setTimeout(poll, 1000);
    }
  } catch (e) {
    message(e.message, true);
    busy = false;
    $('publish-button').disabled = false;
    applyTestMode();
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  $('publish-form').onsubmit = e => { e.preventDefault(); shown = 0; start(); };
  $('job').onchange = load;
  $('channel').onchange = load;

  ['short', 'long'].forEach(k => {
    $('tab-' + k).onclick = () => { if (kind !== k) { kind = k; load(); } };
  });

  $('title').oninput = counts;
  $('description').oninput = counts;

  $('tag-entry').onkeydown = e => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      const t = e.target.value.trim();
      if (t && !tags.some(x => x.toLowerCase() === t.toLowerCase())) tags.push(t);
      e.target.value = '';
      renderTags();
    }
  };

  $('add-chapter').onclick = () => chapter();
  $('link-search').oninput = linkOptions;

  $('publish-both').onclick = async () => {
    try { await startPair(); } catch (e) { message(e.message, true); }
  };

  $('save-draft').onclick = async () => {
    try {
      if (TEST_MODE) throw Error('TEST copy: actions are disabled');
      await api('/api/draft', form());
      message('Draft saved.');
    } catch (e) { message(e.message, true); }
  };

  $('reset').onclick = load;

  $('cancel').onclick = async () => {
    if (currentTask && busy) {
      if (TEST_MODE) { message('TEST copy: actions are disabled', true); return; }
      try {
        await api('/publish/cancel/' + currentTask, {});
      } catch (e) { message(e.message, true); }
    } else {
      message('Cancelled.');
      load();
    }
  };

  $('retry').onclick = () => { shown = 0; start('resume').catch(e => message(e.message, true)); };
  $('restart').onclick = () => { shown = 0; start('restart').catch(e => message(e.message, true)); };

  document.querySelectorAll('.regenerate').forEach(b => {
    b.onclick = async () => {
      b.disabled = true;
      message('Regenerating ' + b.dataset.field + '…');
      try {
        if (TEST_MODE) throw Error('TEST copy: actions are disabled');
        const snapshot = form();
        const j = await api('/api/regenerate', {...snapshot, field: b.dataset.field});
        if (snapshot.job !== $('job').value || snapshot.kind !== kind || snapshot.channel !== $('channel').value) return;
        if (b.dataset.field === 'tags') {
          tags = j.value;
          renderTags();
        } else if (b.dataset.field === 'chapters') {
          $('chapters').replaceChildren();
          j.value.forEach(c => chapter(c.seconds, c.title));
        } else {
          $(b.dataset.field).value = j.value;
        }
        counts();
        message('Updated ' + b.dataset.field + '.');
      } catch (e) {
        message(e.message, true);
      } finally {
        b.disabled = false;
        applyTestMode();
      }
    };
  });

  async function uploadThumb(file, seconds) {
    if (TEST_MODE) throw Error('TEST copy: actions are disabled');
    try {
      const data = new FormData();
      data.set('job', $('job').value);
      data.set('channel', $('channel').value);
      data.set('kind', kind);
      if (file) data.set('file', file);
      else data.set('seconds', seconds);

      const r = await fetch('/api/thumbnail', {method:'POST', body:data});
      const j = await r.json();
      if (!r.ok) throw Error(j.error);
      thumb = j.thumbnail;
      previewThumb();
      $('frame-dialog').close();
      message('Thumbnail updated.');
    } catch (e) {
      message(e.message, true);
    }
  }

  $('custom-open').onclick = () => $('custom-file').click();
  $('custom-file').onchange = e => {
    if (e.target.files[0]) uploadThumb(e.target.files[0]);
  };
  $('generated').onclick = () => { thumb = 'generated'; previewThumb(); };

  $('frame-open').onclick = () => {
    $('frame-player').src = $('player').src;
    $('frame-dialog').showModal();
  };
  $('frame-player').onloadedmetadata = () => {
    $('frame-time').max = Math.max(0, $('frame-player').duration - .1);
  };
  $('frame-time').oninput = e => {
    $('frame-player').currentTime = Number(e.target.value);
    $('frame-position').textContent = Math.floor(e.target.value / 60) + ':' + String(Math.floor(e.target.value % 60)).padStart(2, '0');
  };
  $('frame-save').onclick = () => uploadThumb(null, $('frame-player').currentTime);
  $('frame-close').onclick = () => {
    $('frame-player').pause();
    $('frame-dialog').close();
  };

  try {
    records = await api('/api/published');
    const params = new URLSearchParams(location.search);

    if (params.get('job')) $('job').value = params.get('job');
    if (params.get('channel')) $('channel').value = params.get('channel');
    if (params.get('kind') === 'short' || params.get('kind') === 'long') kind = params.get('kind');

    if (PUBLISHED_VIEW) {
      document.querySelectorAll('.edit-only, .video-preview-card, .channel-row, .tabs').forEach(el => el.hidden = true);
      $('published-links').hidden = false;
      renderPublishedLinks();
      applyTestMode();
      return;
    }

    jobs = await api('/api/jobs');
    await load();

    const previous = params.get('task') || localStorage.getItem('publisherTask');
    if (previous) {
      currentTask = previous;
      $('progress-empty').hidden = true;
      poll();
    }
    applyTestMode();
  } catch (e) {
    message(e.message, true);
    applyTestMode();
  }
});
