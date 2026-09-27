"""Local-only HTML display QA, not benchmark browser transitions."""
import argparse
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--html', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    errors, remote = [], []
    filter_checks = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge', headless=True)
        try:
            page = browser.new_page(viewport={'width':1440, 'height':1000})
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.on('request', lambda r: remote.append(r.url) if r.url.startswith(('http:', 'https:')) else None)
            page.goto(args.html.resolve().as_uri(), wait_until='load', timeout=60000)
            # QA loads every embedded image; production HTML remains lazy for large panels.
            page.evaluate("async () => {const imgs=[...document.images]; imgs.forEach(i=>i.loading='eager'); await Promise.all(imgs.map(i=>i.decode().catch(()=>null)));}")
            page.screenshot(path=str(args.output / 'desktop.png'))
            broken = page.evaluate("() => [...document.querySelectorAll('a[href^=\"#\"]')].filter(a=>!document.getElementById(a.hash.slice(1))).map(a=>a.hash)")
            wide = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            count = page.locator('section').count()
            for selector, attribute in [('#state-filter', 'state'), ('#agreement-filter', 'agreement')]:
                control = page.locator(selector)
                if control.count() and control.locator('option').count() > 1:
                    value = control.locator('option').nth(1).get_attribute('value')
                    control.select_option(value)
                    visible = page.locator('section:visible').count()
                    expected = page.locator('section[data-%s="%s"]' % (attribute, value)).count()
                    filter_checks.append({'selector': selector, 'visible': visible, 'expected': expected, 'passed': visible == expected})
                    control.select_option('')
            if count:
                page.locator('section').nth(min(2, count-1)).scroll_into_view_if_needed()
                page.screenshot(path=str(args.output / 'sample.png'))
            page.set_viewport_size({'width':390, 'height':844})
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=str(args.output / 'mobile.png'))
            narrow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            images = page.locator('img[src^="data:"]').count()
            unloaded = page.locator('img').evaluate_all('(imgs)=>imgs.filter(x=>!x.complete||!x.naturalWidth).length')
            candidate = page.locator('section details').filter(has=page.locator('summary', has_text='原O/B与逐项核验')).first
            expanded_overflow = False
            if candidate.count():
                candidate.locator('summary').first.click()
                candidate.scroll_into_view_if_needed()
                page.screenshot(path=str(args.output / 'mobile_evidence.png'))
                expanded_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
        finally:
            browser.close()
    result = {'tested_html': str(args.html.resolve()),
              'tested_html_sha256': hashlib.sha256(args.html.read_bytes()).hexdigest(),
              'errors': errors, 'remote_requests': remote, 'broken_anchors': broken,
              'desktop_overflow': wide, 'mobile_overflow': narrow, 'embedded_images': images,
              'unloaded_images': unloaded, 'sections': count, 'model_calls':0, 'business_browser_operations':0}
    result['filter_checks'] = filter_checks
    result['expanded_mobile_overflow'] = expanded_overflow
    result['passed'] = not any((errors, remote, broken, wide, narrow, unloaded, expanded_overflow)) and images == count and all(x['passed'] for x in filter_checks)
    (args.output / 'QA.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))

if __name__ == '__main__':
    main()
