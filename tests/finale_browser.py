"""Browser regression checks: pip install playwright; python tests/finale_browser.py.

Uses installed Chrome (no application dependencies or downloaded browser required).
Audio plays silently through Chrome's --mute-audio flag, not element.muted.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
URL = (ROOT / 'index.html').as_uri()
KEY = 'misos-bachelor-weekend-v1'
SEED = {'stages': [2, 2, 2, 2], 'riddleOpened': [True] * 4, 'activeActivity': 3}
ERRORS = []
DROP_TIME = 66.6
TWO_BARS = 8 * 60 / 130
PARTY_CUES = [DROP_TIME + TWO_BARS * index for index in range(5)]


def new_page(browser, *, reduced=False, fail=False, seed=SEED):
    context = browser.new_context(viewport={'width': 390, 'height': 844},
                                  reduced_motion='reduce' if reduced else 'no-preference')
    context.add_init_script("""
        if (!sessionStorage.getItem('test-seeded')) {
            localStorage.setItem('misos-bachelor-onboarding-v1', 'complete');
            localStorage.setItem('%s', JSON.stringify(%s));
            sessionStorage.setItem('test-seeded', 'yes');
        }
        window.playCalls = [];
        const originalPlay = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function() {
            window.playCalls.push({time: this.currentTime, gesture: navigator.userActivation.isActive});
            return %s ? Promise.reject(new Error('test playback failure')) : originalPlay.call(this);
        };
        const now = performance.now.bind(performance);
        window.clockOffset = 0;
        performance.now = () => now() + window.clockOffset;
    """ % (KEY, json.dumps(seed), str(fail).lower()))
    page = context.new_page()
    page.on('pageerror', lambda error: ERRORS.append(str(error)))
    page.goto(URL)
    return page


def start(page):
    page.locator('#activate-finale').click()
    assert page.locator('#finale-confirm').evaluate('(el) => el.open')
    page.locator('#confirm-finale').click()
    assert page.locator('#finale-screen').is_visible()
    assert state(page)['mode'] == 'emotion' and state(page)['text'] == 'Mišo,'
    assert not page.locator('#finale-exit').is_visible()
    assert not page.locator('#party-visuals').is_visible()


def mock_clock(page):
    page.evaluate("""() => {
        const audio = document.getElementById('finale-audio');
        audio.pause();
        window.mediaTime = 0;
        Object.defineProperty(audio, 'currentTime', {
            configurable: true, get: () => window.mediaTime, set: time => window.mediaTime = time
        });
    }""")


def seek(page, time):
    page.evaluate("""time => {
        window.mediaTime = time;
        document.getElementById('finale-audio').dispatchEvent(new Event('timeupdate'));
    }""", time)


def state(page):
    return page.evaluate("""() => ({
        mode: document.getElementById('finale-screen').dataset.mode,
        text: document.getElementById('finale-message').textContent,
        time: document.getElementById('finale-audio').currentTime,
        paused: document.getElementById('finale-audio').paused,
        calls: window.playCalls.length
    })""")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel=os.environ.get('BROWSER_CHANNEL', 'chrome'), headless=True, args=['--mute-audio'])
    page = new_page(browser)
    assert state(page)['calls'] == 0 and state(page)['paused'] and state(page)['time'] == 0
    page.reload()
    assert page.locator('#activate-finale').is_visible() and state(page)['calls'] == 0
    page.locator('#activate-finale').click()
    assert state(page)['calls'] == 0
    page.locator('#cancel-finale').click()
    start(page)
    page.wait_for_function("document.getElementById('finale-audio').currentTime > .1")
    assert page.evaluate('window.playCalls') == [{'time': 0, 'gesture': True}]
    page.evaluate("document.getElementById('confirm-finale').click()")
    assert state(page)['calls'] == 1
    page.locator('#finale-mute').click()
    before = state(page)['time']
    page.wait_for_function("time => document.getElementById('finale-audio').currentTime > time + .1", arg=before)
    assert page.locator('#finale-audio').evaluate('(a) => a.muted && !a.paused')
    page.locator('#finale-mute').click()
    assert state(page)['calls'] == 1
    # Real MP3 playback crosses the actual boundary; no synthetic media clock here.
    page.evaluate("document.getElementById('finale-audio').currentTime = 65.8")
    page.wait_for_function("document.getElementById('finale-screen').dataset.mode === 'party'")
    drop = state(page)
    assert DROP_TIME <= drop['time'] < DROP_TIME + .5 and not drop['paused'] and drop['calls'] == 1, drop
    print('PASS real audio, user gesture, no autoplay, mute, repeated clicks, drop:', drop['time'])

    # An interrupted finale requires a fresh gesture after refresh.
    page.reload()
    assert state(page)['calls'] == 0 and page.locator('#activate-finale').is_visible()
    start(page)
    mock_clock(page)
    cues = [(0, 'Mišo,'), (4, 'úlohy'), (10, 'Ale to'), (15, 'Dnes sú'),
            (21, 'Možno'), (28, 'Ale všetci'), (33, 'KVÔLI TEBE.'),
            (39, 'Dnes je'), (46, 'Tak si'), (50, 'Na všetky'),
            (58, 'Tak si túto noc'), (62, 'Sme radi'), (DROP_TIME - .001, 'Sme radi'), (PARTY_CUES[0], 'EMOCIONÁLNY'),
            (PARTY_CUES[1] - .001, 'EMOCIONÁLNY'), (PARTY_CUES[1], 'AKTIVUJEM'),
            (PARTY_CUES[2] - .001, 'AKTIVUJEM'), (PARTY_CUES[2], 'DEAKTIVUJEM BEZPEČNOSTNÉ PROTOKOLY...'),
            (PARTY_CUES[3] - .001, 'DEAKTIVUJEM'), (PARTY_CUES[3], 'SPÚŠŤAM KONTROLOVANÝ CHAOS...'),
            (PARTY_CUES[4] - .001, 'SPÚŠŤAM'), (PARTY_CUES[4], 'ČO SA STANE')]
    for time, text in cues:
        seek(page, time)
        result = state(page)
        assert result['text'].startswith(text), (time, result)
        assert result['mode'] == ('party' if time >= DROP_TIME else 'emotion')
        assert ('statement' in page.locator('#finale-message').get_attribute('class')) == (time >= PARTY_CUES[4])
        assert page.locator('#finale-label').is_visible() == (time < PARTY_CUES[4])
        assert page.locator('#finale-screen .party-status').count() == 0
    assert page.locator('.party-spark').count() == 0
    assert page.locator('#party-visuals').is_visible()
    decorations = page.locator('#party-visuals').evaluate("el => el.getAnimations({subtree: true}).map(a => a.animationName)")
    assert decorations.count('party-laser-sweep') == 6
    assert decorations.count('party-tunnel-flight') == 4
    assert decorations.count('party-meter') == 12
    transforms = []
    for time in [DROP_TIME + 8.2, DROP_TIME + 8.5]:
        seek(page, time)
        transforms.append(page.locator('#party-visuals').evaluate("el => ['.party-laser', '.party-tunnel', '.party-meter'].map(selector => getComputedStyle(el.querySelector(selector)).transform)"))
    assert all(first != second for first, second in zip(*transforms)), transforms
    print('PASS final statement replaces status cue; lasers, tunnel and meters animate with the audio')
    # Every beat has exactly one bright window, aligned to media time in both layers.
    # The first beat also uses this rhythm rather than a separate drop animation.
    for beat_index in [0, 1, 24, 100]:
        for phase, bright in [(.05, True), (.5, False), (.95, False)]:
            time = DROP_TIME + (beat_index + phase) * 60 / 130
            seek(page, time)
            lights = page.locator('#finale-screen').evaluate("""el => ({
                border: Number(getComputedStyle(el, '::before').opacity),
                background: Number(getComputedStyle(el, '::after').opacity),
                clocks: el.getAnimations({subtree: true}).filter(a => ['party-strobe', 'party-light'].includes(a.animationName))
                    .map(a => ({time: a.currentTime, state: a.playState}))
            })""")
            assert (lights['border'] > .9) == bright and (lights['background'] > .05) == bright, lights
            assert len(lights['clocks']) == 2
            assert all(abs(clock['time'] - (time - DROP_TIME) * 1000) < 1 and clock['state'] == 'paused' for clock in lights['clocks'])
    print('PASS exactly one flash per beat; both layers follow audio position, including the drop')
    # Resume rendering from the current position, without replaying missed cues.
    for time, expected in [(45, 'Dnes je'), (DROP_TIME + .3, 'EMOCIONÁLNY'), (76, 'DEAKTIVUJEM'), (80, 'SPÚŠŤAM'), (84, 'ČO SA STANE')]:
        page.evaluate("""time => {
            Object.defineProperty(document, 'hidden', {configurable: true, value: true});
            document.dispatchEvent(new Event('visibilitychange'));
            window.mediaTime = time;
            Object.defineProperty(document, 'hidden', {configurable: true, value: false});
            document.dispatchEvent(new Event('visibilitychange'));
        }""", time)
        assert state(page)['text'].startswith(expected)
    # Check long emotional blocks and the headline at narrow and landscape sizes.
    for width, height in [(320, 568), (390, 844), (844, 390), (1440, 900)]:
        page.set_viewport_size({'width': width, 'height': height})
        for time in [21, 43, 52, PARTY_CUES[2], PARTY_CUES[3], PARTY_CUES[4]]:
            seek(page, time)
            box = page.locator('#finale-message').bounding_box()
            assert box['x'] >= 0 and box['x'] + box['width'] <= width + 1, (width, time, box)
            assert box['y'] >= 0 and box['y'] + box['height'] <= height, (height, time, box)
            if os.environ.get('FINALE_SCREENSHOTS') and width == 390 and time in [43, PARTY_CUES[4]]:
                page.screenshot(path=str(Path(os.environ['FINALE_SCREENSHOTS']) / ('finale-%s.png' % time)), animations='disabled')
    page.set_viewport_size({'width': 390, 'height': 844})
    seek(page, 83.99)
    assert page.locator('#finale-screen').is_visible()
    seek(page, 84)
    assert page.locator('#finale-screen').is_visible()
    seek(page, 3600)
    assert page.locator('#finale-screen').is_visible()
    assert state(page)['text'].startswith('ČO SA STANE')
    assert page.locator('#finale-screen').evaluate("el => getComputedStyle(el, '::before').animationIterationCount") == 'infinite'
    for layer, animation in [('::before', 'party-strobe'), ('::after', 'party-light')]:
        style = page.locator('#finale-screen').evaluate("(el, layer) => { const css = getComputedStyle(el, layer); return { name: css.animationName, duration: parseFloat(css.animationDuration), timing: css.animationTimingFunction }; }", layer)
        assert style['name'] == animation and abs(style['duration'] - 60 / 130) < .000001
        assert style['timing'] == 'steps(1)'
    page.locator('#finale-exit').click()
    assert page.locator('#completed-dashboard').is_visible()
    assert not page.locator('#finale-screen').is_visible()
    assert page.locator('#party-visuals').evaluate('el => el.getAnimations({subtree: true}).length') == 0
    saved = page.evaluate("key => JSON.parse(localStorage.getItem(key))", KEY)
    assert saved['finaleActivated'] and saved['finaleCompleted']
    page.reload()
    assert state(page)['calls'] == 0 and page.locator('#completed-dashboard').is_visible()
    assert not page.locator('#activate-finale').is_visible()
    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('#reset-game').click()
    assert page.locator('.cold-open').is_visible()
    assert page.evaluate('key => localStorage.getItem(key)', KEY) is None
    assert page.locator('#finale-audio').evaluate('(a) => a.paused && a.currentTime === 0 && !a.muted && a.volume === 1')
    print('PASS immediate emotional opening, all cues, visibility catch-up, layout, persistent party, manual exit and reset')

    reduced = new_page(browser, reduced=True)
    start(reduced)
    mock_clock(reduced)
    seek(reduced, DROP_TIME)
    assert reduced.locator('.party-spark').count() == 0
    assert reduced.locator('#finale-screen').evaluate("el => getComputedStyle(el, '::before').animationName") == 'none'
    assert reduced.locator('#finale-screen').evaluate("el => getComputedStyle(el, '::after').display") == 'none'
    assert not reduced.locator('#party-visuals').is_visible()
    assert reduced.locator('#party-visuals').evaluate('el => el.getAnimations({subtree: true}).length') == 0
    assert 'drop-impact' not in reduced.locator('#finale-screen').get_attribute('class')
    reduced.on('dialog', lambda dialog: dialog.accept())
    reduced.locator('#finale-reset').click()
    assert reduced.locator('.cold-open').is_visible()
    assert reduced.locator('#finale-audio').evaluate('(a) => a.paused && a.currentTime === 0')
    print('PASS reduced motion and reset during cinematic')

    continuing = new_page(browser)
    start(continuing)
    continuing.wait_for_function("document.getElementById('finale-audio').currentTime > .1")
    continuing.evaluate("document.getElementById('finale-audio').currentTime = 83.8")
    continuing.wait_for_function("document.getElementById('finale-audio').currentTime >= 84")
    assert continuing.locator('#finale-screen').is_visible()
    continuing.locator('#finale-exit').click()
    continuing.locator('#completed-dashboard').wait_for(state='visible')
    assert not state(continuing)['paused'] and state(continuing)['calls'] == 1
    before = state(continuing)['time']
    continuing.locator('#finale-mute').click()
    continuing.wait_for_function("time => document.getElementById('finale-audio').currentTime > time + .1", arg=before)
    continuing.on('dialog', lambda dialog: dialog.accept())
    continuing.locator('#reset-game').click()
    assert continuing.locator('#finale-audio').evaluate('(a) => a.paused && a.currentTime === 0 && !a.muted && a.volume === 1')
    print('PASS real audio continues after the party; completed dashboard mute and reset work')

    ended = new_page(browser)
    start(ended)
    ended.wait_for_function("document.getElementById('finale-audio').currentTime > .1")
    ended.evaluate("const a = document.getElementById('finale-audio'); a.currentTime = a.duration - .2")
    ended.wait_for_function("document.getElementById('finale-audio').ended")
    assert ended.locator('#finale-screen').is_visible() and state(ended)['mode'] == 'party'
    assert ended.locator('#finale-exit').is_visible()
    assert ended.locator('#finale-screen').evaluate("el => getComputedStyle(el, '::before').animationName") == 'party-strobe'
    ended.reload()
    assert ended.locator('#completed-dashboard').is_visible() and state(ended)['calls'] == 0
    print('PASS party keeps blinking after track ends; refresh remembers celebration without replay')

    failed = new_page(browser, fail=True)
    start(failed)
    failed.wait_for_function("document.getElementById('finale-controls').hidden")
    failed.evaluate('window.clockOffset = 45000')
    failed.wait_for_function("document.getElementById('finale-message').textContent.startsWith('Dnes je')")
    failed.evaluate('window.clockOffset = 66600')
    failed.wait_for_function("document.getElementById('finale-screen').dataset.mode === 'party'")
    failed.evaluate('window.clockOffset = 70500')
    failed.wait_for_function("document.getElementById('finale-message').textContent.startsWith('AKTIVUJEM')")
    failed.evaluate('window.clockOffset = 74000')
    failed.wait_for_function("document.getElementById('finale-message').textContent.startsWith('DEAKTIVUJEM')")
    failed.evaluate('window.clockOffset = 78000')
    failed.wait_for_function("document.getElementById('finale-message').textContent.startsWith('SPÚŠŤAM')")
    failed.evaluate('window.clockOffset = 84000')
    failed.wait_for_function("document.getElementById('finale-message').textContent.startsWith('ČO SA STANE')")
    assert failed.locator('#finale-screen').is_visible()
    failed.locator('#finale-exit').click()
    assert failed.locator('#completed-dashboard').is_visible()
    print('PASS playback failure fallback through persistent party and manual exit')

    # Run the actual fourth answer/reveal flow; only shorten its existing presentation timers.
    fourth = new_page(browser, seed={**SEED, 'stages': [2, 2, 2, 1]})
    assert not fourth.locator('#activate-finale').is_visible()
    fourth.evaluate("""() => {
        const schedule = window.setTimeout;
        window.setTimeout = (callback, delay) => schedule(callback, Math.min(delay, 30));
        window.revealOrder = [];
        new MutationObserver(() => {
            if (!document.getElementById('access-granted').hidden) window.revealOrder.push('reveal');
            if (!document.getElementById('completion').hidden) window.revealOrder.push('activation');
        }).observe(document.body, {subtree: true, attributes: true, attributeFilter: ['hidden']});
    }""")
    fourth.locator('#riddle-answer').fill('presypacie hodiny')
    fourth.locator('#answer-button').click()
    fourth.locator('#activate-finale').wait_for(state='visible')
    order = fourth.evaluate('window.revealOrder')
    assert order.index('reveal') < order.index('activation'), order
    assert fourth.locator('#destination-four').is_visible() and state(fourth)['calls'] == 0
    print('PASS Activity #4 reveal precedes activation; unlocking does not play audio')

    preview = new_page(browser, seed={**SEED, 'stages': [1, 0, 0, 0], 'activeActivity': 0})
    preview.evaluate("localStorage.removeItem('misos-bachelor-onboarding-v1')")
    saved_game = preview.evaluate('JSON.stringify(localStorage)')
    preview.goto(URL + '?preview=finale')
    assert preview.locator('#finale-preview-note').is_visible()
    assert preview.locator('#activate-finale').evaluate('(el) => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; }')
    assert preview.locator('.activity.unlocked').count() == 4
    assert state(preview)['calls'] == 0
    start(preview)
    preview.locator('#finale-preview-skip').click()
    preview.wait_for_function("document.getElementById('finale-screen').dataset.mode === 'party'")
    assert DROP_TIME <= state(preview)['time'] < DROP_TIME + 2 and state(preview)['calls'] == 1
    preview.locator('#finale-exit').click()
    assert preview.locator('#completed-dashboard').is_visible()
    assert preview.evaluate('JSON.stringify(localStorage)') == saved_game
    preview.locator('#reset-game').click()
    assert preview.locator('#activate-finale').is_visible()
    assert preview.locator('#finale-audio').evaluate('(a) => a.paused && a.currentTime === 0')
    start(preview)
    preview.locator('#finale-reset').click()
    assert preview.locator('#activate-finale').is_visible()
    assert preview.evaluate('JSON.stringify(localStorage)') == saved_game
    preview.reload()
    assert preview.locator('#activate-finale').is_visible() and state(preview)['calls'] == 0
    preview.locator('#exit-finale-preview').click()
    assert preview.locator('#welcome').is_visible()
    assert preview.evaluate('JSON.stringify(localStorage)') == saved_game
    print('PASS finale preview bypasses game/onboarding, jumps to drop, repeats and never changes saved progress')

    failed_preview = new_page(browser, fail=True)
    failed_preview.goto(URL + '?preview=finale')
    start(failed_preview)
    failed_preview.locator('#finale-preview-skip').click()
    assert state(failed_preview)['mode'] == 'party'
    print('PASS preview drop shortcut also works when audio fails')
    assert not ERRORS, ERRORS
    print('PASS no browser JavaScript errors')
    browser.close()
