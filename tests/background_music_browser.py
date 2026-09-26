"""Run with Playwright installed; BROWSER_CHANNEL=msedge selects installed Edge."""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL = (Path(__file__).resolve().parents[1] / 'index.html').as_uri()
KEY = 'misos-bachelor-weekend-v1'
STARTED = 'misos-bachelor-music-started-v1'
MUTED = 'misos-bachelor-music-muted-v1'
ERRORS = []


def new_page(browser, *, onboarded=False, saved=None, muted=False, blocked=False, storage_denied=False):
    context = browser.new_context(viewport={'width': 390, 'height': 844}, reduced_motion='reduce')
    context.add_init_script("""
        if (!sessionStorage.getItem('seeded')) {
            localStorage.clear();
            localStorage.setItem('misos-bachelor-cold-open-v1', 'complete');
            if (%s) localStorage.setItem('misos-bachelor-onboarding-v1', 'complete');
            if (%s) localStorage.setItem('%s', JSON.stringify(%s));
            localStorage.setItem('%s', String(%s));
            sessionStorage.setItem('seeded', 'yes');
        }
        window.audioCalls = [];
        window.overlaps = [];
        window.fadeVolumes = [];
        const play = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function() {
            const other = document.getElementById(this.id === 'main-audio' ? 'finale-audio' : 'main-audio');
            audioCalls.push({id: this.id, time: this.currentTime, gesture: navigator.userActivation.isActive});
            if (other && !other.paused) overlaps.push(this.id);
            if (this.id === 'main-audio' && %s && !navigator.userActivation.isActive) {
                return Promise.reject(new DOMException('Autoplay blocked', 'NotAllowedError'));
            }
            return play.call(this);
        };
        if (%s) {
            Storage.prototype.getItem = () => { throw new Error('Storage unavailable'); };
            Storage.prototype.setItem = () => { throw new Error('Storage unavailable'); };
            Storage.prototype.removeItem = () => { throw new Error('Storage unavailable'); };
        }
    """ % (json.dumps(onboarded), json.dumps(saved is not None), KEY, json.dumps(saved), MUTED,
           json.dumps(muted), json.dumps(blocked), json.dumps(storage_denied)))
    page = context.new_page()
    page.on('pageerror', lambda error: ERRORS.append(str(error)))
    if storage_denied:
        page.clock.install()
    page.goto(URL)
    return page


def main_playing(page):
    page.wait_for_function("!document.getElementById('main-audio').paused && document.getElementById('main-audio').currentTime > 0")


def main_calls(page):
    return page.evaluate("audioCalls.filter(call => call.id === 'main-audio')")


