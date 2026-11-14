"""Consistency check for ondos.md. Usage: python3 lint.py ondos.md"""
import re, sys, collections
L = open(sys.argv[1], encoding='utf-8').read().split('\n')

def sec(i):
    for j in range(i, -1, -1):
        if L[j].startswith('#'): return L[j].lstrip('# ')[:40]
    return '?'

def cells(l): return [c.strip() for c in l.strip().strip('|').split('|')]
def norm(x): return re.sub(r'\s+', ' ', x.replace('`', '').replace('\\*', '*')).strip().lower()

# 1. same field name with different type or unit
fields = collections.defaultdict(list)
hdr = None
for i, l in enumerate(L):
    if not l.startswith('|'): hdr = None; continue
    c = cells(l)
    if hdr is None: hdr = [norm(x) for x in c]; continue
    if l.startswith('| ---'): continue
    if 'field' in hdr[:1] and 'type' in hdr:
        ti = hdr.index('type'); ui = hdr.index('unit') if 'unit' in hdr else None
        for name in re.split(r',\s*', norm(c[0])):
            if re.fullmatch(r'[a-z_][a-z0-9_\[\]]*', name):
                fields[name].append((norm(c[ti]), norm(c[ui]) if ui is not None else None, i + 1, sec(i)))
out = []
for f, v in sorted(fields.items()):
    if len({t for t, _, _, _ in v}) > 1 or len({u for _, u, _, _ in v if u}) > 1:
        out.append(f'FIELD {f}: ' + ' | '.join(f'{t}/{u} (l.{n}, {s})' for t, u, n, s in v))

# 2. a named parameter given with different values: name (200 ms)
vals = collections.defaultdict(set); where = collections.defaultdict(list)
for i, l in enumerate(L):
    for m in re.finditer(r'\b([a-z][a-z0-9_]*_(?:ms|s|hz|deg|mm))\b\s*\(?(?:=|of|is)?\s*(\d[\d.,]*)\s*(ms|s|hz|hz|deg|°|mm)\b', l, re.I):
        vals[m.group(1)].add(m.group(2)); where[m.group(1)].append(i + 1)
for k, v in vals.items():
    if len(v) > 1: out.append(f'VALUE {k}: {sorted(v)} lines {where[k][:8]}')

# 3. topics used but not defined as a #### block
defined = {l[5:].strip() for l in L if l.startswith('#### ')}
used = collections.Counter()
for l in L:
    for m in re.finditer(r'\b((?:vision|plan|platform|glove|game|ai|pid|control|cs|sys)/[a-z_]+)\b', l):
        used[m.group(1)] += 1
for t in sorted(used):
    if t not in defined and not any(d.startswith(t) or t.startswith(d) for d in defined):
        out.append(f'TOPIC {t}: used {used[t]}×, no #### block')

print('\n'.join(out) or 'no issues'); print(f'-- {len(out)} findings')
