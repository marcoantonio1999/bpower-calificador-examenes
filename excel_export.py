"""Minimal OOXML writer for the desktop exporter; no Excel installation needed."""
import math
import re
import zipfile
from xml.sax.saxutils import escape


def column(n):
    value = ''
    while n:
        n, d = divmod(n-1, 26)
        value = chr(65+d) + value
    return value


def xml(value):
    return escape(re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]', '', str(value)))


def worksheet(rows, widths):
    body = []
    for i, row in enumerate(rows, 1):
        cells = []
        for j, value in enumerate(row, 1):
            ref = f'{column(j)}{i}'
            if value is None:
                cells.append(f'<c r="{ref}"/>')
            elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                cells.append(f'<c r="{ref}" s="2"><v>{value}</v></c>')
            else:
                value = str(value)
                if len(value.encode('utf-16-le'))//2 > 32767:
                    value = value[:15000] + '\n[Texto largo: consulta avance.json.]'
                cells.append(f'<c r="{ref}" t="inlineStr" s="{1 if i == 1 else 0}"><is><t xml:space="preserve">{xml(value)}</t></is></c>')
        body.append(f'<row r="{i}" ht="{32 if i==1 else 48}" customHeight="1">' + ''.join(cells) + '</row>')
    cols = ''.join(f'<col min="{i}" max="{i}" width="{w}" customWidth="1"/>' for i,w in enumerate(widths,1))
    last = f'{column(len(rows[0]))}{len(rows)}'
    return (f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:{last}"/>'
        '<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane xSplit="1" ySplit="1" topLeftCell="B2" activePane="bottomRight" state="frozen"/></sheetView></sheetViews>'
        f'<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData><autoFilter ref="A1:{last}"/></worksheet>')


def export_results(results, destination):
    summary = [['Nombre', 'Correo', 'Teléfono', 'Fecha del examen (original)', 'Archivo PDF', 'Estado',
                'Puntos obtenidos (parciales si faltan)', 'Puntos posibles', 'Calificación / 10',
                'Respondidas', 'Observaciones', 'Modelo IA', 'Tokens entrada (esta ejecución)', 'Tokens salida (esta ejecución)', 'IA desde caché']]
    details = [['Archivo PDF', 'Pregunta', 'Tipo', 'Respuesta recibida', 'Respuesta esperada',
                'Puntos', 'Máximo', 'Explicación', 'Requiere revisión']]
    for row in results:
        ai = row.get('ai') or {}
        summary.append([row.get('name',''),row.get('email',''),row.get('phone',''),row.get('date',''),
            row['file'],row['status'],row.get('score'),row.get('maximum'),row.get('grade'),row.get('answered'),
            row.get('observations',''),ai.get('model',''),ai.get('input_tokens',0),ai.get('output_tokens',0),'Sí' if ai.get('cached') else 'No'])
        for d in row.get('details',[]):
            details.append([row['file'],d['id'],'Abierta' if d['type']=='open' else 'Opción múltiple',d['answer'],d['expected'],
                            d['points'],d['max_points'],d['reason'],'Sí' if d['review'] else 'No'])
    sheets = [worksheet(summary,[32,36,24,28,38,22,25,20,20,18,65,24,22,22,18]),
              worksheet(details,[38,14,22,65,65,14,14,70,22])]
    styles = ('<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><sz val="11"/><name val="Arial"/><b/><color rgb="FFFFFFFF"/></font></fonts>'
        '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF2357A5"/><bgColor indexed="64"/></patternFill></fill></fills>'
        '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="3">'
        '<xf fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf>'
        '<xf fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
        '<xf numFmtId="2" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"><alignment vertical="center" horizontal="right"/></xf>'
        '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    parts = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in (1,2))+'</Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Calificaciones" sheetId="1" r:id="rId1"/><sheet name="Detalle" sheetId="2" r:id="rId2"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in (1,2))+'<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': styles, **{f'xl/worksheets/sheet{i}.xml': s for i,s in enumerate(sheets,1)}}
    with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name,'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+content)
