"""Offline presentation QA, adapted from the project's existing viewer check."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--page', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--channel', default='msedge')
    args = parser.parse_args()
    page_path = args.page.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    network, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel=args.channel)
        page = browser.new_page(viewport={'width': 1440, 'height': 1080}, device_scale_factor=1)
        page.route('http://**/*', lambda route: route.abort())
        page.route('https://**/*', lambda route: route.abort())
        page.on('request', lambda request: network.append(request.url)
                if request.url.startswith(('http:', 'https:')) else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(page_path.as_uri(), wait_until='load')
        page.screenshot(path=str(out / 'overview.png'))
        image_records = []
        for img in page.locator('img').all():
            img.scroll_into_view_if_needed()
            img.evaluate('img => img.decode()')
            image_records.append(img.evaluate('i => ({alt:i.alt, loaded:i.complete && i.naturalWidth>0, width:i.naturalWidth, height:i.naturalHeight})'))
        missing = page.locator('a[href^="#"]').evaluate_all(
            "links => links.map(x => x.getAttribute('href').slice(1)).filter(id => id && !document.getElementById(id))")
        for anchor, filename in [('#overview', 'results.png'),
                                 ('#official140-alternative_conclusion', 'official_new_questions.png'),
                                 ('#clean140-old_questions', 'clean_old_questions.png')]:
            page.locator(anchor).scroll_into_view_if_needed()
            page.screenshot(path=str(out / filename))
        desktop_overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
        page.set_viewport_size({'width': 390, 'height': 844})
        page.locator('#overview').scroll_into_view_if_needed()
        page.screenshot(path=str(out / 'mobile_overview.png'))
        mobile_overflow = page.evaluate('document.documentElement.scrollWidth > innerWidth')
        expected = json.loads((page_path.parent / 'PROVENANCE.json').read_text(encoding='utf-8'))['image_count']
        receipt = {
            'page': str(page_path), 'browser_version': browser.version, 'channel': args.channel,
            'image_count': len(image_records), 'expected_image_count': expected, 'images': image_records,
            'network_requests': network, 'page_errors': errors, 'missing_anchor_targets': missing,
            'desktop_horizontal_overflow': desktop_overflow, 'mobile_horizontal_overflow': mobile_overflow,
            'model_requests': 0, 'business_browser_operations': 0,
            'scope': 'Local presentation QA only, separate from the experimental browser ledger.'
        }
        receipt['passed'] = (len(image_records) == expected and expected > 0 and
                             all(i['loaded'] for i in image_records) and
                             not any((network, errors, missing, desktop_overflow, mobile_overflow)))
        (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        browser.close()
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    if not receipt['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
