"""번역 검증 — 넣기 전에 터질 것을 전부 잡는다.

    python tools/check.py [trans/*.json ...]

1) 글리프    한글·공백 말고 폰트에 없는 문자가 섞였는가
2) 줄 폭     말풍선을 넘기는 줄이 있는가
3) 음절 예산 고유 음절이 재활용 칸 상한을 넘는가
4) 원문 대조 엔트리 번호가 실제로 존재하는가, 문자 수 증감은 얼마인가

## 줄 폭 예산 (실측 근거)
원본 일본어 **말풍선 대사 2,879줄**(UI·크레딧·튜토리얼 제외)을 재보면
    중앙값 181 / 95% 338 / 99% 459 / 실제 최대 639~719   (advance 단위)
게임이 자동 줄바꿈을 하지 않고 글자도 축소하지 않으므로, 원문이 실제로 쓰는
폭까지는 안전하다. 그래서 상한을 640, 권장을 460 으로 잡는다.
한글 advance 28, 전용 공백 12 → 640단위 ≈ 한글 24자, 460단위 ≈ 17자.
"""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project
import caff
import font as fontmod
import build_kr as B

WIDTH_MAX = 640
WIDTH_WARN = 460


def line_width(s, space_adv=B.SPACE_ADV, hangul_adv=B.HANGUL_ADV, font=None):
    w = 0
    for ch in s:
        if ch == B.SPACE:
            w += space_adv
        elif B.is_hangul(ch):
            w += hangul_adv
        elif font is not None and ord(ch) in font.code2glyph:
            w += font.glyphs[font.code2glyph[ord(ch)]].adv
        else:
            w += hangul_adv
    return w


def check(paths=None, verbose=True):
    paths = paths or B.trans_paths()
    trans = B.load_trans(paths)
    src = project.work('orig', 'dvddata', 'aid', 'font', B.FONT, 'default.bin')
    f = fontmod.Font(open(src if os.path.exists(src) else project.font_path(B.FONT),
                          'rb').read(), B.FONT)
    cap = len(f.reusable('kanji')) + len(f.reusable('kana')) + len(f.reusable('wide'))

    errs = []
    warns = []
    syl = set()
    n_line = 0
    for scene, ents in sorted(trans.items()):
        p = os.path.join(project.text_root(), B.LANG, scene, 'default.bin')
        if not os.path.exists(p):
            errs.append(('씬없음', scene, ''))
            continue
        c = caff.load(B.LANG, scene)
        jp_parts = {i: __import__('extract').parts(c.values[i])
                    for i in ents if 0 <= i < c.n}
        for i, ko in sorted(ents.items()):
            if not (0 <= i < c.n):
                errs.append(('엔트리없음', '%s[%d]' % (scene, i), '엔트리 %d개' % c.n))
                continue
            for si, seg in enumerate(ko):
                # ★예산 = 말풍선 상한과 **그 조각의 원문 폭** 중 큰 쪽.
                #   Menus·tips 같은 UI 패널은 자체 줄바꿈이 있어 원문부터 길다.
                #   원문보다 넓어지지만 않으면 원문이 들어가던 곳엔 들어간다.
                jps = jp_parts.get(i) or []
                jw = 0
                if si < len(jps):
                    for ln in jps[si].split('\n'):
                        jw = max(jw, line_width(ln, font=f))
                limit = max(WIDTH_MAX, jw)
                for ch in seg:
                    if B.needs_slot(ch):
                        syl.add(ch)
                    elif ch not in '\n\r' and ord(ch) not in f.code2glyph:
                        errs.append(('글리프', '%s[%d]' % (scene, i),
                                     '폰트에 없음 %r U+%04X' % (ch, ord(ch))))
                for ln in seg.split('\n'):
                    n_line += 1
                    w = line_width(ln, font=f)
                    if w > limit:
                        errs.append(('폭초과', '%s[%d]' % (scene, i),
                                     '%d > %d  %r' % (w, limit, ln)))
                    elif w > WIDTH_WARN and jw <= WIDTH_WARN:
                        warns.append(('폭주의', '%s[%d]' % (scene, i),
                                      '%d > 권장 %d  %r' % (w, WIDTH_WARN, ln)))

    syl.discard(B.SPACE)
    if verbose:
        print('번역 %d씬 / 줄 %d개 / 고유 음절 %d자 (상한 %d, 여유 %d)'
              % (len(trans), n_line, len(syl), cap, cap - len(syl) - 1))
        for kind, where, msg in errs:
            print('  [오류] %-8s %-22s %s' % (kind, where, msg))
        for kind, where, msg in warns[:20]:
            print('  [주의] %-8s %-22s %s' % (kind, where, msg))
        if len(warns) > 20:
            print('  ... 주의 외 %d건' % (len(warns) - 20))
        print('=> %s' % ('통과' if not errs else '오류 %d건' % len(errs)))
    if len(syl) + 1 > cap:
        print('!! 음절이 재활용 칸을 넘었다 (%d > %d)' % (len(syl) + 1, cap))
        return errs + [('음절초과', '', '')]
    return errs


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x.endswith('.json')]
    sys.exit(1 if check(a or None) else 0)
