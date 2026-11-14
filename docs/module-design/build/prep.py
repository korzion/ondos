import re,sys
s=open(sys.argv[1],encoding='utf-8').read()
L=s.split('\n'); out=[]; ids={}
for l in L:
    m=re.match(r'^(#{2,4}) (\d+)\. (.*)$',l) or re.match(r'^(#{3,4}) (\d+\.\d+) (.*)$',l) or re.match(r'^(#{3,4}) ([A-E]\.\d+) (.*)$',l) or re.match(r'^(#{2,4}) (IF-\d\d) (.*)$',l)
    if m:
        key=m.group(2); hid='s-'+key.lower().replace('.','-')
        ids[key]=hid; l=f'{l} {{#{hid}}}'
    if re.match(r'^!\[.*\]\(.*\)$',l): l=l+'{width=100%}'
    out.append(l)
s='\n'.join(out)
def link(t):
    if t.startswith('#') or t.startswith('|') and False: return t
    t=re.sub(r'\b(section|Section|sections) (\d+\.\d+|\d+)\b(?!\])',lambda m: f'[{m.group(0)}](#{ids[m.group(2)]})' if m.group(2) in ids else m.group(0),t)
    t=re.sub(r'(?<![\[\w/-])(IF-0\d)\b(?![\]\w])',lambda m: f'[{m.group(1)}](#{ids[m.group(1)]})' if m.group(1) in ids else m.group(0),t)
    t=re.sub(r'(?<![\[\w./-])([A-E]\.\d{1,2})\b(?![\]\w.])',lambda m: f'[{m.group(1)}](#{ids[m.group(1)]})' if m.group(1) in ids else m.group(0),t)
    return t
# PLACEHOLDER-ESC: keep <module>, <program> ... visible (pandoc would drop them as HTML)
s=s.replace('<br>','`<w:r><w:br/></w:r>`{=openxml}')
s=re.sub(r'<(?!br>|/?w:)([A-Za-z_][A-Za-z0-9_ .-]*)>',lambda m: '&lt;'+m.group(1)+'&gt;',s)
res=[]
for l in s.split('\n'):
    res.append(l if l.startswith('#') or l.startswith('![') else link(l))
open(sys.argv[2],'w',encoding='utf-8').write('\n'.join(res))
print(len(ids),'anchors')
