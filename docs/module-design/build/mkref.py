from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.enum.text import WD_ALIGN_PARAGRAPH
NAVY='1F3864'; BLUE='2F5496'
d=Document('ref0.docx')
def font(st,size=None,color=None,bold=None,italic=None):
    f=st.font; f.name='Calibri'
    rpr=st.element.get_or_add_rPr(); rf=rpr.find(qn('w:rFonts'))
    if rf is None: rf=OxmlElement('w:rFonts'); rpr.append(rf)
    for a in ('w:ascii','w:hAnsi','w:cs','w:eastAsia'): rf.set(qn(a),'Calibri')
    for a in ('w:asciiTheme','w:hAnsiTheme','w:cstheme','w:eastAsiaTheme'):
        if rf.get(qn(a)) is not None: del rf.attrib[qn(a)]
    if size: f.size=Pt(size)
    if color: f.color.rgb=RGBColor.from_string(color)
    if bold is not None: f.bold=bold
    if italic is not None: f.italic=italic
def spacing(st,before,after,line=None,keep=False):
    pf=st.paragraph_format; pf.space_before=Pt(before); pf.space_after=Pt(after)
    if line: pf.line_spacing=line
    if keep: pf.keep_with_next=True
def bottom_border(st,color,sz=8):
    ppr=st.element.get_or_add_pPr(); b=OxmlElement('w:pBdr'); e=OxmlElement('w:bottom')
    e.set(qn('w:val'),'single'); e.set(qn('w:sz'),str(sz)); e.set(qn('w:space'),'4'); e.set(qn('w:color'),color); b.append(e); ppr.append(b)
S0=d.styles
class _S:
    def __getitem__(self,n):
        for st in S0:
            if st.name in (n,n.lower()) or st.style_id==n.replace(' ',''):
                return st
        raise KeyError(n)
S=_S()
for n in ['Normal','Body Text','First Paragraph','Compact','Block Text']:
    try: font(S[n],10.5,'222222'); spacing(S[n],0,6,1.12)
    except KeyError: pass
try: spacing(S['Compact'],0,2,1.1)
except KeyError: pass
spec={'Title':(28,NAVY,True),'Heading 1':(26,NAVY,True),'Heading 2':(20,NAVY,True),'Heading 3':(15,BLUE,True),'Heading 4':(12,BLUE,True),'Heading 5':(11,NAVY,True)}
for n,(sz,c,b) in spec.items():
    try: font(S[n],sz,c,b,False)
    except KeyError: pass
spacing(S['Heading 2'],18,10,keep=True); bottom_border(S['Heading 2'],NAVY,12)
spacing(S['Heading 3'],16,6,keep=True); bottom_border(S['Heading 3'],'B7C3D0',4)
spacing(S['Heading 4'],12,4,keep=True)
try: spacing(S['Heading 5'],10,3,keep=True)
except KeyError: pass
for n in ['Image Caption','Caption','Table Caption']:
    try:
        font(S[n],9,'555555',False,True); S[n].paragraph_format.alignment=WD_ALIGN_PARAGRAPH.CENTER; spacing(S[n],2,12)
    except KeyError: pass
try: S['Captioned Figure'].paragraph_format.alignment=WD_ALIGN_PARAGRAPH.CENTER
except KeyError: pass
try:
    font(S['TOC Heading'],20,NAVY,True)
except KeyError: pass
for n in ['Hyperlink']:
    try: S[n].font.color.rgb=RGBColor.from_string(BLUE)
    except KeyError: pass
sec=d.sections[0]
sec.page_width=Cm(21); sec.page_height=Cm(29.7); sec.left_margin=sec.right_margin=Cm(2.2); sec.top_margin=Cm(2); sec.bottom_margin=Cm(2)
for p in sec.header.paragraphs: p.text=''
fp=sec.footer.paragraphs[0]; fp.text=''; fp.alignment=WD_ALIGN_PARAGRAPH.CENTER
def fld(p,code):
    r=p.add_run(); b=OxmlElement('w:fldChar'); b.set(qn('w:fldCharType'),'begin'); r._r.append(b)
    r2=p.add_run(); it=OxmlElement('w:instrText'); it.set(qn('xml:space'),'preserve'); it.text=code; r2._r.append(it)
    r3=p.add_run(); e=OxmlElement('w:fldChar'); e.set(qn('w:fldCharType'),'end'); r3._r.append(e)
    for r in (r,r2,r3): r.font.size=Pt(9); r.font.color.rgb=RGBColor.from_string('7F7F7F')
fld(fp,' PAGE ')
# first page different (no number on cover)
sp=sec._sectPr; t=OxmlElement('w:titlePg'); sp.append(t)
d.save('ref.docx'); print('ref ok')
