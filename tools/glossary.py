"""같은 원문 조각은 한 번만 번역한다 — 전 씬에 자동 전파.

    python tools/glossary.py                 # 이미 번역된 것을 같은 원문에 전파
    python tools/glossary.py --todo [씬]     # 아직 안 된 고유 조각을 빈도순으로
    python tools/glossary.py --stats

전체 조각 5,259개 중 고유는 4,387개다. `続ける` `戻る` `キャンセル` 같은 UI 문구는
씬을 넘나들며 10~20번씩 나온다. 원문이 **완전히 같으면** 번역도 같아야 하므로
한 곳만 채우고 나머지는 여기서 퍼뜨린다. 일관성도 같이 지켜진다.
"""
import collections
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project


def files():
    return sorted(glob.glob(os.path.join(project.ROOT, 'trans', '[!_]*.json')))


def load():
    return [(p, json.load(io.open(p, encoding='utf-8'))) for p in files()]


def save(p, d):
    with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(d, ensure_ascii=False, indent=1))


GLOSS = os.path.join(project.ROOT, 'trans', '_glossary.json')


def load_gloss():
    if os.path.exists(GLOSS):
        return json.load(io.open(GLOSS, encoding='utf-8'))
    return {}


def save_gloss(m):
    with io.open(GLOSS, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True))


def collect(docs):
    """jp -> ko (이미 번역된 것). 충돌하면 알린다."""
    m = {}
    clash = collections.defaultdict(set)
    for p, d in docs:
        for k, v in d['entries'].items():
            for jp, ko in zip(v['jp'], v['ko']):
                if not ko or not jp.strip():
                    continue
                if jp in m and m[jp] != ko:
                    clash[jp].add(m[jp])
                    clash[jp].add(ko)
                m[jp] = ko
    return m, clash


def propagate(docs, m):
    n = 0
    for p, d in docs:
        dirty = False
        for k, v in d['entries'].items():
            for i, (jp, ko) in enumerate(zip(v['jp'], v['ko'])):
                if not ko and jp in m:
                    v['ko'][i] = m[jp]
                    n += 1
                    dirty = True
        if dirty:
            save(p, d)
    return n


def todo(docs, scene=None):
    c = collections.Counter()
    where = {}
    for p, d in docs:
        if scene and d['scene'] != scene:
            continue
        for k, v in d['entries'].items():
            for jp, ko in zip(v['jp'], v['ko']):
                if ko or not jp.strip():
                    continue
                c[jp] += 1
                where.setdefault(jp, '%s[%s]' % (d['scene'], k))
    return c, where


def stats(docs):
    tot = done = 0
    per = []
    for p, d in docs:
        t = sum(1 for v in d['entries'].values() for x in v['jp'] if x.strip())
        y = sum(1 for v in d['entries'].values()
                for jp, ko in zip(v['jp'], v['ko']) if jp.strip() and ko)
        tot += t
        done += y
        per.append((t - y, t, d['scene']))
    per.sort(reverse=True)
    print('조각 %d / 번역 %d (%.1f%%)  남은 %d' % (tot, done, done * 100.0 / tot, tot - done))
    return per


if __name__ == '__main__':
    a = sys.argv[1:]
    docs = load()
    if '--todo' in a:
        sc = a[a.index('--todo') + 1] if len(a) > a.index('--todo') + 1 else None
        c, w = todo(docs, sc)
        print('남은 고유 조각 %d개 (총 %d회)' % (len(c), sum(c.values())))
        for jp, n in c.most_common():
            print('%3d %-24s %s' % (n, w[jp], jp.replace('\n', '\\n')))
    elif '--stats' in a:
        for rem, tot, sc in stats(docs)[:30]:
            if rem:
                print('  %-22s %5d / %5d 남음' % (sc, rem, tot))
    else:
        m, clash = collect(docs)
        for jp, vs in list(clash.items())[:10]:
            print('  충돌 %r -> %s' % (jp[:30], [v[:20] for v in vs]))
        g = load_gloss()
        g.update(m)                       # 파일에 이미 든 번역이 우선순위가 낮다
        m2 = dict(load_gloss())
        m2.update(m)
        n = propagate(docs, m2)
        save_gloss(m2)
        print('사전 %d개 / 전파 %d조각' % (len(m2), n))
        stats(docs)
