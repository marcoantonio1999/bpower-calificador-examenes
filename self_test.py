"""Packaged offline end-to-end test, also prepares fictitious UI fixtures."""
import json
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, ArrayObject, TextStringObject, NumberObject
from grader import validate_key, process_folder


def fixture(path, second='C'):
    writer=PdfWriter();page=writer.add_blank_page(612,792)
    fields=ArrayObject()
    data={'nombre_completo':'Persona ficticia QA','correo_electronico':'qa@example.invalid',
          'telefono':'0012345678','fecha':'20/10/2026','pregunta_01':'B','pregunta_02':second}
    for index,(name,value) in enumerate(data.items()):
        field=DictionaryObject({NameObject('/Type'):NameObject('/Annot'),NameObject('/Subtype'):NameObject('/Widget'),
             NameObject('/FT'):NameObject('/Tx'),NameObject('/T'):TextStringObject(name),NameObject('/V'):TextStringObject(value),
             NameObject('/Rect'):ArrayObject([NumberObject(n) for n in (40,720-index*40,400,742-index*40)])})
        fields.append(writer._add_object(field))
    page[NameObject('/Annots')]=fields
    writer.root_object[NameObject('/AcroForm')]=writer._add_object(DictionaryObject({NameObject('/Fields'):fields}))
    writer.write(path)


def run(path):
    folder=path.parent/'examenes-ficticios';folder.mkdir(parents=True,exist_ok=True)
    fixture(folder/'persona-a.pdf');fixture(folder/'persona-b.pdf','A')
    key=validate_key({'title':'Prueba ficticia QA - no es clave de examen real','questions':[
        dict(id='1',type='choice',expected='B',points=2),dict(id='2',type='choice',expected='C',points=3)]})
    (path.parent/'clave-ficticia.json').write_text(json.dumps(key,ensure_ascii=False,indent=2),encoding='utf-8')
    result=process_folder(folder,key)
    assert [row['grade'] for row in result['results']]==[10,4]
    assert all(row['phone']=='0012345678' for row in result['results'])
    assert Path(result['excel']).exists()
    path.write_text(json.dumps({'status':'OK','synthetic_grades':[10,4],'excel':result['excel']},indent=2),encoding='utf-8')
