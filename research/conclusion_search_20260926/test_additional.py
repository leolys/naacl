import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('additional_tests_runtime',HERE/'run_additional.py')
run=importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class FakeHTTP:
    def __init__(self):
        buffer=io.BytesIO()
        Image.new('RGB',(16,12),(20,40,60)).save(buffer,format='JPEG')
        self.body=buffer.getvalue()
        self.urls=[]
    def get(self,url,**kwargs):
        self.urls.append((url,kwargs))
        return type('Response',(),{'status_code':200,'headers':{'Content-Type':'image/jpeg'},'content':self.body})()


class AdditionalTests(unittest.TestCase):
    def test_chart_conversion_is_complete_pixel_identical_and_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=run.search.read(HERE/'config.json')
            ledger=run.base.Ledger(root,config)
            api=run.FullChartAPI(config,ledger)
            api.http=FakeHTTP()
            folder=root/'official140/symmetric_hypotheses/hypothesis_00'
            folder.parent.mkdir(parents=True)
            context={'state':{'url':'http://127.0.0.1:123/task/pub001/form'}}
            image=api.chart_image(context,folder)
            self.assertEqual(api.chart_image(context,folder),image)
            self.assertEqual(len(api.http.urls),1)
            self.assertEqual(api.http.urls[0][0],'http://127.0.0.1:123/task/pub001/chart')
            self.assertFalse(api.http.urls[0][1]['allow_redirects'])
            with Image.open(image) as decoded:
                self.assertEqual(decoded.size,(16,12))
                with Image.open(io.BytesIO(api.http.body)) as original:
                    self.assertEqual(decoded.convert('RGB').tobytes(),original.convert('RGB').tobytes())
            self.assertEqual(ledger.data['browser_operations'],1)
            self.assertEqual(ledger.data['request_attempts'],0)

    def test_chart_cache_never_crosses_arms_when_ephemeral_port_repeats(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            config=run.search.read(HERE/'config.json')
            api=run.FullChartAPI(config,run.base.Ledger(root,config))
            api.http=FakeHTTP()
            context={'state':{'url':'http://127.0.0.1:123/task/pub001/form'}}
            files=[]
            for arm in ('official140','clean140'):
                folder=root/arm/'symmetric_hypotheses/hypothesis_00'
                folder.parent.mkdir(parents=True)
                files.append(api.chart_image(context,folder))
            self.assertEqual(len(api.http.urls),2)
            self.assertNotEqual(files[0],files[1])

    def test_external_other_task_and_query_urls_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            config=run.search.read(HERE/'config.json')
            api=run.FullChartAPI(config,run.base.Ledger(Path(directory),config))
            api.http=FakeHTTP()
            for url in ['http://example.org/task/pub001/form','http://127.0.0.1:123/task/pub002/form',
                        'http://127.0.0.1:123/task/pub001/form?view=clean']:
                with self.assertRaises(ValueError):
                    api.chart_image({'state':{'url':url}},Path(directory)/'arm/branch/hypothesis')
            self.assertEqual(api.http.urls,[])

    def test_transfer_verifies_six_without_dropping_or_repairing(self):
        records=[{'id':'c%d'%i} for i in range(6)]
        response={'checks':[{'chain_id':r['id'],'O_status':'supported','B_status':'uncertain',
                            'inference':'valid','reason':'test','visible_evidence':[]} for r in records],
                  'summary':'test'}
        class API:
            def call(self,folder,system,context,image,schema,stage):
                self.schema=schema
                return json.dumps(response)
        api=API()
        with tempfile.TemporaryDirectory() as directory:
            parsed=run.transfer_verify(api,Path(directory)/'verify',{'chains':records},'unused.png')
        self.assertEqual(len(parsed['checks']),6)
        self.assertEqual(api.schema['properties']['checks']['maxItems'],6)
        self.assertEqual(run.base.SCHEMAS['verify']['properties']['checks']['maxItems'],5)


if __name__=='__main__':
    unittest.main()
