"""Browser checks: pip install playwright; python tests/activity_navigation_browser.py.

Set BROWSER_CHANNEL=msedge to use installed Edge instead of Chrome.
"""
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
URL = (ROOT / 'index.html').as_uri()
KEY = 'misos-bachelor-weekend-v1'
ERRORS = []


def new_page(browser, stages, width=390, height=844):
    context = browser.new_context(viewport={'width': width, 'height': height}, reduced_motion='reduce')
    context.add_init_script("""
        if (!sessionStorage.getItem('seeded')) {
            localStorage.clear();
            localStorage.setItem('misos-bachelor-cold-open-v1', 'complete');
            localStorage.setItem('misos-bachelor-onboarding-v1', 'complete');
            localStorage.setItem('%s', JSON.stringify(%s));
            sessionStorage.setItem('seeded', 'yes');
        }
        Object.defineProperty(navigator, 'geolocation', {value: {
            getCurrentPosition() { throw new Error('Unexpected geolocation request'); }
        }});
    """ % (KEY, json.dumps({'stages': stages, 'riddleOpened': [True] * 4, 'activeActivity': 0})))
    page = context.new_page()
    page.on('pageerror', lambda error: ERRORS.append(str(error)))
    page.goto(URL)
    return page


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel=os.environ.get('BROWSER_CHANNEL', 'chrome'),
                                         headless=True, args=['--mute-audio'])
    page = new_page(browser, [1, 0, 0, 0])
    assert page.locator('.activity-navigation').count() == 0
    page.evaluate("""() => {
        const schedule = window.setTimeout;
        window.setTimeout = (callback, delay) => schedule(callback, Math.min(delay, 20));
    }""")
    page.locator('#riddle-answer').fill('slnko')
    page.locator('#answer-button').click()
    expect(page.locator('#destination .activity-navigation')).to_be_visible()
    page.reload()
    expect(page.locator('#destination .activity-navigation')).to_be_visible()
    print('PASS activity navigation remains gated by full unlock and survives reload')

    page = new_page(browser, [2] * 4)
    expected = [
        'Centrum Nauki Kopernik, Wybrzeże Kościuszkowskie 20, 00-390 Warszawa',
        'Miami Wars, Solec 8, 00-439 Warszawa',
        'https://maps.app.goo.gl/SnPpvK2UPu3bSVFt8',
        '52.240950, 21.011296'
    ]
    for index in range(4):
        page.locator('.activity').nth(index).click()
        link = page.locator('.destination:visible .activity-navigation a')
        expect(link).to_have_text('🧭 NAVIGOVAŤ NA MIESTO')
        href = link.get_attribute('href')
        if index == 2:
            assert href == expected[index]
        else:
            query = parse_qs(urlparse(href).query)
            assert query['destination'] == [expected[index]]
            assert query['api'] == ['1'] and query['dir_action'] == ['navigate']
    page.on('dialog', lambda dialog: dialog.accept())
    page.locator('#reset-game').click()
    assert page.locator('.activity-navigation').count() == 0
    print('PASS all existing activity navigation URLs and reset behavior preserved')

    assert not ERRORS, ERRORS
    print('PASS no browser JavaScript errors')
    browser.close()
