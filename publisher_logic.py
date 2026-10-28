"""Finished-job discovery and metadata validation. No pipeline imports or writes."""
import json
import re
import shutil
import subprocess
from pathlib import Path
import youtube_publisher as backend

ROOT = Path(__file__).resolve().parent

def config():
    return backend.read_json(ROOT / 'config.json')

def identifier(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', str(value)):
        raise ValueError('Invalid job/channel identifier')
    return str(value)

def job_roots():
    """Video Studio's jobs folder, then any extra roots (e.g. the Newsroom's staging folder)."""
    cfg = config()
    return [Path(cfg['video_studio_jobs'])] + [Path(p) for p in cfg.get('extra_job_roots', [])]

def job_path(job):
    identifier(job)
    roots = job_roots()
    return next((r / job for r in roots if (r / job).is_dir()), roots[0] / job)

def assets(job, kind):
    if kind not in ('short', 'long'):
        raise ValueError('Unknown video type')
    folder = job_path(job) / 'output'
    videos = [p for p in folder.glob('*_short.mp4' if kind == 'short' else '*_explainer_*.mp4') if not p.name.startswith('_')]
    if len(videos) != 1:
        raise ValueError('No video found in this job folder.' if not videos else 'Multiple videos found; resolve ambiguity first.')
    description = folder / ('youtube_short_description.txt' if kind == 'short' else 'youtube_description.txt')
    thumbs = [folder / name for name in (('thumbnail_9_16.png',) if kind == 'short' else
             ('thumbnail_16_9.png', 'thumbnail_16_9.jpg', 'thumbnail.png', 'thumbnail_9_16.png'))]
    return videos[0], next((p for p in thumbs if p.is_file()), None), description

def records():
    result, seen = [], set()
    for path in (ROOT / 'uploads').glob('*/*/published*.json'):
        try:
            record = backend.read_json(path)
            if record.get('deleted') or record.get('video_id') in seen or not record.get('video_id'):
                continue
            seen.add(record['video_id'])
            result.append(record)
        except (ValueError, OSError):
            continue
    return result

def find_record(channel, job, kind):
    """Return (path, record) for channel+job+kind, including deleted records."""
    for path in (ROOT / 'uploads').glob('*/*/published*.json'):
        try:
            record = backend.read_json(path)
        except (ValueError, OSError):
            continue
        if record.get('channel') == channel and record.get('job') == job and record.get('kind') == kind:
            return path, record
    return None, None

PLACEHOLDER = '<PASTE LONG VIDEO LINK HERE>'
_PLACEHOLDER_LINE = re.compile(r'(?m)^[^\r\n]*' + re.escape(PLACEHOLDER) + r'[^\r\n]*(?:\r?\n)?(?:[ \t]*\r?\n)?')

def long_record(channel, job):
    """The published explainer of this job on this channel, or None."""
    for record in records():
        if record.get('job') == job and record.get('kind') == 'long' and record.get('channel', '').lower() == channel.lower():
            return record
    return None

def has_long(job):
    try:
        assets(job, 'long')
        return True
    except ValueError:
        return False

def link_short(job, channel, description, long_url=None):
    """Short <-> explainer cross-link. -> (description, state)
    'linked'     the placeholder is replaced with the explainer's URL (given, or from its published record)
    'needs_long' the job has an explainer that is not published yet: the placeholder stays, publishing must wait
    'no_long'    the job has no explainer: the placeholder line (the promise of a longer video) is removed
    'none'       nothing to link"""
    url = long_url or (long_record(channel, job) or {}).get('url')
    if PLACEHOLDER not in description:
        # a Short made on its own whose explainer was made later: add the link line it never had
        if url and url not in description and has_long(job):
            return description.rstrip() + f'\n\nFull breakdown: {url}\n', 'linked'
        return description, 'none'
    if url:
        return description.replace(PLACEHOLDER, url), 'linked'
    if has_long(job):
        return description, 'needs_long'
    return _PLACEHOLDER_LINE.sub('', description).rstrip() + '\n', 'no_long'

AI_TAG = re.compile(r'GENERATED|FLOW|GEMINI', re.I)

def ai_content(job):
    """Does the video contain AI-generated visuals (Gemini images, Google Flow / WanGP clips)? -> (bool, [reasons]).
    The Newsroom writes ai_content.json when it stages a job; otherwise the render timelines' rung tags decide."""
    folder = job_path(job)
    marker = folder / 'ai_content.json'
    if marker.is_file():
        try:
            data = backend.read_json(marker)
            return bool(data.get('altered')), list(data.get('why', []))
        except (OSError, ValueError):
            pass
    why = []
    for timeline in (folder / 'short' / 'public' / 'teaser.json', folder / 'build' / 'public' / 'teaser.json'):
        try:
            data = backend.read_json(timeline)
        except (OSError, ValueError):
            continue
        for beat in data.get('beats', []):
            for bg in beat.get('bgs', []):
                tag = str(bg.get('tag') or '')
                if AI_TAG.search(tag) and tag not in why:
                    why.append(tag)
    return bool(why), why

def destination(channel, job):
    return ROOT / 'uploads' / identifier(channel).lower() / identifier(job)

def jobs():
    result, seen = [], set()
    folders = [j for root in job_roots() if root.exists() for j in root.iterdir()]
    for job in sorted(folders, key=lambda j: j.name, reverse=True):
        if not job.is_dir() or not re.fullmatch(r'[A-Za-z0-9_-]+', job.name) or job.name in seen:
            continue
        seen.add(job.name)
        kinds = {}
        for kind in ('short', 'long'):
            try:
                video, thumb, desc = assets(job.name, kind)
                kinds[kind] = {'filename': video.name, 'size': video.stat().st_size,
                               'thumbnail': bool(thumb), 'description': desc.is_file()}
            except ValueError:
                pass
        state = {}
        try:
            state = backend.read_json(job / 'state.json')
        except (ValueError, OSError):
            pass
        if kinds or state.get('status') == 'finished':
            result.append({'id': job.name, 'types': kinds})
    return result

def original_description(job, kind):
    path = assets(job, kind)[2]
    return path.read_bytes().decode('utf-8-sig') if path.exists() else ''

def parse_chapters(text):
    values = []
    for stamp, title in re.findall(r'(?m)^(\d+:\d{2}(?::\d{2})?)\s+(.+?)\r?$', text):
        seconds = 0
        for part in stamp.split(':'):
            seconds = seconds * 60 + int(part)
        values.append({'seconds': seconds, 'title': title})
    return values

def job_chapters(job, kind):
    if kind == 'short':
        return []
    existing = parse_chapters(original_description(job, kind))
    if existing:
        return existing
    root = job_path(job)
    for path in (root / 'build/public/teaser.json', root / 'longedit/public/teaser.json'):
        if not path.exists():
            continue
        try:
            timeline = backend.read_json(path)
            sections = backend.read_json(root / 'plan.json')['sections']
            return [{'seconds': int(beat['start']), 'title': section['title']}
                    for beat, section in zip(timeline['beats'], sections)]
        except (ValueError, OSError, KeyError, TypeError):
            continue
    return []

def defaults(job, kind, channel):
    _, cfg = backend.load_channel(channel)
    original = original_description(job, kind)
    cached = destination(channel, job) / f'youtube_{kind}_metadata.json'
    plan_path = job_path(job) / ('short' if kind == 'short' else '') / 'plan.json'
    plan = {}
    try:
        plan = backend.read_json(plan_path)
    except (OSError, ValueError):
        try:
            plan = backend.read_json(job_path(job) / 'plan.json')
        except (OSError, ValueError):
            pass
    meta = {}
    if cached.exists():
        meta = backend.read_json(cached)
    title = meta.get('title') or (cfg['title_prefix'] + plan.get('title', assets(job, kind)[0].stem.replace('_', ' ')))[:100]
    words = re.findall(r'[A-Za-z][A-Za-z0-9-]{3,}', title + ' ' + original.split('\n\n')[0])
    stopwords = {'this', 'that', 'with', 'from', 'just', 'what', 'into', 'their', 'about', 'watch', 'full', 'more', 'breaks', 'down', 'credit'}
    tags, seen = [], set()
    for tag in cfg['default_tags'] + meta.get('tags', []) + words:
        if tag.casefold() not in seen and tag.casefold() not in stopwords:
            tags.append(tag)
            seen.add(tag.casefold())
        if len(tags) == 15:
            break
    description, link_state = meta.get('description', original), 'none'
    if kind == 'short':
        description, link_state = link_short(job, channel, description)
    altered, altered_why = ai_content(job)
    return dict(job=job, kind=kind, channel=channel.lower(), title=title, long_link=link_state,
                altered_content=altered, altered_why=altered_why,
                description=description, tags=tags,
                category=cfg['default_category'], visibility='Private', made_for_kids=False,
                language='English', chapters=job_chapters(job, kind),
                thumbnail='generated' if assets(job, kind)[1] else '', link_target='')

def ffmpeg():
    found = shutil.which('ffmpeg')
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def probe(video):
    found = shutil.which('ffprobe')
    if found:
        out = subprocess.run([found, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(video)],
                             capture_output=True, text=True, timeout=20, check=True)
        info = json.loads(out.stdout)
        stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
        return dict(duration=float(info['format']['duration']), width=stream['width'], height=stream['height'], fps=stream['r_frame_rate'])
    out = subprocess.run([ffmpeg(), '-hide_banner', '-i', str(video)], capture_output=True, text=True, timeout=20)
    duration = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', out.stderr)
    dimensions = re.search(r'Video:.*?\b(\d{2,5})x(\d{2,5})\b.*?([\d.]+) fps', out.stderr)
    return dict(duration=sum(float(x) * mul for x, mul in zip(duration.groups(), [3600, 60, 1])) if duration else 0,
                width=int(dimensions[1]) if dimensions else 0, height=int(dimensions[2]) if dimensions else 0,
                fps=dimensions[3] if dimensions else '?')

def thumbnail_path(data):
    value = data.get('thumbnail')
    if value == 'generated':
        path = assets(data['job'], data['kind'])[1]
    else:
        path = destination(data['channel'], data['job']) / 'thumbnails' / Path(value or '').name
    if not path or not path.is_file():
        raise ValueError('Select or create a thumbnail first.')
    return path

def finalize(data):
    data = dict(data)
    identifier(data['job'])
    data['channel'], _ = backend.load_channel(data['channel'])
    assets(data['job'], data['kind'])
    if data['kind'] == 'short':
        data['description'], data['long_link'] = link_short(data['job'], data['channel'], data.get('description', ''), data.get('long_url'))
        if data['long_link'] == 'needs_long':
            raise ValueError('This Short links to its explainer, which is not published yet. Publish the explainer first, '
                             'or use Publish both (explainer first, then the Short with the explainer link).')
    if not data.get('title', '').strip() or len(data['title']) > 100:
        raise ValueError('Title must be 1–100 characters.')
    if not data.get('description', '').strip() or len(data['description']) > 5000:
        raise ValueError('Description must be 1–5000 characters.')
    if any(c in data['title'] + data['description'] for c in '<>'):
        raise ValueError('YouTube metadata cannot contain angle brackets.')
    original = original_description(data['job'], data['kind'])
    # Preserve source and every attribution line, while allowing hook/chapter edits.
    lines = original.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith('Source:')), len(lines))
    credits = lines[start:] + [line for line in lines[:start] if re.match(r'^(Photo|Credit|Music|Footage):', line)]
    credits += re.findall(r'Credit:\s*[^\r\n]+', original)
    for line in credits:
        if line.strip() and line not in data['description']:
            raise ValueError('Existing source/credits must remain intact: ' + line)
    tags = data.get('tags', [])
    if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() and ',' not in t for t in tags):
        raise ValueError('Tags must be nonempty strings without commas.')
    if len({t.casefold() for t in tags}) != len(tags) or sum(len(t) + (2 if ' ' in t else 0) for t in tags) + max(len(tags)-1, 0) > 500:
        raise ValueError('Tags must be unique and fit 500 characters.')
    if data.get('category') not in backend.CATEGORIES or data.get('visibility') not in ('Private', 'Unlisted', 'Public') or type(data.get('made_for_kids')) is not bool:
        raise ValueError('Invalid category, visibility, or audience.')
    # YouTube "Altered content": always Yes when the video contains AI-generated visuals, whatever the draft says
    detected, _ = ai_content(data['job'])
    data['altered_content'] = bool(data.get('altered_content')) or detected
    if data.get('language') not in ('English', 'Spanish', 'French', 'German', 'Arabic', 'Hindi', 'Urdu'):
        raise ValueError('Unsupported language.')
    chapters = data.get('chapters', []) if data['kind'] == 'long' else []
    if chapters:
        if len(chapters) < 3 or chapters[0]['seconds'] != 0 or any(
            type(c['seconds']) is not int or c['seconds'] < 0 or not c['title'].strip() or '\n' in c['title'] for c in chapters):
            raise ValueError('Chapters need at least 3 entries starting at 0:00.')
        if any(b['seconds'] - a['seconds'] < 10 for a, b in zip(chapters, chapters[1:])):
            raise ValueError('Chapters must be ordered and at least 10 seconds apart.')
        duration = probe(assets(data['job'], data['kind'])[0])['duration']
        if duration and chapters[-1]['seconds'] > duration - 10:
            raise ValueError('Last chapter must leave at least 10 seconds of video.')
    description = re.sub(r'(?m)^\d+:\d{2}(?::\d{2})?\s+[^\r\n]*\r?\n?', '', data['description']).rstrip()
    if chapters:
        description += '\n\n' + '\n'.join(f"{c['seconds']//60}:{c['seconds']%60:02} {c['title']}" for c in chapters)
    if len(description) > 5000:
        raise ValueError('Description plus chapters exceeds 5000 characters.')
    data.update(description=description, chapters=chapters)
    thumbnail_path(data)
    target = data.get('link_target')
    if target:
        choices = [r for r in records() if r['video_id'] == target]
        if len(choices) != 1 or (choices[0].get('job') == data['job'] and choices[0].get('kind') == data['kind'] and choices[0]['channel'] == data['channel']):
            raise ValueError('Select a published target other than this video.')
    return data
