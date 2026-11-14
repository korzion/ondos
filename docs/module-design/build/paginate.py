"""Pagination rules: python3 paginate.py in.docx out.docx"""
import sys
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
d=Document(sys.argv[1])
def keep_next(p,on=True):
    p.paragraph_format.keep_with_next=on
def is_image(p):
    return bool(p._p.findall('.//'+qn('w:drawing')))
body=d.element.body
blocks=list(body.iterchildren())
# map paragraph elements to python-docx paragraphs
from docx.text.paragraph import Paragraph
from docx.table import Table
for i,el in enumerate(blocks):
    if el.tag==qn('w:p'):
        p=Paragraph(el,d)
        p.paragraph_format.widow_control=True
        nxt=blocks[i+1] if i+1<len(blocks) else None
        txt=p.text.strip()
        # image stays with its caption
        if is_image(p): keep_next(p)
        # intro sentence ending with ':' stays with the following table/list
        elif txt.endswith(':') and nxt is not None: keep_next(p)
        # short bold labels such as **Rules** / **Notes** / step-by-step headings
        elif txt and len(txt)<60 and all(r.bold for r in p.runs if r.text.strip()) and p.runs: keep_next(p)
        # info lines "Writer: ... Rate: ..." stay with their field table
        elif txt.startswith(('Writer:','Rate:')): keep_next(p)
    elif el.tag==qn('w:tbl'):
        t=Table(el,d)
        rows=t.rows
        for r in rows:
            trPr=r._tr.get_or_add_trPr()
            c=OxmlElement('w:cantSplit'); c.set(qn('w:val'),'true'); trPr.append(c)
        if len(rows)<=5:
            for r in rows[:-1]:
                for c in r.cells:
                    for p in c.paragraphs: keep_next(p)
        else:
            # keep the header and the first two rows together
            for r in list(rows[:2]):
                for c in r.cells:
                    for p in c.paragraphs: keep_next(p)
# cap figure height so a figure fits on a partly filled page
from docx.shared import Cm
MAXH=Cm(10.5)
for shp in d.inline_shapes:
    if shp.height>MAXH:
        r=MAXH/shp.height; shp.width=int(shp.width*r); shp.height=MAXH
for p in d.paragraphs:
    if is_image(p): p.alignment=1
import re as _re
for p in d.paragraphs:
    sn=p.style.name.lower() if p.style is not None else ''
    t=p.text.strip()
    if sn.startswith('heading') and (t.startswith(('Part I ','Part I –','Part II','Appendix','References')) or _re.match(r'^[B-E] – ',t)):
        p.paragraph_format.page_break_before=True
d.save(sys.argv[2]); print('paginated')
