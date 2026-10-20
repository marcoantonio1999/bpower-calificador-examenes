import io
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zipfile
from xml.etree import ElementTree as ET
from grader import (GradingError, MODEL, validate_key, load_key, read_pdf, key_from_solved_pdf,
                    extract_candidate, build_request, call_openai, validate_ai_grades, grade_candidate, process_folder)


def sample_key(opened=False):
    return validate_key({'title':'Examen ficticio QA', 'questions':[
        dict(id='1',type='choice',expected='B',points=2),
        dict(id='2',type='open' if opened else 'choice',expected='4' if opened else 'C',
             prompt='¿Cuánto es 2 + 2?' if opened else '',points=3,rubric='Equivalencia numérica.' if opened else '')]})


def data(a='/B',b='/C'):
    return {'fields':dict(nombre_completo='Persona ficticia QA',correo_electronico='qa@example.invalid',
                           telefono='0012345678',fecha='20/10/2026',pregunta_01=a,pregunta_02=b),'text':'Texto ficticio.'}


def make_pdf(path, opened=False, a='B', b='C', teacher=False):
    from reportlab.pdfgen import canvas
    from pypdf import PdfReader, PdfWriter
    c=canvas.Canvas(str(path)); c.setTitle('PDF ficticio de prueba; no es examen real')
    c.drawString(60,800,'Examen ficticio QA - No contactar')
    y=760
    for name,value in [('nombre_completo','Persona ficticia QA'),('correo_electronico','qa@example.invalid'),('telefono','0012345678'),('fecha','20/10/2026')]:
        c.acroForm.textfield(name=name,value=value,x=60,y=y,width=300,height=20); y-=30
    for q,value in [('pregunta_01',a),('pregunta_02',b)]:
        if q=='pregunta_02' and opened:
            c.acroForm.textfield(name=q,value=value,x=60,y=y,width=300,height=25); y-=40
        else:
            for i,letter in enumerate('ABCD'):
                c.acroForm.radio(name=q,value=letter,selected=(letter==value),x=60+i*50,y=y)
            y-=40
    c.showPage();c.save()


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self): self.temp.cleanup()

    def test_mc_correct_weighted_no_api(self):
        with patch('grader.call_openai',side_effect=AssertionError('No network')):
            r=grade_candidate(data(),sample_key())
        self.assertEqual((r['score'],r['maximum'],r['grade']),(5,5,10))
        self.assertEqual(r['phone'],'0012345678')

    def test_mc_partial_weighted(self):
        r=grade_candidate(data('/A','/C'),sample_key())
        self.assertEqual((r['score'],r['grade']),(3,6))

    def test_valid_blank_is_zero(self):
        r=grade_candidate(data('/Off','/Off'),sample_key())
        self.assertEqual((r['grade'],r['answered']),(0,0))

    def test_missing_field_not_zero(self):
        d=data(); del d['fields']['pregunta_02']
        r=grade_candidate(d,sample_key())
        self.assertIsNone(r['grade']); self.assertEqual(r['status'],'Revisar')

    def test_ambiguous_choice_manual(self):
        r=grade_candidate(data('/A y B'),sample_key())
        self.assertIsNone(r['grade'])

    def test_identity_missing_review(self):
        d=data();d['fields']['nombre_completo']=''
        self.assertEqual(grade_candidate(d,sample_key())['status'],'Revisar')

    def test_key_invalid_variants(self):
        for key in [{},{'questions':[]},{'questions':[dict(id='1',type='choice',expected='')]},
                    {'questions':[dict(id='1',type='open',expected='Sí')]},
                    {'questions':[dict(id='1',type='choice',expected='A',points=float('nan'))]}]:
            with self.subTest(key=key),self.assertRaises(GradingError): validate_key(key)

    def test_duplicate_ids_rejected(self):
        k=sample_key();k['questions'][1]['id']='1'
        with self.assertRaises(GradingError): validate_key(k)

    def test_duplicate_fields_rejected(self):
        k=sample_key();k['questions'][1]['field']='pregunta_01'
        with self.assertRaises(GradingError):validate_key(k)

    def test_csv_key(self):
        path=self.root/'key.csv';path.write_text('id,type,expected,points,prompt,rubric,field\n1,choice,B,2,,,pregunta_01\n',encoding='utf-8-sig')
        self.assertEqual(load_key(path)['questions'][0]['points'],2)

    def test_plain_text_explicit_answers(self):
        d={'fields':{},'text':'Nombre completo: Persona QA\nCorreo: qa@example.invalid\n1. Pregunta de prueba\nRespuesta: B\n2. ¿Cuánto es 2 + 2?\nRespuesta: 4'}
        identity,answers,recognized=extract_candidate(d,sample_key(True))
        self.assertEqual(answers,{'1':'B','2':'4'});self.assertEqual(identity['name'],'Persona QA')

    def test_plain_no_answers_manual(self):
        r=grade_candidate({'fields':{},'text':'1. ¿Pregunta?\nA. Respuesta\nB. Respuesta'},sample_key())
        self.assertIsNone(r['grade'])

    def test_request_text_only_low_no_identity(self):
        payload=build_request(sample_key(True)['questions'][1:],{'2':'4'})
        self.assertEqual(payload['model'],MODEL);self.assertEqual(payload['reasoning'],{'effort':'low'})
        self.assertFalse(payload['store'])
        self.assertNotIn('qa@example',str(payload));self.assertNotIn('input_file',str(payload))
        self.assertNotIn('api_key',str(payload))

    def test_ai_mock_contract_and_partial_score(self):
        def fake(key,qs,answers): return {'grades':{'2':{'points':1.5,'reason':'Crédito parcial ficticio.','review':False}},'model':MODEL}
        r=grade_candidate(data('/B','cuatro'),sample_key(True),api_key='fake-only',ai_enabled=True,ai_call=fake)
        self.assertEqual(r['grade'],7)

    def test_open_no_key_pending(self):
        r=grade_candidate(data('/B','4'),sample_key(True),ai_enabled=True)
        self.assertIsNone(r['grade']);self.assertIn('API key',r['ai']['error'])

    def test_blank_open_no_paid_call(self):
        r=grade_candidate(data('/B',''),sample_key(True),api_key='fake',ai_enabled=True,
                          ai_call=lambda *args: self.fail('Must not call'))
        self.assertEqual(r['grade'],4)

    def test_ai_schema_rejects_bad_grades(self):
        q=sample_key(True)['questions'][1:]
        for grades in [[],[dict(id='3',points=1,reason='x',review=False)],
                       [dict(id='2',points=99,reason='x',review=False)],
                       [dict(id='2',points=float('nan'),reason='x',review=False)],
                       [dict(id='2',points=True,reason='x',review=False)],
                       [dict(id='2',points=1,reason='',review=False)]]:
            with self.subTest(grades=grades),self.assertRaises(GradingError): validate_ai_grades({'grades':grades},q)

    def test_http_error_no_retry_no_secret(self):
        calls=[]
        def opener(req,timeout):
            calls.append(req);raise urllib.error.HTTPError(req.full_url,401,'SECRET NEVER PRINT',{},None)
        with self.assertRaises(GradingError) as caught: call_openai('fake-secret',sample_key(True)['questions'][1:],{'2':'4'},opener)
        self.assertEqual(len(calls),1);self.assertNotIn('fake-secret',str(caught.exception));self.assertNotIn('SECRET',str(caught.exception))

    def test_responses_real_shape_via_fake_transport(self):
        payload={'status':'completed','model':MODEL,'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps({'grades':[dict(id='2',points=3,reason='Equivalente.',review=False)]})}]}],'usage':{'input_tokens':80,'output_tokens':50}}
        def opener(request,timeout):
            actual=json.loads(request.data);self.assertEqual(actual['reasoning']['effort'],'low')
            self.assertEqual(request.full_url,'https://api.openai.com/v1/responses')
            return io.BytesIO(json.dumps(payload).encode())
        result=call_openai('fake-test',sample_key(True)['questions'][1:],{'2':'4'},opener)
        self.assertEqual(result['grades']['2']['points'],3)

    def test_cache_avoids_paid_repeats(self):
        cache=sqlite3.connect(':memory:');cache.execute('CREATE TABLE grades (digest TEXT PRIMARY KEY,result TEXT)')
        calls=[]
        def fake(*args):
            calls.append(1);return {'grades':{'2':dict(points=3,reason='Correcta.',review=False)},'input_tokens':10,'output_tokens':10,'model':MODEL}
        for i in range(2): r=grade_candidate(data('/B','4'),sample_key(True),api_key='fake',ai_enabled=True,ai_call=fake,cache=cache)
        self.assertEqual(len(calls),1);self.assertTrue(r['ai']['cached']);self.assertEqual(r['ai']['input_tokens'],0)
        key=sample_key(True);key['questions'][1]['rubric']='Criterio nuevo'
        grade_candidate(data('/B','4'),key,api_key='fake',ai_enabled=True,ai_call=fake,cache=cache)
        self.assertEqual(len(calls),2);cache.close()

    def test_read_synthetic_pdf_and_solved_key(self):
        pdf=self.root/'teacher.pdf';make_pdf(pdf)
        d=read_pdf(pdf);self.assertEqual(d['fields']['pregunta_01'],'/B')
        self.assertEqual(len(key_from_solved_pdf(pdf)['questions']),2)

    def test_bad_pdf(self):
        pdf=self.root/'bad.pdf';pdf.write_bytes(b'not pdf')
        with self.assertRaises(GradingError):read_pdf(pdf)

    def test_folder_duplicates_corrupt_and_excel(self):
        make_pdf(self.root/'a.pdf');(self.root/'duplicate.pdf').write_bytes((self.root/'a.pdf').read_bytes())
        (self.root/'broken.pdf').write_bytes(b'broken')
        result=process_folder(self.root,sample_key())
        self.assertEqual(result['count'],3);self.assertEqual(result['review'],1)
        self.assertTrue(Path(result['excel']).exists())
        self.assertIn('Duplicado omitido',[r['status'] for r in result['results']])
        with zipfile.ZipFile(result['excel']) as z:
            ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            sheet=ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
            self.assertEqual(sheet.find('.//m:c[@r="I2"]/m:v',ns).text,'10.0')
            self.assertEqual(sheet.find('.//m:c[@r="C2"]/m:is/m:t',ns).text,'0012345678')

    def test_api_error_circuit_breaker_preserves_mc(self):
        make_pdf(self.root/'a.pdf',opened=True,b='4');make_pdf(self.root/'b.pdf',opened=True,b='cuatro')
        calls=[]
        def fake(*args):calls.append(1);raise GradingError('OpenAI HTTP 503: fallo. No se reintentó.')
        r=process_folder(self.root,sample_key(True),api_key='fake-secret',ai_enabled=True,ai_call=fake)
        self.assertEqual(len(calls),1)
        self.assertEqual([x['score'] for x in r['results']],[2,2])
        self.assertTrue(all(x['grade'] is None for x in r['results']))
        self.assertNotIn('fake-secret',(Path(r['output'])/'avance.json').read_text())

    def test_excel_formula_injection_safe(self):
        from excel_export import export_results
        path=self.root/'test.xlsx'
        export_results([dict(file='=BAD()',name='=HYPERLINK("bad")',status='Revisar')],path)
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                root=ET.fromstring(z.read(name));self.assertFalse(root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}f'))

    def test_pause_keeps_result(self):
        make_pdf(self.root/'a.pdf');make_pdf(self.root/'b.pdf',a='A')
        calls=[]
        r=process_folder(self.root,sample_key(),progress=lambda *args:calls.append(1),cancelled=lambda:len(calls)>0)
        self.assertEqual(r['count'],1);self.assertTrue(Path(r['excel']).exists())


if __name__=='__main__': unittest.main()
