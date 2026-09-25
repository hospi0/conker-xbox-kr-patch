"""넣기 전에 터질 것을 전부 잡는다.

    python tools/selftest.py

1) 컨테이너 왕복   전 언어 전 씬 파싱→재조립 바이트 일치
2) 폰트 왕복       파싱→재조립 바이트 일치, 섹션 크기 합 = 파일 크기
3) 글리프 크롭     알려진 한자 셀에 잉크가 있는가 (UV 해석 검증)
4) 배정 무결       slots.json 이 1:1 이고 전부 재활용 가능 코드인가
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project
import caff
import font as fontmod

KANJI_SAMPLE = '万丈上下人日本語時間'


def main():
    fail = 0

    if not caff.roundtrip():
        fail += 1

    for name in ('ConkerFont', 'ConkerFontJapanese'):
        src = project.font_path(name)
        orig = project.work('orig', os.path.relpath(src, project.game_dir()))
        f = fontmod.Font(open(orig if os.path.exists(orig) else src, 'rb').read(), name)
        ok = f.build() == bytes(f.raw)
        print('폰트 왕복 %-20s %s (글리프 %d, 아틀라스 %dx%d)'
              % (name, 'OK' if ok else '불일치', f.n, f.W, f.H))
        fail += 0 if ok else 1

    f = fontmod.Font.load('ConkerFontJapanese')
    bad = []
    for ch in KANJI_SAMPLE:
        c = ord(ch)
        if c not in f.code2glyph:
            bad.append((ch, '미등록'))
            continue
        g, px = f.crop(c)
        if not any(px):
            bad.append((ch, '빈 셀'))
    print('글리프 크롭 %d자 중 이상 %d건 %s'
          % (len(KANJI_SAMPLE), len(bad), bad if bad else ''))
    fail += 1 if bad else 0

    p = project.work('slots.json')
    if os.path.exists(p):
        m = json.load(io.open(p, encoding='utf-8'))
        reuse = set(c for c, _ in f.reusable('kanji')) | set(c for c, _ in f.reusable('kana'))
        dup = len(m) != len(set(m.values()))
        out = [s for s, c in m.items() if c not in reuse]
        print('배정 %d자  중복 %s  재활용밖 %d건' % (len(m), '있음' if dup else '없음', len(out)))
        fail += 1 if (dup or out) else 0
        print('  남은 칸 %d' % (len(reuse) - len(m)))
    else:
        print('배정 없음 (slots.json 미생성)')

    print('=> %s' % ('전부 통과' if not fail else '실패 %d건' % fail))
    return fail


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
