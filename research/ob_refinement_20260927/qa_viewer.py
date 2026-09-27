"""Local display regression, not a benchmark or model request."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from evaluate import digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    errors, remote, filters, failed_images = [], [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda err: errors.append(str(err)))
            page.on('request', lambda req: remote.append(req.url) if req.url.startswith(('http:', 'https:')) else None)
            page.goto(args.html.resolve().as_uri(), wait_until='load')
            ids = page.locator('#case option').evaluate_all('(xs)=>xs.map(x=>x.value)')
            for slug in ids:
                page.select_option('#case', slug)
                okay = page.locator('.chart').evaluate('(img)=>img.decode().then(()=>img.naturalWidth>0).catch(()=>false)')
                if not okay:
                    failed_images.append(slug)
                if slug not in page.locator('#body h2').inner_text():
                    errors.append('Wrong selected case: ' + slug)
            page.select_option('#case', ids[0])
            page.screenshot(path=str(args.output / 'desktop.png'))
            desktop_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            for value in ('improved', 'degraded', 'same', 'failed'):
                page.select_option('#filter', value)
                actual = page.locator('#case option').count()
                expected = page.evaluate('(v)=>D.records.filter(r=>changeType(r)===v).length', value)
                filters.append({'filter': value, 'actual': actual, 'expected': expected, 'passed': actual == expected})
            page.select_option('#filter', 'all')
            page.fill('#query', ids[0])
            search_results = page.locator('#case option').evaluate_all('(xs)=>xs.map(x=>x.value)')
            search_matches = page.locator('#case option').count() == 1
            page.fill('#query', '')
            page.select_option('#case', ids[-1])
            next_prev = page.locator('#body h2').inner_text().startswith(ids[-1])
            page.click('#prev')
            next_prev = next_prev and page.locator('#body h2').inner_text().startswith(ids[-2])
            page.click('#next')
            next_prev = next_prev and page.locator('#body h2').inner_text().startswith(ids[-1])
            page.set_viewport_size({'width': 390, 'height': 844})
            page.screenshot(path=str(args.output / 'mobile.png'))
            mobile_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.locator('#body section details summary').first.click()
            expanded_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
        finally:
            browser.close()
    report = {'tested_html': str(args.html.resolve()), 'tested_html_sha256': digest(args.html),
              'cases_exercised': len(ids), 'errors': errors, 'external_requests': remote,
              'failed_images': failed_images, 'filter_checks': filters, 'search_passed': search_matches,
              'search_query': ids[0], 'search_result_ids': search_results,
              'next_prev_passed': next_prev, 'desktop_overflow': desktop_overflow,
              'mobile_overflow': mobile_overflow, 'expanded_mobile_overflow': expanded_overflow,
              'model_requests': 0, 'business_browser_operations': 0}
    report['passed'] = (not any((errors, remote, failed_images, desktop_overflow, mobile_overflow, expanded_overflow))
                        and all(x['passed'] for x in filters) and search_matches and next_prev and len(ids) > 0)
    (args.output / 'QA.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
