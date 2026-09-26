"""Run with Playwright installed; BROWSER_CHANNEL=msedge selects installed Edge."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

URL = (Path(__file__).resolve().parents[1] / 'index.html').as_uri()
ERRORS = []


def new_page(browser, reduced=False):
    context = browser.new_context(viewport={'width': 390, 'height': 844},
                                  reduced_motion='reduce' if reduced else 'no-preference')
    context.add_init_script("""
        localStorage.clear();
        localStorage.setItem('misos-bachelor-cold-open-v1', 'complete');
        window.mainPlays = [];
        const play = HTMLMediaElement.prototype.play;
        HTMLMediaElement.prototype.play = function() {
            if (this.id === 'main-audio') mainPlays.push({time: this.currentTime, gesture: navigator.userActivation.isActive});
            return play.call(this);
        };
        window.menuEvents = [];
        window.addEventListener('bachelor:dashboard', () => {
            const audio = document.getElementById('main-audio');
            menuEvents.push({time: audio.currentTime, paused: audio.paused});
        });
    """)
    page = context.new_page()
    page.on('pageerror', lambda error: ERRORS.append(str(error)))
    page.goto(URL)
    return page


with sync_playwright() as p:
    browser = p.chromium.launch(channel=os.environ.get('BROWSER_CHANNEL', 'chrome'), headless=True,
                                args=['--mute-audio'])
    # Real MP3 playback through the full 26 seconds, with no synthetic clock.
    real = new_page(browser)
    real.locator('#start-weekend').click()
    assert real.evaluate('mainPlays') == [{'time': 0, 'gesture': True}]
    real.evaluate("document.getElementById('start-weekend').dispatchEvent(new MouseEvent('click'))")
    assert len(real.evaluate('mainPlays')) == 1
    real.wait_for_function('menuEvents.length === 1', timeout=35000)
    event = real.evaluate('menuEvents[0]')
    assert 26 <= event['time'] < 26.15, event
    assert not event['paused'] and len(real.evaluate('mainPlays')) == 1
    real.wait_for_function('document.getElementById("main-audio").currentTime > 26.3')
    expect(real.locator('#page')).to_be_visible()
    print('PASS real song starts at zero and the menu opens at the drop without another play call:', event)

    for reduced in (False, True):
        page = new_page(browser, reduced)
        page.clock.install()
        page.evaluate("""() => {
            const audio = document.getElementById('main-audio');
            window.songTime = 19;
            Object.defineProperty(audio, 'currentTime', {
                configurable: true, get: () => songTime, set: value => { songTime = value; }
            });
            window.seekSong = time => {
                songTime = time;
                audio.dispatchEvent(new Event('timeupdate'));
            };
        }""")
        page.locator('#start-weekend').click()
        assert page.evaluate('songTime') == 0
        page.evaluate('seekSong(.3)')
        expect(page.locator('#boot-screen')).to_be_visible()
        page.clock.fast_forward(90000)
        expect(page.locator('#page')).not_to_be_visible()
        expect(page.locator('#boot-status')).to_have_text('KONTROLUJEM ZÁSOBY PIVA...')
        page.evaluate('seekSong(14.2)')
        expect(page.locator('#boot-status')).to_have_text('KONTAKTUJEM DÍLERA...')
        page.evaluate("document.getElementById('start-weekend').dispatchEvent(new MouseEvent('click'))")
        page.evaluate("window.dispatchEvent(new Event('bachelor:started'))")
        assert page.evaluate('songTime') == 14.2
        assert len(page.evaluate('mainPlays')) == 1
        page.evaluate('seekSong(22)')
        expect(page.locator('#boot-status')).to_have_text('POSLEDNÁ KONTROLA...')
        expect(page.locator('#boot-percentage')).to_have_text('98%')
        page.evaluate('seekSong(24)')
        expect(page.locator('#boot-heading')).to_have_text('SYSTÉM PRIPRAVENÝ')
        expect(page.locator('#boot-success')).to_be_visible()
        expect(page.locator('#boot-percentage')).to_have_text('100%')
        page.evaluate('seekSong(25.999)')
        expect(page.locator('#page')).not_to_be_visible()
        page.evaluate('seekSong(26)')
        expect(page.locator('#page')).to_be_visible()
        assert page.evaluate('menuEvents') == [{'time': 26, 'paused': False}]
        page.evaluate('seekSong(30)')
        assert len(page.evaluate('menuEvents')) == 1
        assert len(page.evaluate('mainPlays')) == 1
        assert page.evaluate("localStorage.getItem('misos-bachelor-onboarding-v1')") == 'complete'
        page.context.close()
    print('PASS paused media cannot advance initialization; media seeks catch up, exact 26s boundary, reduced motion and repeated taps')

    lagged = new_page(browser)
    lagged.locator('#start-weekend').click()
    lagged.evaluate("""() => {
        const audio = document.getElementById('main-audio');
        Object.defineProperty(audio, 'currentTime', {get: () => 27.5});
        document.dispatchEvent(new Event('visibilitychange'));
    }""")
    expect(lagged.locator('#page')).to_be_visible()
    assert len(lagged.evaluate('mainPlays')) == 1
    print('PASS returning after the drop opens the menu immediately without replaying messages')
    assert not ERRORS, ERRORS
    print('PASS no browser JavaScript errors')
    browser.close()
