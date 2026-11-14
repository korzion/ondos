"""One-step build: python3 build.py <source.md> <resource_dir> <out_dir>
Makes Ondos_Module_Design.docx and .pdf (cover, TOC, page breaks, styled tables)."""
import re,subprocess,sys,os
src,res,out=sys.argv[1],sys.argv[2],sys.argv[3]
here=os.path.dirname(os.path.abspath(__file__))
subprocess.run(['python3','-I',os.path.join(here,'prep.py'),src,'doc.md'],check=True,stdout=subprocess.DEVNULL)
s=open('doc.md',encoding='utf-8').read()
def ox(x): return '\n```{=openxml}\n'+x+'\n```\n\n'
PB='<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
def para(text,size,color='1F3864',bold=False,before=0,after=120,italic=False):
    rpr=f'<w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/>{"<w:b/>" if bold else ""}{"<w:i/>" if italic else ""}<w:color w:val="{color}"/><w:sz w:val="{size*2}"/></w:rPr>'
    return f'<w:p><w:pPr><w:spacing w:before="{before}" w:after="{after}"/></w:pPr><w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
# cover: replace the title block
m=re.match(r'# (.+?)\n\n(.+?)\n\n(.+?)\n\n(.+?)\n\n',s)
title,company,course,date=m.groups()
title=title.split(' {#')[0]
cover=(para('',12,before=1100)+para('MODULE DESIGN DOCUMENT',12,'2F5496',True,0,120)+
       para(title,34,'1F3864',True,0,200)+
       '<w:p><w:pPr><w:pBdr><w:bottom w:val="single" w:sz="18" w:space="1" w:color="1F3864"/></w:pBdr><w:spacing w:after="360"/></w:pPr></w:p>'+
       para(company,14,'222222',True,0,80)+para(course,12,'404040',False,0,80)+para(date,12,'404040',False,0,360))
s=ox(cover)+s[m.end():]
s=s.replace('**Modules and members**',ox('<w:p><w:pPr><w:spacing w:before="0" w:after="120"/></w:pPr></w:p>')+'**Modules and members**',1)
toc=PB+'<w:p><w:pPr><w:pStyle w:val="TOCHeading"/></w:pPr><w:r><w:t>Contents</w:t></w:r></w:p><w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "2-3" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>Contents</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
s=s.replace('## Part I – System',ox(toc)+'## Part I – System',1)
s=re.sub(r'!\[[^\]]*\]\(([^)]+)\)\{width=100%\}\n\n(Figure \d+ – [^\n]+)',lambda m: f'![{m.group(2)}]({m.group(1)}){{width=100%}}',s)
open('doc2.md','w',encoding='utf-8').write(s)
subprocess.run(['pandoc','doc2.md','-o','raw.docx','--reference-doc',os.path.join(here,'ref.docx'),'--resource-path',res],check=True)
subprocess.run(['python3',os.path.join(here,'style.py'),'raw.docx','styled.docx'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['python3',os.path.join(here,'paginate.py'),'styled.docx','paged.docx'],check=True,stdout=subprocess.DEVNULL)
subprocess.run(['timeout','300','python3',os.path.join(here,'topdf.py'),'paged.docx',os.path.join(out,'Ondos_Module_Design.pdf'),os.path.join(out,'Ondos_Module_Design.docx')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print('done')