with sync_playwright() as p:
    browser = p.chromium.launch(channel=os.environ.get('BROWSER_CHANNEL', 'chrome'), headless=True,
                                args=['--mute-audio', '--autoplay-policy=no-user-gesture-required'])
    fresh = new_page(browser)
    assert not main_calls(fresh)
    fresh.locator('#welcome-heading').click()
    assert not main_calls(fresh)
    fresh.locator('#start-weekend').click()
    main_playing(fresh)
    assert main_calls(fresh)[0]['gesture']
    assert fresh.evaluate('key => localStorage.getItem(key)', STARTED) == 'true'
    assert fresh.locator('#main-audio').evaluate('a => a.loop')
    expect(fresh.locator('#music-mute')).to_be_visible()
    fresh.reload()  # Starting is persisted even before the loading sequence completes.
    main_playing(fresh)
    before = fresh.locator('#main-audio').evaluate('a => a.currentTime')
    calls = len(main_calls(fresh))
    fresh.locator('#music-mute').click()
    expect(fresh.locator('#music-mute')).to_have_attribute('aria-pressed', 'true')
    fresh.wait_for_function('time => document.getElementById("main-audio").currentTime > time + .1', arg=before)
    assert fresh.locator('#main-audio').evaluate('a => a.muted && !a.paused')
    assert len(main_calls(fresh)) == calls
    fresh.reload()
    main_playing(fresh)
    assert fresh.locator('#main-audio').evaluate('a => a.muted')
    fresh.locator('#music-mute').click()
    assert fresh.evaluate('key => localStorage.getItem(key)', MUTED) == 'false'
    # Exercise the real media loop without waiting for the whole song.
    fresh.locator('#main-audio').evaluate('a => { a.currentTime = a.duration - .15; }')
    fresh.wait_for_function('document.getElementById("main-audio").currentTime < 2')
    main_playing(fresh)
    print('PASS start gesture, boot/reload playback, continuous mute/unmute, saved preference and real looping')

    denied = new_page(browser, onboarded=True, blocked=True)
    assert main_calls(denied)
    assert denied.locator('#main-audio').evaluate('a => a.paused')
    denied.locator('#page h1').click()
    main_playing(denied)
    denied.locator('#main-audio').evaluate('a => a.pause()')
    denied.evaluate("window.dispatchEvent(new Event('pageshow'))")
    main_playing(denied)
    denied.locator('#main-audio').evaluate('a => a.pause()')
    denied.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    main_playing(denied)
    print('PASS blocked autoplay silently retries on interaction and returning to the app')

    seed = {'stages': [2] * 4, 'activeActivity': 1, 'riddleOpened': [True] * 4}
    finale = new_page(browser, onboarded=True, saved=seed)
    main_playing(finale)
    expect(finale.locator('#destination-two-heading')).to_have_text('SUNSET BOAT TOUR')
    finale.evaluate("document.getElementById('main-audio').addEventListener('volumechange', e => fadeVolumes.push(e.target.volume))")
    finale.locator('#activate-finale').click()
    expect(finale.locator('#confirm-finale')).to_be_enabled()
    assert finale.locator('#main-audio').evaluate('a => a.paused')
    assert finale.evaluate('fadeVolumes.some(volume => volume > 0 && volume < 1)')
    position = finale.locator('#main-audio').evaluate('a => a.currentTime')
    finale.locator('#cancel-finale').click()
    main_playing(finale)
    assert finale.locator('#main-audio').evaluate('a => a.currentTime') >= position
    finale.locator('#activate-finale').click()
    finale.keyboard.press('Escape')
    main_playing(finale)
    finale.locator('#activate-finale').click()
    finale.locator('#confirm-finale').click()
    finale.wait_for_function('document.getElementById("finale-audio").currentTime > .1')
    assert finale.locator('#main-audio').evaluate('a => a.paused')
    expect(finale.locator('#music-controls')).to_be_hidden()
    assert not finale.evaluate('overlaps')
    assert finale.evaluate("audioCalls.filter(call => call.id === 'finale-audio')[0].gesture")
    finale.locator('#finale-mute').click()
    assert finale.locator('#finale-audio').evaluate('a => a.muted && !a.paused')
    assert not finale.locator('#main-audio').evaluate('a => a.muted')
    finale.locator('#finale-audio').evaluate('a => { a.currentTime = 82; }')
    expect(finale.locator('#finale-message')).to_contain_text('ČO SA STANE')
    finale.locator('#finale-exit').click()
    finale.locator('#page h1').click()
    assert finale.locator('#main-audio').evaluate('a => a.paused')
    assert not finale.evaluate('overlaps')
    finale.reload()
    finale.locator('#page h1').click()
    assert not main_calls(finale)
    expect(finale.locator('#music-controls')).to_be_hidden()
    print('PASS fade/cancel, no track overlap, finale gesture/mute unchanged and completed dashboard stays blocked')

    for flags in [{'finaleActivated': True}, {'finaleCompleted': True}]:
        saved = new_page(browser, onboarded=True, saved={**seed, **flags})
        saved.locator('#page h1').click()
        saved.evaluate("window.dispatchEvent(new Event('pageshow'))")
        assert not main_calls(saved)
        saved.context.close()
    print('PASS reloading interrupted/completed finales never starts background music')

    finale.on('dialog', lambda dialog: dialog.accept())
    finale.locator('#reset-game').click()
    assert finale.locator('#main-audio').evaluate('a => a.paused && a.currentTime === 0')
    finale.locator('#music-mute').click()  # Preference remains available without starting music.
    assert not main_calls(finale)
    assert finale.evaluate('key => localStorage.getItem(key)', STARTED) is None
    finale.reload()
    assert not main_calls(finale)
    finale.evaluate("localStorage.setItem('misos-bachelor-cold-open-v1', 'complete')")
    finale.reload()
    finale.locator('#start-weekend').click()
    main_playing(finale)
    assert finale.locator('#main-audio').evaluate('a => a.muted')
    print('PASS reset waits for a new start tap, including after reload, and retains mute preference')

    unavailable = new_page(browser, storage_denied=True)
    unavailable.clock.run_for(40000)
    expect(unavailable.locator('#start-weekend')).to_be_visible()
    unavailable.locator('#start-weekend').click()
    main_playing(unavailable)
    unavailable.locator('#music-mute').click()
    assert unavailable.locator('#main-audio').evaluate('a => a.muted')
    print('PASS storage failure does not break playback or mute')
    assert not ERRORS, ERRORS
    print('PASS no browser JavaScript errors')
    browser.close()
