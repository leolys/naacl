"""Run archived original Flask routes; never synthesize the business form."""
from __future__ import annotations

import importlib
import json
import threading
from pathlib import Path
from urllib.parse import urlparse

import flask
from bs4 import BeautifulSoup
from werkzeug.serving import make_server
from deps import SNAPSHOT, PROJECT, public_inputs, wire

MODULES = {'business47': 'business_shell.business_shell_app',
           'public39': 'public_benchmark.public_benchmark_shell_app',
           'environment35': 'environment_energy_shell.environment_shell_app',
           'health19': 'health_shell.health_shell_app'}


def catalog():
    # Offline preparation metadata, never supplied to a model.
    rows = wire.read(PROJECT / '.aris/task_flows_20260924/RUNTIME_TASKS.json')
    return [{'task_id': row['slug'], 'arm': row['arm'], 'domain': row['domain'],
             'alias': 'task_%03d' % (index + 1)} for index, row in enumerate(rows)]


def make_original(case, private):
    private = Path(private)
    private.mkdir(parents=True, exist_ok=True)
    if not hasattr(flask.Flask, 'get'):
        flask.Flask.get = lambda self, rule, **kw: self.route(rule, methods=['GET'], **kw)
        flask.Flask.post = lambda self, rule, **kw: self.route(rule, methods=['POST'], **kw)
    mod = importlib.import_module('web_agent_benchmark.' + MODULES[case['domain']])
    tasks = SNAPSHOT / 'web_agent_benchmark/benchmark_v2_open/splits' / case['arm'] / (case['domain'] + '_tasks.jsonl')
    receipts = private / 'submissions.jsonl'
    if case['domain'] == 'business47':
        app = mod.make_app(tasks, receipts, private / 'summary.md', private / 'manual_review.md', False)
    elif case['domain'] == 'public39':
        app = mod.make_app(receipts, tasks, private / 'summary.md', False)
    else:
        app = mod.make_app(tasks, receipts, False)
    return app


