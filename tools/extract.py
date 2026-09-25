"""번역 작업 파일 생성 — 씬마다 `trans/<씬>.json`.

    python tools/extract.py            # 없는 것만 만들고 기존 ko 는 보존
    python tools/extract.py --stats    # 분량만 집계

## 왜 세그먼트 단위인가
엔트리 하나는 씬 통째이고 `{PMARKER}` `{PARAGRAPH}` 로 말풍선이 나뉜다.
구분자를 통째로 보존해야 하므로 **구분자로 쪼갠 조각 배열**을 그대로 작업 단위로 쓴다.
`ko` 는 `jp` 와 **길이가 같아야 하고**, 빈 문자열이면 그 조각은 원문을 남긴다.

조각 안의 `\n` 은 말풍선 안 줄바꿈이다. 게임은 자동 줄바꿈을 하지 않으므로
직접 넣어야 한다. 줄 폭 예산은 `tools/check.py` 참조 (상한 640단위 ≈ 한글 24자).

`{RED}` `{THROB}` `{TXT_JOYSTICK}` 같은 인라인 토큰은 **그 자리에 그대로 둔다.**
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project
import caff

SEP = re.compile(r'(\{PMARKER\}|\{PARAGRAPH\})')
LANG = 'Japanese'
REF = 'English'


def parts(s):
    """구분자로 쪼갠 텍스트 조각들 (구분자는 뺀다)."""
    return SEP.split(s)[::2]


def seps(s):
    """조각 사이 구분자들."""
    return SEP.split(s)[1::2]


def join(ps, ss):
    out = ps[0]
    for sep, p in zip(ss, ps[1:]):
        out += sep + p
    return out


def worth(s):
    """번역할 값인가 — 숫자·좌표·빈값은 뺀다."""
    t = SEP.sub('', s).strip()
    if not t:
        return False
    return bool(re.search(r'[^\d\s,.:%\-+]', t))


def path_for(scene):
    return os.path.join(project.ROOT, 'trans', '%s.json' % scene)


def build(scene, keep=True):
    jp = caff.load(LANG, scene)
    try:
        en = caff.load(REF, scene)
    except Exception:
        en = None
    old = {}
    p = path_for(scene)
    if keep and os.path.exists(p):
        doc = json.load(io.open(p, encoding='utf-8'))
        old = doc.get('entries', {})
    ents = {}
    for i, v in enumerate(jp.values):
        if not worth(v):
            continue
        jps = parts(v)
        ens = parts(en.values[i]) if en and i < en.n else []
        ko = old.get(str(i), {}).get('ko') or [''] * len(jps)
        if len(ko) != len(jps):
            ko = (ko + [''] * len(jps))[:len(jps)]
        ents[str(i)] = {'en': ens, 'jp': jps, 'ko': ko}
    return {'scene': scene, 'n': jp.n, 'entries': ents}


def save(doc):
    p = path_for(doc['scene'])
    with io.open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(doc, ensure_ascii=False, indent=1))
    return p


def main(argv):
    scenes = caff.scenes(LANG)
    tot_e = tot_s = tot_c = done = 0
    for sc in scenes:
        doc = build(sc)
        n_e = len(doc['entries'])
        n_s = sum(len(v['jp']) for v in doc['entries'].values())
        n_c = sum(len(x) for v in doc['entries'].values() for x in v['jp'])
        d = sum(1 for v in doc['entries'].values() for x in v['ko'] if x)
        tot_e += n_e
        tot_s += n_s
        tot_c += n_c
        done += d
        if '--stats' not in argv:
            save(doc)
    print('씬 %d / 번역대상 엔트리 %d / 조각 %d / 일본어 %d자 / 번역완료 %d조각 (%.1f%%)'
          % (len(scenes), tot_e, tot_s, tot_c, done, done * 100.0 / max(1, tot_s)))


if __name__ == '__main__':
    main(sys.argv[1:])
