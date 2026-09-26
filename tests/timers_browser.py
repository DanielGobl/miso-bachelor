"""Browser checks: pip install playwright; python tests/timers_browser.py."""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

URL = (Path(__file__).resolve().parents[1] / 'index.html').as_uri()
KEY = 'misos-bachelor-weekend-v1'
ERRORS = []


def new_page(browser, seed=None, onboarded=True):
    context = browser.new_context(viewport={'width': 390, 'height': 844})
    context.add_init_script("""
        if (!sessionStorage.getItem('seeded')) {
            localStorage.clear();
            localStorage.setItem('misos-bachelor-cold-open-v1', 'complete');
            if (%s) localStorage.setItem('misos-bachelor-onboarding-v1', 'complete');
            const seed = %s;
            if (seed) localStorage.setItem('%s', JSON.stringify(seed));
            sessionStorage.setItem('seeded', 'yes');
        }
        const now = Date.now.bind(Date);
        Date.now = () => now() + Number(sessionStorage.getItem('elapsed') || 0);
    """ % (json.dumps(onboarded), json.dumps(seed), KEY))
    page = context.new_page()
    page.on('pageerror', lambda error: ERRORS.append(str(error)))
    page.goto(URL)
    return page


def saved(page):
    return page.evaluate('(key) => JSON.parse(localStorage.getItem(key))', KEY)


def elapse(page, milliseconds):
    page.evaluate("""ms => {
        sessionStorage.setItem('elapsed', ms);
        window.dispatchEvent(new Event('pageshow'));
    }""", milliseconds)


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='chrome', headless=True, args=['--mute-audio'])
    page = new_page(browser)
    # Shorten presentation sequences while exercising real access/riddle transitions.
    page.evaluate("""() => {
        const schedule = window.setTimeout;
        window.setTimeout = (callback, delay) => schedule(callback, Math.min(delay, 20));
    }""")
    page.locator('#access-code').fill('EXPERIMENT')
    page.locator('#unlock-button').click()
    timer = page.locator('#challenge .timer-value')
    expect(timer).to_have_text('60:00')
    started = saved(page)['timers'][0]['challengeStartedAt']
    elapse(page, 120000)
    expect(timer).to_have_text('58:00')
    page.reload()
    assert saved(page)['timers'][0]['challengeStartedAt'] == started
    assert timer.inner_text().startswith('57:') or timer.inner_text() == '58:00'
    elapse(page, 3601000)
    expect(timer).to_have_text('00:00')
    expect(page.locator('#challenge .timer-status')).to_contain_text('ČAS VYPRŠAL')
    assert page.locator('#challenge .complete-task').is_enabled()
    page.evaluate("""() => {
        const schedule = window.setTimeout;
        window.setTimeout = (callback, delay) => schedule(callback, Math.min(delay, 20));
    }""")
    page.locator('#challenge .complete-task').click()
    expect(page.locator('#riddle .timer-value')).to_have_text('10:00')
    page.locator('.hint-toggle').nth(1).click()
    expect(page.locator('#hint-copy-1')).to_be_visible()
    assert saved(page)['timers'][0]['hintsOpened'] == [False, True, False]
    riddle_started = saved(page)['timers'][0]['riddleStartedAt']
    page.reload()
    assert saved(page)['timers'][0]['riddleStartedAt'] == riddle_started
    expect(page.locator('#hint-copy-1')).to_be_visible()
    elapse(page, 4202000)
    expect(page.locator('#riddle .timer-value')).to_have_text('00:00')
    assert page.locator('#answer-button').is_enabled()
    print('PASS access flow, both timer durations, reload persistence and nonblocking expiry')

    # Each activity has separate hint state and its original hint text.
    hints = new_page(browser, {'stages': [1] * 4, 'riddleOpened': [True] * 4, 'activeActivity': 0})
    expected_last = ['Každé ráno ma hľadáš na oblohe.', 'Sever je moja slabosť.',
                     'Po použití zo mňa zostane popol.', 'Moje hrdlo udáva rýchlosť, akou plynie čas.']
    for index, expected in enumerate(expected_last):
        hints.locator('.activity').nth(index).click()
        for hint in range(3):
            expect(hints.locator('.hint-toggle').nth(hint)).to_have_attribute('aria-expanded', 'false')
            hints.locator('.hint-toggle').nth(hint).click()
            expect(hints.locator(f'#hint-copy-{hint}')).to_be_visible()
        expect(hints.locator('#hint-copy-2')).to_have_text(expected)
    hints.reload()
    for state in saved(hints)['timers']:
        assert state['hintsOpened'] == [True] * 3
    assert hints.evaluate('document.documentElement.scrollWidth <= innerWidth')
    print('PASS all 12 hints, separate saved state, older saves and mobile layout')

    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('#reset-game').click()
    expect(page.locator('.cold-open')).to_be_visible()
    assert page.evaluate('(key) => localStorage.getItem(key)', KEY) is None
    page.reload()
    page.evaluate("localStorage.setItem('misos-bachelor-onboarding-v1', 'complete')")
    page.reload()
    page.evaluate("""() => {
        const schedule = window.setTimeout;
        window.setTimeout = (callback, delay) => schedule(callback, Math.min(delay, 20));
    }""")
    page.locator('#access-code').fill('EXPERIMENT')
    page.locator('#unlock-button').click()
    expect(page.locator('#challenge .timer-value')).to_have_text('60:00')
    assert saved(page)['timers'][0]['hintsOpened'] == [False] * 3
    assert saved(page)['timers'][0]['riddleStartedAt'] is None
    print('PASS reset clears timers/hints and a new challenge starts at 60:00')

    loading = new_page(browser, onboarded=False)
    loading.clock.install()
    loading.evaluate("""() => {
        const audio = document.getElementById('main-audio');
        let songTime = 0;
        Object.defineProperty(audio, 'currentTime', {
            configurable: true, get: () => songTime, set: value => { songTime = value; }
        });
        window.setSongTime = time => {
            songTime = time;
            audio.dispatchEvent(new Event('timeupdate'));
        };
    }""")
    loading.locator('#start-weekend').click()
    messages = [
        'KONTROLUJEM ZÁSOBY PIVA...', 'SYNCHRONIZUJEM PARTIU...', 'PRIPRAVUJEM FINANCIE...',
        'KALIBRUJEM PEČEŇ...', 'PRIPRAVUJEM POCHYBNÉ ROZHODNUTIA...', 'KONTAKTUJEM BOBRY...',
        'MAŽEM SIMINE ČÍSLO...', 'KONTAKTUJEM DÍLERA...', 'MAŽEM HISTÓRIU PREHLIADAČA...',
        'ZABEZPEČUJEM DIPLOMATICKÚ IMUNITU...', 'AKTIVUJEM REŽIM ŽENÍCH...'
    ]
    for index, message in enumerate(messages):
        loading.evaluate('setSongTime', index * 2 + .3)
        expect(loading.locator('#boot-status')).to_have_text(message)
    loading.evaluate('setSongTime', 22)
    expect(loading.locator('#boot-status')).to_have_text('POSLEDNÁ KONTROLA...')
    loading.evaluate('setSongTime', 24)
    expect(loading.locator('#boot-percentage')).to_have_text('100%')
    loading.evaluate('setSongTime', 26)
    expect(loading.locator('#page')).to_be_visible()
    print('PASS all 11 custom loading messages and completed onboarding')
    assert not ERRORS, ERRORS
    print('PASS no browser JavaScript errors')
    browser.close()
