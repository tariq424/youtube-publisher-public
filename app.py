"""Local, independent publishing UI. Run only on loopback."""
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file
from PIL import Image
import publisher_logic as logic
import youtube_publisher as backend

ROOT = Path(__file__).resolve().parent
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 12 * 1024 * 1024
tasks = {}
task_lock = threading.Lock()
browser_lock = threading.Lock()

@app.before_request
def local_requests():
    # Prevent a remote site from submitting publish requests to localhost.
    if request.method != 'GET':
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            return jsonify(error='Cross-origin requests are not allowed.'), 403
    if request.host.split(':')[0] not in ('127.0.0.1', 'localhost'):
        return jsonify(error='Local access only.'), 403

@app.errorhandler(ValueError)
@app.errorhandler(FileNotFoundError)
def input_error(error):
    return jsonify(error=str(error)), 400

@app.get('/')
def home():
    channels = []
    for path in (ROOT / 'channel_configs').glob('*.json'):
        channels.append({'key': path.stem, 'name': backend.read_json(path)['youtube_channel_name']})
    return render_template('publish.html', channels=channels, categories=backend.CATEGORIES)

@app.get('/health')
def health():
    return jsonify(service='youtube-publisher', port=logic.config()['port'])

@app.get('/api/jobs')
def jobs():
    return jsonify(logic.jobs())

@app.get('/api/published')
def published():
    return jsonify(logic.records())

@app.get('/api/video/<job>/<kind>')
def video(job, kind):
    return send_file(logic.assets(job, kind)[0], conditional=True)

@app.get('/api/defaults/<job>/<kind>/<channel>')
def defaults(job, kind, channel):
    data = logic.defaults(job, kind, channel)
    video, thumb, _ = logic.assets(job, kind)
    return jsonify(data=data, media=dict(filename=video.name, size=video.stat().st_size, **logic.probe(video)))

@app.get('/api/thumbnail/<channel>/<job>/<kind>/<name>')
def thumbnail(channel, job, kind, name):
    return send_file(logic.thumbnail_path(dict(channel=channel, job=job, kind=kind, thumbnail=name)), conditional=True)

@app.post('/api/thumbnail')
def create_thumbnail():
    job, channel, kind = request.form['job'], request.form['channel'], request.form['kind']
    backend.load_channel(channel)
    video = logic.assets(job, kind)[0]
    folder = logic.destination(channel, job) / 'thumbnails'
    folder.mkdir(parents=True, exist_ok=True)
    name = uuid.uuid4().hex + '.jpg'
    path = folder / name
    if 'file' in request.files:
        image = Image.open(request.files['file'].stream)
        image.load()
        image.convert('RGB').save(path, quality=92)
    else:
        import subprocess
        position = float(request.form.get('seconds', '0'))
        duration = logic.probe(video)['duration']
        if not 0 <= position < duration:
            raise ValueError('Frame must be within the video.')
        subprocess.run([logic.ffmpeg(), '-y', '-ss', str(position), '-i', str(video), '-frames:v', '1', str(path)],
                       capture_output=True, timeout=40, check=True)
    with Image.open(path) as image:
        width, height = (720, 1280) if kind == 'short' else (1280, 720)
        from PIL import ImageOps
        ImageOps.fit(image, (width, height)).save(path, quality=92)
    return jsonify(thumbnail=name)

@app.post('/api/regenerate')
def regenerate():
    data = request.get_json()
    original = logic.original_description(data['job'], data['kind'])
    field = data['field']
    if field == 'chapters':
        return jsonify(value=logic.job_chapters(data['job'], data['kind']))
    if field not in ('title', 'description', 'tags'):
        raise ValueError('Unsupported field')
    meta = backend.generate(logic.job_path(data['job']), original, data['kind'], None)
    _, cfg = backend.load_channel(data['channel'])
    backend.apply_defaults(meta, original, cfg)
    return jsonify(value=meta[field])

@app.post('/api/draft')
def save_draft():
    data = request.get_json()
    backend.load_channel(data['channel'])
    logic.assets(data['job'], data['kind'])
    folder = logic.destination(data['channel'], data['job'])
    folder.mkdir(parents=True, exist_ok=True)
    backend.write_json(folder / 'draft.json', data)
    return jsonify(saved=True)

