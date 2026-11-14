import sys
from docx import Document
from docx.shared import Pt, Emu, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
d=Document(sys.argv[1])
sec=d.sections[0]; from docx.shared import Cm; tw=(sec.page_width or Cm(21))-(sec.left_margin or Cm(2))-(sec.right_margin or Cm(2))
def cell_shade(c,hexcol):
    tcPr=c._tc.get_or_add_tcPr(); sh=OxmlElement('w:shd'); sh.set(qn('w:val'),'clear'); sh.set(qn('w:color'),'auto'); sh.set(qn('w:fill'),hexcol); tcPr.append(sh)
def borders(t):
    tblPr=t._tbl.tblPr; b=OxmlElement('w:tblBorders')
    for e in ('top','left','bottom','right','insideH','insideV'):
        x=OxmlElement('w:'+e); x.set(qn('w:val'),'single'); x.set(qn('w:sz'),'4'); x.set(qn('w:space'),'0'); x.set(qn('w:color'),'C9D3DF'); b.append(x)
    old=tblPr.find(qn('w:tblBorders'))
    if old is not None: tblPr.remove(old)
    tblPr.append(b)
for t in d.tables:
    borders(t)
    mar=OxmlElement('w:tblCellMar')
    for side,v in (('top',40),('bottom',40),('left',80),('right',80)):
        e=OxmlElement('w:'+side); e.set(qn('w:w'),str(v)); e.set(qn('w:type'),'dxa'); mar.append(e)
    t._tbl.tblPr.append(mar)
    rows=t.rows; n=len(t.columns)
    lens=[0]*n; cnt=[0]*n
    for r in rows:
        for i,c in enumerate(r.cells[:n]):
            L=len(c.text); lens[i]=max(lens[i], min(L,80)) if False else lens[i]+min(L,120); cnt[i]+=1
    avg=[max(4,lens[i]/max(cnt[i],1)) for i in range(n)]
    longest=[max((len(wd) for r in rows for wd in r.cells[i].text.split()),default=3) for i in range(n)]
    w=[a**0.8 for a in avg]; tot=sum(w)
    twc=tw/635/1440*2.54  # text width in cm
    minf=[min(0.35,(L*0.19+0.3)/twc) for L in longest]
    frac=[x/tot for x in w]
    for _ in range(5):
        short=[i for i in range(n) if frac[i]<minf[i]]
        if not short: break
        fixed=sum(minf[i] for i in short); free=[i for i in range(n) if i not in short]; fs=sum(frac[i] for i in free) or 1
        frac=[minf[i] if i in short else frac[i]*(1-fixed)/fs for i in range(n)]
    w=frac; tot=1.0
    # fixed layout
    tblPr=t._tbl.tblPr
    lay=OxmlElement('w:tblLayout'); lay.set(qn('w:type'),'fixed'); tblPr.append(lay)
    tblW=tblPr.find(qn('w:tblW'))
    if tblW is None: tblW=OxmlElement('w:tblW'); tblPr.append(tblW)
    tblW.set(qn('w:w'),str(int(tw/635))); tblW.set(qn('w:type'),'dxa')
    grid=t._tbl.tblGrid
    for i,gc in enumerate(grid.findall(qn('w:gridCol'))):
        gc.set(qn('w:w'),str(int(tw*w[i]/tot/635)))
    for ri,r in enumerate(rows):
        for i,c in enumerate(r.cells[:n]):
            c.width=Emu(int(tw*w[i]/tot))
            for p in c.paragraphs:
                p.paragraph_format.space_after=Pt(1); p.paragraph_format.space_before=Pt(1); p.paragraph_format.line_spacing=1.0
                for run in p.runs:
                    run.font.size=Pt(8.5)
                    if ri==0:
                        run.font.bold=True; run.font.color.rgb=RGBColor.from_string('FFFFFF')
            if ri==0: cell_shade(c,'1F3864')
            elif ri%2==0: cell_shade(c,'F2F5F9')
    # repeat header row
    trPr=rows[0]._tr.get_or_add_trPr(); h=OxmlElement('w:tblHeader'); h.set(qn('w:val'),'true'); trPr.append(h)
d.save(sys.argv[2]); print(len(d.tables),'tables styled')
