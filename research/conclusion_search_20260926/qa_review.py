"""Offline browser smoke for the self-contained review; no model calls."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--html', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    remote, errors, checks = [], [], {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('request', lambda request: remote.append(request.url) if request.url.startswith(('http:', 'https:')) else None)
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(args.html.resolve().as_uri(), wait_until='load', timeout=60000)
            page.screenshot(path=str(args.output/'desktop.png'))
            checks['broken_anchors'] = page.evaluate('''() => [...document.querySelectorAll('a[href^="#"]')]
                .map(a=>a.getAttribute('href').slice(1)).filter(id=>!document.getElementById(id))''')
            checks['remote_dependencies'] = page.evaluate('''() => [...document.querySelectorAll('[src],link[href]')]
                .map(e=>e.getAttribute('src')||e.getAttribute('href')).filter(u=>/^(https?:)?\\/\\//.test(u))''')
            checks['desktop_overflow'] = page.evaluate('document.documentElement.scrollWidth > innerWidth')
            checks['headings'] = page.locator('h2').all_text_contents()
            checks['embedded_images'] = page.locator('img[src^="data:"]').count()
            page.locator('#isolated-clean140-symmetric_hypotheses').scroll_into_view_if_needed()
            page.screenshot(path=str(args.output/'normal_chain.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=str(args.output/'mobile.png'))
            checks['mobile_overflow'] = page.evaluate('document.documentElement.scrollWidth > innerWidth')
        finally:
            browser.close()
    checks.update(remote_requests=remote, page_errors=errors, model_calls=0)
    checks['passed'] = not any((checks['broken_anchors'], checks['remote_dependencies'], remote, errors,
                               checks['desktop_overflow'], checks['mobile_overflow']))
    (args.output/'QA.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(checks, ensure_ascii=False))
    if not checks['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
