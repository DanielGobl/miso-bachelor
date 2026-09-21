"""Browser checks: pip install playwright; python tests/intro_browser.py."""
from pathlib import Path

from playwright.sync_api import sync_playwright, expect

URL = (Path(__file__).resolve().parents[1] / 'index.html').as_uri()
ERRORS = []


def new_page(browser, reduced=False):
    context = browser.new_context(viewport={'width': 390, 'height': 844},
                                  reduced_motion='reduce' if reduced else 'no-preference')
    page = context.new_page()
    page.on('pageerror', lambda error: ERRORS.append(str(error)))
    page.clock.install()
    page.goto(URL)
    return page


def departure(page):
    expect(page.locator('.cold-open')).to_be_visible()
    expect(page.locator('#welcome')).to_be_hidden()
    expect(page.locator('#page')).to_be_hidden()
    expect(page.locator('#flight-plane')).to_be_hidden()
    messages = ['INICIALIZUJEM OPERÁCIU...', 'LOKALIZUJEM CIEĽ...',
                'BRATISLAVA → VARŠAVA', 'TRASA POTVRDENÁ ✓']
    for message in messages:
        expect(page.locator('#cold-message')).to_have_text(message)
        page.clock.fast_forward(3300)
    expect(page.locator('#cold-message')).to_have_text('LET DO VARŠAVY...')
    expect(page.locator('#flight-plane')).to_be_visible()
    expect(page.locator('.cold-open')).to_have_class('cold-open route-visible')


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel='chrome', headless=True)
    page = new_page(browser)
    departure(page)
    start = page.locator('#flight-plane').get_attribute('transform')
    page.clock.fast_forward(4000)
    middle = page.locator('#flight-plane').get_attribute('transform')
    assert middle != start
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.flight-map').evaluate("el => el.getBoundingClientRect().bottom <= innerHeight")
    page.clock.fast_forward(4000)
    expect(page.locator('#cold-message')).to_have_text('PRISTÁTIE POTVRDENÉ ✓')
    assert 'translate(350 80)' in page.locator('#flight-plane').get_attribute('transform')
    assert 'flight-arrived' in page.locator('.cold-open').get_attribute('class')
    page.clock.fast_forward(3300)
    expect(page.locator('#cold-message')).to_have_text('CIEĽ DOSIAHNUTÝ')
    page.clock.fast_forward(3300)
    expect(page.locator('#cold-message')).to_have_text('VITAJ V POĽSKU, MIŠO.')
    page.clock.fast_forward(3300)
    page.clock.fast_forward(400)
    expect(page.locator('.cold-open')).to_be_hidden()
    expect(page.locator('#welcome')).to_be_visible()
    assert page.evaluate("localStorage.getItem('misos-bachelor-cold-open-v1')") == 'complete'
    page.reload()
    expect(page.locator('#welcome')).to_be_visible()
    expect(page.locator('.cold-open')).to_be_hidden()
    page.locator('#start-weekend').click()
    page.clock.fast_forward(220)
    expect(page.locator('#boot-screen')).to_be_visible()
    print('PASS first-visit route, moving plane, landing, mobile layout, welcome and saved completion')

    reduced = new_page(browser, reduced=True)
    departure(reduced)
    start = reduced.locator('#flight-plane').get_attribute('transform')
    reduced.clock.fast_forward(4000)
    assert reduced.locator('#flight-plane').get_attribute('transform') == start
    reduced.clock.fast_forward(4000)
    assert 'translate(350 80)' in reduced.locator('#flight-plane').get_attribute('transform')
    print('PASS reduced motion preserves departure/arrival and reading time')

    existing = new_page(browser)
    existing.evaluate("""() => {
        localStorage.setItem('misos-bachelor-weekend-v1', JSON.stringify({stages: [1,0,0,0]}));
        localStorage.removeItem('misos-bachelor-cold-open-v1');
    }""")
    existing.reload()
    expect(existing.locator('#welcome')).to_be_visible()
    expect(existing.locator('.cold-open')).to_be_hidden()
    existing.goto(URL + '?preview=finale')
    expect(existing.locator('#activate-finale')).to_be_visible()
    assert existing.locator('.cold-open').count() == 0
    print('PASS existing saves and finale preview bypass intro')
    assert not ERRORS, ERRORS
    print('PASS no browser JavaScript errors')
    browser.close()
