"""Playwright-only Studio upload and linking, with bounded recovery and screenshots."""
import re
import time
import logging
from pathlib import Path
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
import youtube_publisher as backend

def last_fifteen_start(end_stamp):
    """Studio's MM:SS:frames clock; preserve the exact final frame."""
    match = re.fullmatch(r'(\d+):([0-5]\d):(\d{2})', end_stamp)
    if not match:
        raise ValueError('Unexpected Studio timecode: ' + end_stamp)
    minutes, seconds, frames = match.groups()
    end_seconds = int(minutes) * 60 + int(seconds)
    if end_seconds < 25:
        raise ValueError('End screens require a video at least 25 seconds long.')
    start = end_seconds - 15
    return f'{start//60:02}:{start%60:02}:{frames}'

def publish(data, video, thumbnail, cfg, channel_name, folder, emit, cancelled, mode='new'):
    state_path = folder.parents[1] / f"automation_{data['kind']}.json"
    state = backend.read_json(state_path) if state_path.exists() and mode != 'restart' else {}
    if mode == 'restart' and state_path.exists():
        backend.write_json(state_path.with_name(f'automation_{data["kind"]}_{int(time.time())}.json'), backend.read_json(state_path))
    state.update(channel=data['channel'], job=data['job'], kind=data['kind'])
    state.pop('error', None)
    sequence = 0
    with sync_playwright() as pw:
        args = ['--lang=en-US']
        if not cfg.get('playwright_headless', False) and cfg.get('offscreen_window', True):
            # a real Chrome window (YouTube Studio is reliable that way) parked off the screen, so nothing pops up
            args += ['--window-position=-32000,-32000', '--window-size=1440,1000']
        context = pw.chromium.launch_persistent_context(cfg['chrome_profile'], channel='chrome',
                    headless=cfg.get('playwright_headless', False), locale='en-US', args=args)
        page = context.new_page()
        page.set_default_timeout(20000)
        def checkpoint(message):
            nonlocal sequence
            if cancelled():
                raise RuntimeError('Publish cancelled. Any existing draft is preserved for recovery.')
            sequence += 1
            name = f'{sequence:04}.png'
            try:
                page.screenshot(path=str(folder / name), full_page=True, timeout=10000)
                emit(message, name)
            except Exception:
                emit(message)
        def action(message, function):
            checkpoint('Before: ' + message)
            result = function()
            checkpoint(message)
            return result
        def click(locator, message):
            return action(message, locator.click)
        def fill(locator, value, message):
            return action(message, lambda: locator.fill(value))
        def dismiss_editor_intro():
            try:
                start = page.get_by_role('button', name='Get started', exact=True)
                start.wait_for(timeout=5000)
                click(start, 'Completing Editor introduction...')
            except PlaywrightTimeoutError:
                pass
        def remember():
            backend.write_json(state_path, state)
        def capture_id(scope):
            links = scope.locator('a[href*="youtu.be/"], a[href*="youtube.com/watch?v="], a[href*="/video/"], a[href*="/shorts/"]')
            for link in links.all():
                href = link.get_attribute('href') or ''
                match = re.search(r'(?:youtu\.be/|[?&]v=|/video/|/shorts/)([\w-]{11})', href)
                if match:
                    state.update(video_id=match[1], url=f'https://www.youtube.com/watch?v={match[1]}')
                    remember()
                    return
            match = re.search(r'https://(?:youtu\.be/|(?:www\.)?youtube\.com/(?:watch\?v=|shorts/))([\w-]{11})', scope.inner_text())
            if match:
                state.update(video_id=match[1], url=f'https://www.youtube.com/watch?v={match[1]}')
                remember()
        def fill_details(scope):
            fill(scope.locator('#title-textarea #textbox'), data['title'], 'Filling title...')
            fill(scope.locator('#description-textarea #textbox'), data['description'], 'Filling description and chapters...')
            if data['kind'] == 'long':
                action('Uploading thumbnail...', lambda: scope.locator('ytcp-thumbnail-uploader input[type=file]').set_input_files(str(thumbnail)))
                try:
                    expect(scope.locator('ytcp-thumbnail-uploader').get_by_role('button', name='Uploaded thumbnail', exact=True)).to_be_visible(timeout=15000)
                except AssertionError as error:
                    raise RuntimeError('YouTube did not accept the custom thumbnail. Open Upload file in Studio and check whether this channel requires phone verification. The existing upload is preserved; do not create another copy.') from error
            else:
                emit('YouTube Shorts uses a video frame thumbnail; custom image upload is unavailable in desktop Studio.')
            audience = 'VIDEO_MADE_FOR_KIDS_MFK' if data['made_for_kids'] else 'VIDEO_MADE_FOR_KIDS_NOT_MFK'
            click(scope.locator(f'tp-yt-paper-radio-button[name="{audience}"]'), 'Setting made-for-kids...')
            more = scope.get_by_text('Show more', exact=True)
            if more.count() and more.is_visible():
                click(more, 'Opening additional fields...')
            tags = scope.locator('#tags-container input')
            chips = scope.locator('#tags-container ytcp-chip')
            for chip in chips.all():
                remove = chip.locator('#remove-icon, [aria-label*="Remove"], yt-icon').last
                if remove.count():
                    click(remove, 'Removing previous tag...')
            for tag in data['tags']:
                fill(tags, tag, 'Adding tag: ' + tag)
                action('Confirming tag...', lambda: tags.press('Enter'))
            click(scope.locator('#category'), 'Setting category...')
            click(page.get_by_role('option', name=data['category'], exact=True), 'Selecting category...')
            language = scope.locator('#language-input')
            click(language, 'Setting language...')
            click(page.get_by_role('option', name=data['language'], exact=True), 'Selecting language...')
            set_altered(scope)
            expect(scope.locator('#title-textarea #textbox')).to_have_text(data['title'])
            expect(scope.locator('#description-textarea #textbox')).to_have_text(data['description'])
            expect(scope.locator('#tags-container ytcp-chip')).to_have_count(len(data['tags']))
            expect(scope.locator('#category')).to_contain_text(data['category'])
            expect(scope.locator('#language-input')).to_contain_text(data['language'])
            expect(scope.locator(f'tp-yt-paper-radio-button[name="{audience}"]')).to_have_attribute('aria-checked', 'true')
        def set_altered(scope):
            """YouTube's "Altered content" question: Yes when the video has AI-generated visuals (Gemini / Flow), else No.
            The answer is never skipped: if the control can't be found, the publish stops with a clear error."""
            want = 'YES' if data.get('altered_content') else 'NO'
            radio = scope.locator(f'tp-yt-paper-radio-button[name="VIDEO_HAS_ALTERED_CONTENT_{want}"]')
            if not radio.count():   # fallback: the Yes / No radio inside the section headed "Altered content"
                section = scope.locator('xpath=//*[normalize-space(text())="Altered content"]/ancestor::*[.//tp-yt-paper-radio-button][1]')
                radio = section.locator('tp-yt-paper-radio-button').filter(
                    has_text=re.compile(r'^\s*' + ('Yes' if want == 'YES' else 'No') + r'\b', re.I))
            if not radio.count():
                raise RuntimeError('YouTube Studio\'s "Altered content" question was not found (the page may have changed). '
                                   'The upload draft is preserved; answer it in Studio or retry after a selector fix.')
            action('Scrolling to Altered content...', lambda: radio.first.scroll_into_view_if_needed())
            click(radio.first, f'Setting Altered content: {"Yes (AI-generated visuals)" if want == "YES" else "No"}...')
            expect(radio.first).to_have_attribute('aria-checked', 'true')
        def finish_dialog(dialog, wait_transfer=True):
            for step in ('Video elements', 'Checks', 'Visibility'):
                click(dialog.locator('#next-button'), 'Continuing to ' + step + '...')
            visibility = dialog.locator(f'tp-yt-paper-radio-button[name="{data["visibility"].upper()}"]')
            click(visibility, 'Setting visibility...')
            expect(visibility).to_have_attribute('aria-checked', 'true')
            emit('Waiting for video transfer and processing...')
            if mode != 'resume' and wait_transfer:
                deadline = time.monotonic() + cfg.get('upload_timeout_seconds', 600)
                last_report = 0
                while True:
                    if cancelled():
                        raise RuntimeError('Publish cancelled; the existing upload draft is preserved.')
                    text = dialog.inner_text()
                    # done only when the file itself is up: "Checks complete" can show while it is still uploading
                    if re.search('Upload complete', text, re.I) and not re.search(r'Uploading\s+\d+\s*%', text, re.I):
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Video transfer did not finish before the configured timeout. Retry the existing draft.')
                    if time.monotonic() - last_report > 20:
                        checkpoint('Waiting for YouTube to finish the transfer...')
                        last_report = time.monotonic()
                    page.wait_for_timeout(1000)
            else:
                checkpoint('Existing video ID recovered; finishing its saved draft without re-uploading the file.')
            capture_id(dialog)
            id_deadline = time.monotonic() + 60
            while not state.get('video_id') and time.monotonic() < id_deadline:
                if cancelled():
                    raise RuntimeError('Publish cancelled; existing upload draft is preserved.')
                page.wait_for_timeout(1000)
                capture_id(dialog)
            if not state.get('video_id'):
                raise RuntimeError('YouTube has not provided a video ID. Recover the existing draft before retrying.')
            click(dialog.locator('#done-button'), 'Finalizing upload...')
            expect(dialog.locator('#title-textarea #textbox')).to_be_hidden(timeout=60000)
            state['finalized'] = True
            remember()
            action('Verifying video details...', lambda: page.goto(f'https://studio.youtube.com/video/{state["video_id"]}/edit', wait_until='domcontentloaded'))
        def reopen_if_draft():
            """YouTube sometimes keeps a just-finished upload as a draft without its details (filename as title). Put the
            details in again on the same video instead of waiting for a visibility that will never come."""
            for attempt in range(2):
                page.wait_for_timeout(5000)
                edit_draft = page.get_by_role('button', name='Edit draft', exact=True)
                if not (edit_draft.count() and edit_draft.is_visible()):
                    return
                checkpoint(f'YouTube kept the upload as a draft without its details; filling them in again ({attempt + 1}/2)...')
                click(edit_draft, 'Reopening the draft...')
                dialog = page.locator('ytcp-uploads-dialog')
                expect(dialog.locator('#title-textarea #textbox')).to_be_visible(timeout=30000)
                fill_details(dialog)
                finish_dialog(dialog, wait_transfer=False)   # the file is already on YouTube

        def wait_for_visibility():
            deadline = time.monotonic() + cfg.get('upload_timeout_seconds', 600)
            next_report = 0
            while time.monotonic() < deadline:
                if cancelled():
                    raise RuntimeError('Verification cancelled. The existing upload is preserved.')
                visibility = page.locator('ytcp-video-metadata-visibility')
                if visibility.count() and data['visibility'] in visibility.inner_text(timeout=5000):
                    expect(page.get_by_role('button', name='Edit draft', exact=True)).to_be_hidden()
                    return
                info = page.locator('ytcp-video-info')
                if info.count() and re.search('processing (failed|abandoned)|upload failed|rejected', info.inner_text(timeout=5000), re.I):
                    raise RuntimeError('YouTube could not process this upload. Inspect ' + page.url)
                if time.monotonic() >= next_report:
                    checkpoint('Waiting for YouTube processing and persisted ' + data['visibility'] + ' visibility...')
                    next_report = time.monotonic() + 20
                page.wait_for_timeout(1500)
            raise RuntimeError('YouTube visibility is still pending after the configured processing timeout. Retry this existing video; do not upload another copy.')
        try:
            action('Navigating to YouTube Studio...', lambda: page.goto('https://studio.youtube.com/', wait_until='domcontentloaded'))
            click(page.locator('ytcp-app #avatar-btn'), 'Opening channel switcher...')
            click(page.get_by_text('Switch account', exact=True), 'Switching to ' + channel_name + ' channel...')
            entries = page.locator('ytd-account-item-renderer').filter(has=page.get_by_text(channel_name, exact=True))
            expect(entries).to_have_count(1)
            click(entries, 'Selecting ' + channel_name + '...')
            expect(page.locator('ytcp-navigation-drawer #entity-name')).to_have_text(channel_name, timeout=60000)
            checkpoint('Channel verified: ' + channel_name)
            if mode == 'resume' and not state.get('video_id') and state.get('submitted'):
                action('Finding existing upload...', lambda: page.goto('https://studio.youtube.com/', wait_until='domcontentloaded'))
                click(page.get_by_role('menuitem', name='Content', exact=True), 'Opening channel content...')
                if data['kind'] == 'short':
                    click(page.get_by_role('tab', name='Shorts', exact=True), 'Finding existing Short...')
                # Studio may retain the filename if metadata autosave was interrupted.
                titles = re.compile('^(?:' + re.escape(data['title']) + '|' + re.escape(video.stem.replace('_', ' ')) + ')$')
                rows = page.locator('ytcp-video-row').filter(has=page.get_by_text(titles))
                expect(rows).to_have_count(1)
                capture_id(rows)
                if not state.get('video_id'):
                    click(rows.get_by_role('button', name='Edit draft', exact=True), 'Identifying existing upload draft...')
                    dialog = page.locator('ytcp-uploads-dialog')
                    expect(dialog.locator('#title-textarea #textbox')).to_be_visible(timeout=60000)
                    capture_id(dialog)
                if not state.get('video_id'):
                    raise RuntimeError('Cannot safely identify the prior upload. Check Studio manually before restarting.')
            if state.get('video_id'):
                action('Recovering existing video...', lambda: page.goto(f'https://studio.youtube.com/video/{state["video_id"]}/edit', wait_until='domcontentloaded'))
                if not state.get('saved'):
                    edit_draft = page.get_by_role('button', name='Edit draft', exact=True)
                    expect(page.locator('#title-textarea #textbox')).to_be_visible(timeout=60000)
                    if edit_draft.count() and edit_draft.is_visible():
                        click(edit_draft, 'Resuming existing upload draft...')
                        dialog = page.locator('ytcp-uploads-dialog')
                        expect(dialog.locator('#title-textarea #textbox')).to_be_visible(timeout=30000)
                        fill_details(dialog)
                        finish_dialog(dialog)
                    else:
                        # A saved video can remain Pending while YouTube processes it.
                        # Retry must wait for that same ID, not rewrite or re-upload it.
                        expect(page.locator('#title-textarea #textbox')).to_have_text(data['title'])
                        state['finalized'] = True
                        remember()
                        checkpoint('Recovered finalized upload; waiting for YouTube to finish processing it.')
            else:
                click(page.get_by_role('button', name='Create', exact=True), 'Opening upload menu...')
                click(page.get_by_role('menuitem', name='Upload videos', exact=True), 'Opening upload dialog...')
                dialog = page.locator('ytcp-uploads-dialog')
                expect(page.get_by_role('button', name='Select files', exact=True)).to_be_visible(timeout=20000)
                state['submitted'] = True
                remember()
                action('Uploading video file...', lambda: dialog.locator('input[type=file]').first.set_input_files(str(video)))
                expect(dialog.locator('#title-textarea #textbox')).to_be_visible(timeout=60000)
                capture_id(dialog)
                fill_details(dialog)
                finish_dialog(dialog)
            reopen_if_draft()
            wait_for_visibility()
            state['saved'] = True
            remember()
            link_error = None
            target = data.get('link_target')
            if target:
                try:
                    if data['kind'] == 'short':
                        click(page.get_by_text('Related video', exact=True), 'Opening Related video...')
                        picker = page.locator('ytcp-video-picker')
                        fill(picker.locator('input').first, f'https://www.youtube.com/watch?v={target}', 'Searching related video...')
                        item = picker.locator(f'[video-id="{target}"], a[href*="{target}"]').first
                        click(item, 'Selecting related video...')
                        click(page.get_by_role('button', name='Save', exact=True), 'Saving Related video...')
                    else:
                        action('Opening end-screen editor...', lambda: page.goto(f'https://studio.youtube.com/video/{state["video_id"]}/editor', wait_until='domcontentloaded'))
                        dismiss_editor_intro()
                        from publisher_logic import records
                        target_record = next(r for r in records() if r['video_id'] == target)
                        target_title = target_record['title']
                        if state.get('link_saved_target') != target:
                            click(page.get_by_role('button', name='Add end screens', exact=True), 'Opening end-screen elements...')
                            click(page.get_by_role('dialog').get_by_text('Video', exact=True), 'Adding video element...')
                            click(page.get_by_text('Choose specific video', exact=True), 'Choosing target video...')
                            picker = page.get_by_role('dialog', name='Choose specific video')
                            if target_record['channel'] == data['channel']:
                                fill(picker.get_by_placeholder('Search your videos'), target_title, 'Searching end-screen video...')
                            else:
                                search = picker.get_by_placeholder('Search videos from other channels')
                                fill(search, f'https://www.youtube.com/watch?v={target}', 'Finding published source video by URL...')
                                action('Searching external video...', lambda: search.press('Enter'))
                            card = picker.locator('ytcp-entity-card').filter(has=page.locator(f'.thumbnail[style*="/{target}/"]'))
                            expect(card).to_have_count(1)
                            click(card, 'Selecting target verified by video ID...')
                            if page.get_by_text(re.compile('This video is private.*replaced', re.S)).is_visible():
                                raise ValueError('YouTube requires the fixed end-screen target to be Public or Unlisted.')
                            times = page.locator('ytve-formatted-input input')
                            expect(times).to_have_count(2)
                            end_stamp = times.nth(1).input_value()
                            start_stamp = last_fifteen_start(end_stamp)
                            fill(times.first, start_stamp, 'Setting last-15-seconds timing...')
                            action('Confirming end-screen timing...', lambda: times.first.press('Tab'))
                            expect(times.first).to_have_value(start_stamp)
                            preview = page.locator('ytve-endscreen-editor-preview-overlay')
                            element = page.locator('ytve-endscreen-editor-preview-overlay-item:visible')
                            expect(element).to_have_count(1)
                            rect, item = preview.bounding_box(), element.bounding_box()
                            if not rect or not item:
                                raise RuntimeError('End-screen preview position unavailable.')
                            action('Positioning element top-right...', lambda: element.locator('.edit-overlay').drag_to(preview,
                                target_position={'x': rect['width']-item['width']/2-12, 'y': item['height']/2+12}))
                            moved = element.bounding_box()
                            if moved['x'] < rect['x']+rect['width']/2 or moved['y'] > rect['y']+rect['height']/2:
                                raise RuntimeError('End-screen element did not move to the top-right.')
                            click(page.get_by_role('button', name='Save', exact=True), 'Saving end screen...')
                            state.update(link_saved_target=target, end_screen_start=start_stamp, end_screen_end=end_stamp)
                            remember()
                            page.wait_for_timeout(1500)
                        action('Verifying saved end screen...', lambda: page.reload(wait_until='domcontentloaded'))
                        dismiss_editor_intro()
                        # Reload the editor, reopen the existing element, and verify persisted values.
                        expect(page.get_by_text('End screen', exact=True).first).to_be_visible(timeout=30000)
                        click(page.get_by_text('End screen', exact=True).first, 'Inspecting saved end-screen settings...')
                        times = page.locator('ytve-formatted-input input')
                        expect(times).to_have_count(2)
                        expect(times.first).to_have_value(state['end_screen_start'])
                        expect(times.nth(1)).to_have_value(state['end_screen_end'])
                        selected_target = page.locator('ytve-endscreen-editor-video-element-options').get_by_text('Video: ' + target_title, exact=True)
                        selected_target.scroll_into_view_if_needed()
                        expect(selected_target).to_be_visible()
                        preview = page.locator('ytve-endscreen-editor-preview-overlay').bounding_box()
                        element = page.locator('ytve-endscreen-editor-preview-overlay-item:visible').bounding_box()
                        if not preview or not element or element['x'] < preview['x']+preview['width']/2 or element['y'] > preview['y']+preview['height']/2:
                            raise RuntimeError('Saved end-screen position could not be verified as top-right.')
                        checkpoint('Verified saved end screen: correct target, last 15 seconds, top-right.')
                    if data['kind'] == 'short':
                        action('Verifying saved link...', lambda: page.reload(wait_until='domcontentloaded'))
                        expect(page.locator(f'[video-id="{target}"], a[href*="{target}"]').first).to_be_attached(timeout=20000)
                    state['related_video_id'] = target
                    remember()
                except Exception as error:
                    logging.exception('Post-upload linking failed')
                    link_error = f'Automatic linking failed. Set it manually at https://studio.youtube.com/video/{state["video_id"]}/' + ('edit' if data['kind'] == 'short' else 'editor') + '. ' + str(error).splitlines()[0]
                    checkpoint(link_error)
            try:
                action('Opening uploaded video for verification...', lambda: page.goto(state['url'], wait_until='domcontentloaded'))
                checkpoint('Uploaded video page captured for verification.')
            except Exception as error:
                checkpoint('Video is saved; watch-page verification was unavailable: ' + str(error))
            return dict(video_id=state['video_id'], url=state['url'],
                        related_video_id=state.get('related_video_id'), link_error=link_error)
        except Exception as error:
            if state.get('submitted') and not state.get('video_id'):
                try:
                    capture_id(page.locator('ytcp-uploads-dialog'))
                except Exception:
                    pass
            if state.get('submitted') and not state.get('saved') and not cancelled() and mode == 'new':
                # A metadata-selector failure must not abort the in-flight MP4.
                # Give the transfer a bounded chance to finish so Retry can recover its ID.
                emit('Preserving the existing upload while its file transfer finishes...')
                deadline = time.monotonic() + min(cfg.get('upload_timeout_seconds', 600), 120)
                while time.monotonic() < deadline and not cancelled():
                    try:
                        text = page.locator('ytcp-uploads-dialog').inner_text(timeout=3000)
                        if re.search('Upload complete|Checks complete', text, re.I):
                            break
                        page.wait_for_timeout(1000)
                    except Exception:
                        break
            state['error'] = str(error)
            remember()
            checkpoint('Upload failed: ' + str(error).splitlines()[0])
            raise
        finally:
            context.close()