def update(task, message, screenshot=None):
    with task_lock:
        event = {'time': time.strftime('%H:%M:%S'), 'message': message}
        if screenshot:
            event['screenshot'] = screenshot
        task['events'].append(event)
        backend.write_json(task['folder'] / 'task.json', {k: v for k, v in task.items() if k != 'folder'})
    logging.info('%s %s', task['id'], message)

def worker(task, data, mode):
    folder = task['folder']
    try:
        if not browser_lock.acquire(blocking=False):
            raise ValueError('Another publish is using the shared Chrome profile. Try again after it finishes.')
        try:
            profile_lock = ROOT / 'profiles' / '.main-upload.lock'
            fd = os.open(profile_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            try:
                cfg = logic.config()
                backend.load_global(require_profile=True)
                _, channel = backend.load_channel(data['channel'])
                task['status'] = 'running'
                result = backend.upload_from_form(data, logic.assets(data['job'], data['kind'])[0], logic.thumbnail_path(data),
                                 cfg, channel['youtube_channel_name'], folder,
                                 lambda message, shot=None: update(task, message, shot),
                                 lambda: task.get('cancel_requested', False), mode)
                record = dict(channel=data['channel'], job=data['job'], kind=data['kind'],
                              title=data['title'], timestamp=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                              metadata=data, **result)
                destination = logic.destination(data['channel'], data['job'])
                name = 'published.json'
                if (destination / name).exists() and backend.read_json(destination / name).get('kind') != data['kind']:
                    name = f"published_{data['kind']}.json"
                backend.write_json(destination / name, record)
                (destination / f"youtube_{data['kind']}_url.txt").write_text(result['url'] + '\n', encoding='utf-8')
                task.update(status='complete', result=record)
                update(task, 'Upload complete.' + (' Linking needs manual completion.' if result.get('link_error') else ''))
            finally:
                profile_lock.unlink(missing_ok=True)
        finally:
            browser_lock.release()
    except Exception as error:
        summary = str(error).splitlines()[0]
        task.update(status='cancelled' if task.get('cancel_requested') else 'error', error=summary)
        update(task, summary)
        logging.exception('Publish failed')

@app.post('/publish')
def submit():
    body = request.get_json()
    data = logic.finalize(body)
    mode = body.get('mode', 'new')
    if mode not in ('new', 'resume', 'restart'):
        raise ValueError('Unknown retry mode')
    destination = logic.destination(data['channel'], data['job'])
    destination.mkdir(parents=True, exist_ok=True)
    if any(r.get('channel') == data['channel'] and r.get('job') == data['job'] and r.get('kind') == data['kind'] for r in logic.records()) and mode != 'resume':
        raise ValueError('This video already has a published record. Use Retry to finish linking or edit it in Studio.')
    active = [t for t in tasks.values() if t['status'] in ('queued', 'running', 'waiting')]
    if active:
        raise ValueError('Another publish is in progress.')
    state = destination / f"automation_{data['kind']}.json"
    if state.exists() and mode == 'new':
        raise ValueError('Previous upload state exists. Use Retry from this step or explicitly Restart upload.')
    if mode == 'restart' and not body.get('confirm_restart'):
        raise ValueError('Confirm possible duplicate upload before restarting.')
    backend.write_json(destination / 'draft.json', data)
    task_id = uuid.uuid4().hex
    folder = destination / 'tasks' / task_id
    folder.mkdir(parents=True)
    task = dict(id=task_id, status='queued', events=[], folder=folder)
    tasks[task_id] = task
    update(task, 'Metadata validated. Starting publisher...')
    threading.Thread(target=worker, args=(task, data, mode), daemon=True).start()
    return jsonify(task_id=task_id), 202

@app.post('/publish/pair')
def submit_pair():
    """Publish both versions of one job in order: the explainer first; when it is complete, its YouTube URL replaces the
    Short's link placeholder and the Short is published. If the explainer fails, the Short is not published."""
    body = request.get_json()
    long_body, short_body = dict(body['long']), dict(body['short'])
    if long_body.get('job') != short_body.get('job') or str(long_body.get('channel', '')).lower() != str(short_body.get('channel', '')).lower():
        raise ValueError('Both videos must come from the same job and go to the same channel.')
    if long_body.get('kind') != 'long' or short_body.get('kind') != 'short':
        raise ValueError('Pair publishing needs one explainer (long) and one Short.')
    if [t for t in tasks.values() if t['status'] in ('queued', 'running', 'waiting')]:
        raise ValueError('Another publish is in progress.')
    long_data = logic.finalize(long_body)
    if any(r.get('channel') == long_data['channel'] and r.get('job') == long_data['job'] and r.get('kind') == 'short' for r in logic.records()):
        raise ValueError('This Short already has a published record.')
    probe = logic.finalize({**short_body, 'long_url': 'https://www.youtube.com/watch?v=PENDING0000'})   # validates the Short now
    existing_long = logic.long_record(long_data['channel'], long_data['job'])
    created = {}
    for kind, data in (('long', long_data), ('short', probe)):
        destination = logic.destination(data['channel'], data['job'])
        destination.mkdir(parents=True, exist_ok=True)
        task_id = uuid.uuid4().hex
        folder = destination / 'tasks' / task_id
        folder.mkdir(parents=True)
        created[kind] = dict(id=task_id, status='queued' if kind == 'long' else 'waiting', events=[], folder=folder)
        tasks[task_id] = created[kind]
    update(created['short'], 'Waiting for the explainer to finish; its link goes into this Short.')

    def run_pair():
        lt, st = created['long'], created['short']
        if existing_long:
            update(lt, 'Explainer already published: ' + existing_long['url'])
            lt.update(status='complete', result=existing_long)
        else:
            mode = 'resume' if (logic.destination(long_data['channel'], long_data['job']) / 'automation_long.json').exists() else 'new'
            update(lt, 'Metadata validated. Publishing the explainer first...')
            worker(lt, long_data, mode)
        if lt['status'] != 'complete':
            st.update(status='error', error='Explainer did not finish; the Short was not published so it never links to nothing.')
            update(st, st['error'])
            return
        url = lt['result']['url']
        try:
            short_data = logic.finalize({**short_body, 'long_url': url})
        except Exception as error:
            st.update(status='error', error=str(error).splitlines()[0]); update(st, st['error']); return
        backend.write_json(logic.destination(short_data['channel'], short_data['job']) / 'draft.json', short_data)
        st['status'] = 'queued'
        update(st, 'Explainer is live at ' + url + '; publishing the Short with that link...')
        worker(st, short_data, 'resume' if (logic.destination(short_data['channel'], short_data['job']) / 'automation_short.json').exists() else 'new')

    threading.Thread(target=run_pair, daemon=True).start()
    return jsonify(long_task=created['long']['id'], short_task=created['short']['id']), 202

@app.get('/publish/status/<task_id>')
def status(task_id):
    task = tasks.get(task_id)
    if not task:
        matches = list((ROOT / 'uploads').glob(f'*/*/tasks/{logic.identifier(task_id)}/task.json'))
        if not matches:
            return jsonify(error='Task not found.'), 404
        task = backend.read_json(matches[0])
        if task['status'] in ('queued', 'running'):
            task.update(status='error', error='Publisher restarted. Retry to recover the existing upload.')
    return jsonify({k: v for k, v in task.items() if k != 'folder'})

@app.get('/publish/screenshot/<task_id>/<name>')
def screenshot(task_id, name):
    matches = list((ROOT / 'uploads').glob(f'*/*/tasks/{logic.identifier(task_id)}/{logic.identifier(Path(name).stem)}.png'))
    if not matches:
        return jsonify(error='Screenshot not found'), 404
    return send_file(matches[0], conditional=True)

@app.post('/publish/cancel/<task_id>')
def cancel(task_id):
    if task_id in tasks:
        tasks[task_id]['cancel_requested'] = True
    return jsonify(cancelled=True)

if __name__ == '__main__':
    cfg = logic.config()
    Path(cfg['log_dir']).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=Path(cfg['log_dir']) / 'publisher.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s', encoding='utf-8')
    app.run(host='127.0.0.1', port=int(cfg['port']), debug=False, threaded=True, use_reloader=False)
