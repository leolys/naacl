"""Read-only, offline HTML visual QA; not an agent/model experiment."""
import base64
import re
from io import BytesIO
from bs4 import BeautifulSoup
from PIL import Image
from playwright.sync_api import sync_playwright
from deps import HERE, wire


def main():
    pagefile=HERE/'ONLINE_DEFENSE_REVIEW.html'
    soup=BeautifulSoup(pagefile.read_text(encoding='utf-8'),'html.parser')
    assert not soup.find_all('script')
    assert not soup.select('iframe,form,input,button,object,embed')
    assert len(soup.select('section.trace'))==13
    for element in soup.find_all(True):
        assert not any(str(k).lower().startswith('on') for k in element.attrs)
    images=soup.find_all('img')
    for image in images:
        assert image['src'].startswith(('data:image/png;base64,','data:image/jpeg;base64,'))
        with Image.open(BytesIO(base64.b64decode(image['src'].split(',',1)[1],validate=True))) as raster:
            raster.verify()
    external=[]
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path=wire.read(HERE/'config.json')['browser_executable'])
        page=browser.new_page(viewport={'width':1440,'height':1000})
        def guard(route):
            if route.request.url.startswith(('file:','data:')):route.continue_()
            else:
                external.append(route.request.url)
                route.abort()
        page.route('**/*',guard)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(pagefile.as_uri(),wait_until='load')
        page.screenshot(path=str(HERE/'review_top_v2.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        sample=page.locator('#live_v1_b001_clean140_online_completion').locator('..')
        sample.scroll_into_view_if_needed()
        sample.locator('summary').filter(has_text=re.compile(r'^7\.')).first.click()
        page.screenshot(path=str(HERE/'review_rule_state_v2.png'))
        body=page.locator('body').inner_text()
        assert '初始解释' in body and '逐条实际记录' in body
        assert not external and not errors
        browser.close()
    wire.dump(HERE/'VIEWER_QA.json',{'mode':'offline_artifact_view_not_agent_experiment',
        'sections':13,'embedded_raster_images':len(images),'all_embedded_images_decode':True,
        'external_requests':external,'javascript_errors':errors,'no_horizontal_overflow_at_1440':True,
        'model_requests':0,'read_only_browser_interactions':3,'failed_prior_qa_interaction_attempts':3,
        'screenshots':['review_top_v2.png','review_rule_state_v2.png'],
        'counts_note':'3 successful +3 prior attempted local viewer interactions, separately reported; not additional agent trials. 99 experimental +6 viewer interactions <600 authorized cap.'})
    print('Offline viewer checks passed:',len(images),'embedded images; 13 units.')


if __name__=='__main__':main()