class OriginalBrowser:
    def __init__(self, case, output, budget, executable):
        self.case, self.output, self.budget = case, Path(output), budget
        self.executable = executable
        self.pages, self.history = {}, []
        self.public = self.chart = None
        self.counter = 0
        self.server = self.pw = self.browser = None
        self.output.mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.server = make_server('127.0.0.1', 0, make_original(self.case, self.output / 'private'))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        try:
            self.pw = sync_playwright().start()
            self.browser = self.pw.chromium.launch(headless=True, executable_path=self.executable)
            self.page = self.browser.new_page(viewport={'width': 1440, 'height': 1000}, device_scale_factor=1)
            self.page.set_default_timeout(10000)
            self.base = 'http://127.0.0.1:%d' % self.server.server_port
            self.prefix = '/task/' + self.case['task_id']
            self.page.route('**/*', self._route)
            self.page.on('response', self._response)
            self.budget.transition({'kind': 'initial_open_home'})
            self.page.goto(self.base + self.prefix, wait_until='networkidle')
            self._record({'kind': 'initial_open_home'}, {'ok': True, 'page': 'home'}, 'setup')
            return self
        except BaseException:
            self.close()
            raise

    def _route(self, route):
        url = urlparse(route.request.url)
        allowed = {self.prefix + suffix for suffix in ('', '/dashboard', '/form', '/chart', '/submit', '/confirmation')}
        if url.netloc == urlparse(self.base).netloc and url.path in allowed and not url.query:
            route.continue_()
        else:
            route.abort()

    def _response(self, response):
        if urlparse(response.url).path == self.prefix + '/chart' and response.status == 200:
            mime = response.headers.get('content-type', '')
            suffix = '.png' if 'png' in mime else '.jpeg'
            data = response.body()
            path = self.output / ('observed_chart' + suffix)
            if path.exists() and path.read_bytes() != data:
                raise ValueError('chart_changed_within_task_unsupported')
            if not path.exists():
                path.write_bytes(data)
            self.chart = path

    def _record(self, action, receipt, source='actor'):
        event = {'sequence': len(self.history), 'action': action, 'receipt': receipt, 'source': source}
        self.history.append(event)
        wire.dump(self.output / 'history.json', self.history)

    def snapshot(self):
        self.counter += 1
        suffix = urlparse(self.page.url).path.removeprefix(self.prefix).strip('/')
        page_name = suffix or 'home'
        markup = self.page.content()
        if page_name in ('home', 'dashboard', 'form') and page_name not in self.pages:
            self.pages[page_name] = markup
            (self.output / (page_name + '.html')).write_text(markup, encoding='utf-8')
        if self.public is None and set(self.pages) == {'home', 'dashboard', 'form'}:
            self.public, bindings = public_inputs.extract(self.pages, self.case['alias'])
            public_inputs.verify_bindings(self.public, bindings, self.pages)
            wire.dump(self.output / 'public_task.json', self.public)
            wire.dump(self.output / 'public_bindings.json', bindings)
        soup = public_inputs.visible_soup(markup)
        main = soup.select_one('main') or soup.body
        links = []
        for a in main.select('a[href]'):
            href = a.get('href', '')
            if href in {self.prefix + s for s in ('', '/dashboard', '/form')}:
                links.append(a.get_text(' ', strip=True))
        state = self.page.evaluate('''() => {
          const e = document.querySelector('#primary_action');
          const visible = x => x.type !== 'hidden' && !!(x.offsetWidth || x.offsetHeight || x.getClientRects().length);
          const fields = [...document.querySelectorAll('form input,form select,form textarea')].filter(x => x.id !== 'primary_action' && visible(x)).map(x => ({
            field:x.id || x.name,type:x.tagName==='SELECT'?'select':x.type || x.tagName.toLowerCase(),
            label:document.querySelector('label[for="'+x.id+'"]')?.innerText || x.id || x.name,
            required:x.required,readonly:x.readOnly || x.disabled,
            value:x.tagName==='SELECT'?(x.value?x.selectedOptions[0]?.text:''):x.type==='checkbox'?x.checked:x.value,
            selected_text:x.tagName==='SELECT'?x.selectedOptions[0]?.text:null,
            valid:x.checkValidity(),
            options:x.tagName==='SELECT'?[...x.options].filter(o=>!o.disabled).map(o=>o.text):null}));
          const options=e?[...e.options].filter(o=>o.value && !o.disabled).map(o=>({label:o.text,selected:o.selected})):[];
          return {current_selection:e?.value?e.selectedOptions[0].text:'',option_states:options,
            options:options.map(o=>o.label),fields,submit_visible:!!document.querySelector('form button[type=submit]')};
        }''')
        state.update(page=page_name, visible_text=main.get_text(' ', strip=True), links=links)
        screen = self.output / ('page_%03d.png' % self.counter)
        self.page.screenshot(path=str(screen), full_page=True)
        wire.dump(screen.with_suffix('.json'), {'state': state, 'history_length': len(self.history), 'timing': 'before_next_proposed_action'})
        task = self.public or {'task_alias': self.case['alias'], 'user_goal': self._goal(), 'page_title': soup.title.get_text(' ', strip=True)}
        context = {'task': task, 'state': state, 'history': self.history}
        public_inputs.assert_public(context)
        images = [('chart_1', self.chart)] if self.chart else []
        return context, images + [('page_current', screen)]

    def _goal(self):
        soup = public_inputs.visible_soup(self.pages.get('home', self.page.content()))
        node = soup.select_one('main p.instruction') or soup.select_one('main section > p')
        return node.get_text(' ', strip=True) if node else ''

    def execute(self, action):
        self.budget.transition(action)
        kind = action.get('kind')
        try:
            if kind == 'open_link':
                target = self.page.get_by_role('link', name=action['label'], exact=True)
                href = target.get_attribute('href')
                if href not in {self.prefix + s for s in ('', '/dashboard', '/form')}:
                    raise ValueError('link_not_in_current_task')
                target.click()
                self.page.wait_for_load_state('networkidle')
            elif kind == 'select':
                self.page.locator('#primary_action').select_option(label=action['option'])
            elif kind in ('fill', 'check', 'select_field'):
                field = action['field']
                target = self.page.locator('[id=' + json.dumps(field) + ']')
                if not target.count():
                    target = self.page.locator('[name=' + json.dumps(field) + ']')
                if not target.is_visible() or target.get_attribute('type') == 'hidden' or target.get_attribute('readonly') is not None:
                    raise ValueError('field_not_editable_public')
                if field == 'primary_action':
                    raise ValueError('use_select_for_primary_action')
                if kind == 'fill':
                    target.fill(action['value'])
                elif kind == 'check':
                    target.set_checked(action['value'])
                else:
                    target.select_option(label=action['option'])
            elif kind == 'submit':
                validation = self.page.evaluate("() => [...document.querySelectorAll('form input,form select,form textarea')].filter(e=>e.type!=='hidden' && !e.checkValidity()).map(e=>({field:e.id || e.name,message:e.validationMessage}))")
                if validation:
                    result = {'ok': False, 'submitted': False, 'validation_errors': validation}
                    self._record(action, result)
                    return result
                self.page.locator('form button[type=submit]').click()
                self.page.wait_for_load_state('networkidle')
            else:
                raise ValueError('unsupported_action')
            selected = self.page.evaluate("() => { const s=document.querySelector('#primary_action'); return s?.value?s.selectedOptions[0].text:null; }")
            result = {'ok': True, 'submitted': urlparse(self.page.url).path == self.prefix + '/confirmation',
                      'observed_selection_after': selected}
        except Exception as exc:
            # Raw exception may contain paths or HTML: keep it offline only.
            wire.dump(self.output / ('execution_error_%03d.json' % len(self.history)), {'type': type(exc).__name__, 'detail': str(exc)})
            result = {'ok': False, 'submitted': False, 'error': 'action_not_available_or_invalid_for_current_visible_page'}
        self._record(action, result)
        return result

    def close(self):
        if self.browser:
            self.browser.close()
        if self.pw:
            self.pw.stop()
        if self.server:
            self.server.shutdown()
            self.thread.join(timeout=3)
            self.server.server_close()

    def __exit__(self, *args):
        self.close()
