"""Offline rendering check, never a model or benchmark call."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--html',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(exist_ok=False)
    errors,remote=[],[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='msedge',headless=True)
        try:
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.on('request',lambda r:remote.append(r.url) if r.url.startswith(('http:','https:')) else None)
            page.goto(args.html.resolve().as_uri(),wait_until='load',timeout=60000)
            page.screenshot(path=str(args.output/'desktop.png'))
            anchors=page.evaluate('''() => [...document.querySelectorAll('a[href^="#"]')].map(a=>a.getAttribute('href').slice(1)).filter(id=>!document.getElementById(id))''')
            dependencies=page.evaluate('''() => [...document.querySelectorAll('[src],link[href]')].map(e=>e.getAttribute('src')||e.getAttribute('href')).filter(u=>/^(https?:)?\\/\\//.test(u))''')
            wide_overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
            page.locator('#b002').scroll_into_view_if_needed()
            page.screenshot(path=str(args.output/'b002.png'))
            page.set_viewport_size({'width':390,'height':844})
            page.evaluate('scrollTo(0,0)')
            page.screenshot(path=str(args.output/'mobile.png'))
            narrow_overflow=page.evaluate('document.documentElement.scrollWidth>innerWidth')
            images=page.locator('img[src^="data:"]').count()
        finally:
            browser.close()
    result={'broken_anchors':anchors,'external_dependencies':dependencies,'remote_requests':remote,'page_errors':errors,
            'desktop_overflow':wide_overflow,'mobile_overflow':narrow_overflow,'embedded_images':images,'model_calls':0}
    result['passed']=not any((anchors,dependencies,remote,errors,wide_overflow,narrow_overflow))
    (args.output/'QA.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result))
    if not result['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
