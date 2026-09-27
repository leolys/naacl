"""Offline viewer checks only; no benchmark browser actions or model calls."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from evaluate import sha


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
            page.goto(args.html.resolve().as_uri(), wait_until='load', timeout=120000)
            ids = page.locator('#case option').evaluate_all('(xs)=>xs.map(x=>x.value)')
            for slug in ids:
                page.select_option('#case', slug)
                okay = page.locator('.chart').evaluate('(img)=>img.decode().then(()=>img.naturalWidth>0).catch(()=>false)')
                if not okay:
                    failed_images.append(slug)
                if not page.locator('#body h2').inner_text().startswith(slug):
                    errors.append('Wrong selected case: ' + slug)
                if page.locator('article.card').count() != 6:
                    errors.append('Not six version cards: ' + slug)
            page.select_option('#case', ids[0])
            page.screenshot(path=str(args.output / 'desktop.png'))
            desktop_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            for method in ('v3', 'v4', 'v5', 'v6', 'v7'):
                page.select_option('#method', method)
                for value in ('gain', 'loss', 'wrong', 'null', 'failed'):
                    page.select_option('#filter', value)
                    actual = page.locator('#case option').count()
                    expected = page.evaluate('''([m,f])=>D.rows.filter(r=>{
                        let a=r.arms.plain.state,b=r.arms[m].state;
                        if(f==='gain')return a!=='target'&&b==='target';
                        if(f==='loss')return a==='target'&&b!=='target';
                        if(f==='wrong')return ['trap','other'].includes(a)&&b==='target';
                        if(f==='null')return b==='no_option';
                        return ['interface_failed','not_completed'].includes(b);
                    }).length''', [method, value])
                    filters.append({'method': method, 'filter': value, 'actual': actual,
                                    'expected': expected, 'passed': actual == expected})
            page.select_option('#filter', 'all')
            panels = {}
            for panel, expected in [('dev', 24), ('rest', 116), ('all', 140)]:
                page.select_option('#panel', panel)
                panels[panel] = {'actual': page.locator('#case option').count(), 'expected': expected}
            page.fill('#query', 'b001')
            search_results = page.locator('#case option').evaluate_all('(xs)=>xs.map(x=>x.value)')
            search_matches = search_results == ['b001']
            page.fill('#query', '')
            page.select_option('#case', ids[-1])
            page.click('#prev')
            next_prev = page.locator('#body h2').inner_text().startswith(ids[-2])
            page.click('#next')
            next_prev = next_prev and page.locator('#body h2').inner_text().startswith(ids[-1])
            page.select_option('#case', 'pub006')
            page.locator('#body h2').scroll_into_view_if_needed()
            page.screenshot(path=str(args.output / 'sample.png'))
            page.set_viewport_size({'width': 390, 'height': 844})
            page.evaluate('window.scrollTo(0,0)')
            page.screenshot(path=str(args.output / 'mobile_overview.png'))
            page.locator('#body h2').scroll_into_view_if_needed()
            page.screenshot(path=str(args.output / 'mobile.png'))
            mobile_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.locator('#body section details summary').first.click()
            expanded_overflow = page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.screenshot(path=str(args.output / 'mobile_evidence.png'))
        finally:
            browser.close()
    report = {'tested_html': str(args.html.resolve()), 'tested_html_sha256': sha(args.html),
        'cases_exercised': len(ids), 'six_cards_checked_every_case': True, 'errors': errors,
        'external_requests': remote, 'failed_images': failed_images, 'filter_checks': filters,
        'panel_checks': panels, 'search_passed': search_matches, 'search_result_ids': search_results,
        'next_prev_passed': next_prev, 'desktop_overflow': desktop_overflow,
        'mobile_overflow': mobile_overflow, 'expanded_mobile_overflow': expanded_overflow,
        'model_requests': 0, 'business_browser_operations': 0}
    report['passed'] = (len(ids) == 140 and not any((errors, remote, failed_images, desktop_overflow,
        mobile_overflow, expanded_overflow)) and all(x['passed'] for x in filters)
        and all(x['actual'] == x['expected'] for x in panels.values()) and search_matches and next_prev)
    with (args.output / 'QA.json').open('x', encoding='utf-8') as out:
        json.dump(report, out, ensure_ascii=False, indent=2)
    print(json.dumps(report))
    if not report['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