def delete_video(cfg, channel_name, video_id, folder, emit, dry_run=False):
    """Delete a video from YouTube Studio, then verify that it is gone."""
    open_studio_url = 'https://studio.youtube.com/'
    edit_url_template = 'https://studio.youtube.com/video/{video_id}/edit'
    avatar_selector = 'ytcp-app #avatar-btn'
    switch_account_text = 'Switch account'
    entity_name_selector = 'ytcp-navigation-drawer #entity-name'
    options_button_role_name = 'Options'
    options_button_selector = 'button[aria-label="Options"]'
    delete_forever_text = 'Delete forever'
    understand_checkbox_text = 'I understand that deleting is permanent'
    final_delete_button_text = 'Delete'
    unavailable_texts = ('Video unavailable', 'This video has been removed')

    folder.mkdir(parents=True, exist_ok=True)
    sequence = 0

    def already_gone(page):
        if not page.url.startswith('https://studio.youtube.com/video/'):
            return True
        for text in unavailable_texts:
            if page.get_by_text(text, exact=False).count() > 0:
                return True
        return False

    with sync_playwright() as pw:
        args = ['--lang=en-US']
        if not cfg.get('playwright_headless', False) and cfg.get('offscreen_window', True):
            args += ['--window-position=-32000,-32000', '--window-size=1440,1000']
        context = pw.chromium.launch_persistent_context(
            cfg['chrome_profile'], channel='chrome',
            headless=cfg.get('playwright_headless', False), locale='en-US', args=args)
        page = context.new_page()
        page.set_default_timeout(20000)

        def checkpoint(message):
            nonlocal sequence
            sequence += 1
            safe = re.sub(r'[^A-Za-z0-9_.-]+', '_', message).strip('_')[:60] or 'step'
            shot = folder / f'{sequence:03d}_{safe}.png'
            page.screenshot(path=str(shot))
            emit(message, str(shot))

        def click(locator, message):
            locator.first.wait_for(state='visible', timeout=20000)
            locator.first.click()
            checkpoint(message)

        try:
            checkpoint('Navigating to YouTube Studio...')
            page.goto(open_studio_url, wait_until='domcontentloaded')
            click(page.locator(avatar_selector), 'Opening channel switcher...')
            click(page.get_by_text(switch_account_text, exact=True), 'Switching to ' + channel_name + ' channel...')
            entries = page.locator('ytd-account-item-renderer').filter(has=page.get_by_text(channel_name, exact=True))
            expect(entries).to_have_count(1)
            click(entries, 'Selecting ' + channel_name + '...')
            expect(page.locator(entity_name_selector)).to_have_text(channel_name, timeout=60000)
            checkpoint('Channel verified: ' + channel_name)

            edit_url = edit_url_template.format(video_id=video_id)
            checkpoint('Opening video edit page...')
            page.goto(edit_url, wait_until='domcontentloaded')
            page.wait_for_timeout(1500)

            if already_gone(page):
                checkpoint('Video already unavailable in Studio')
                return {'deleted': True, 'already_gone': True}

            options_button = page.get_by_role('button', name=options_button_role_name, exact=True)
            if options_button.count() == 0:
                options_button = page.locator(options_button_selector)
            click(options_button, 'Opening video options menu...')

            delete_item = page.get_by_text(delete_forever_text, exact=True)
            if delete_item.count() == 0:
                delete_item = page.get_by_role('menuitem', name=delete_forever_text, exact=True)
            click(delete_item, 'Choosing Delete forever...')

            checkbox = page.get_by_role('checkbox', name=understand_checkbox_text, exact=True)
            if checkbox.count() == 1:
                checkbox.check()
            else:
                checkbox_label = page.get_by_text(understand_checkbox_text, exact=True)
                if checkbox_label.count() == 0:
                    raise RuntimeError('Could not find the permanent deletion confirmation checkbox.')
                checkbox_label.first.click()
            checkpoint('Confirmed permanent deletion checkbox')

            if dry_run:
                checkpoint('Dry run: delete confirmation dialog shown')
                close_button = page.get_by_role('button', name='Close', exact=True)
                if close_button.count():
                    close_button.first.click()
                else:
                    page.keyboard.press('Escape')
                checkpoint('Dry run: closed delete confirmation dialog')
                return {'deleted': False, 'already_gone': False, 'dry_run': True}

            dialog = page.get_by_role('dialog')
            if dialog.count():
                confirm_button = dialog.last.get_by_role('button', name=final_delete_button_text, exact=True)
            else:
                confirm_button = page.get_by_role('button', name=final_delete_button_text, exact=True)
            if confirm_button.count() == 0:
                confirm_button = page.locator('ytcp-button').filter(has_text=final_delete_button_text).last
            checkpoint('Clicking final Delete button...')
            confirm_button.click()

            page.wait_for_timeout(3000)
            checkpoint('Delete submitted; verifying the edit page no longer shows it...')
            page.goto(edit_url, wait_until='domcontentloaded')
            if already_gone(page):
                checkpoint('Verified video is gone')
                return {'deleted': True, 'already_gone': False}
            raise RuntimeError('Delete verification failed: Studio still shows the video.')
        except Exception as error:
            checkpoint('Delete failed: ' + str(error).splitlines()[0])
            raise
        finally:
            context.close()
