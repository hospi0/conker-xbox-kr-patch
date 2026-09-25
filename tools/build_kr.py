"""한글 패치 빌더 — 일본어 슬롯에 얹는다.

    python tools/build_kr.py [trans/poc.json ...]        # 파일 패치까지
    python tools/build_kr.py --iso                       # 이어서 ISO 재빌드

★게임은 **charmap 해시표에 문자를 추가할 수 없다**(해시 함수 미복원). 그래서
  이미 등록된 한자·가나 코드포인트의 **글리프만 한글로 다시 그리고**, 텍스트에는
  그 한자 코드를 써 넣는다. charmap·크기 필드·파일 크기가 전부 그대로다.
  → 패치본 텍스트를 그냥 열면 한자 낱말처럼 보인다. 이건 정상이다.
     [[feedback_font_reuse_untranslated_looks_scrambled]] 와 같은 함정이므로
     검증은 **원본↔패치본 바이트 대조**로 한다.

★음절 → 코드포인트 배정은 `work/slots.json` 에 **영구 보존**한다. 배정이 바뀌면
  이미 넣은 텍스트가 전부 깨진다. 새 음절은 항상 뒤에 덧붙인다.

★언어 슬롯: 게임은 Xbox 시스템 언어가 일본어일 때만 ConkerFontJapanese +
  text/Japanese 를 읽는다. 실기/xemu 에서 **시스템 언어를 일본어로 둬야** 보인다.
"""
import glob
import io
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project
import caff
import extract
import font as fontmod
import render

FONT = 'ConkerFontJapanese'
TITLE_FONT = 'FrontendTitleJapanese'
LANG = 'Japanese'
SLOTS = 'slots.json'

# ★★UI 화면은 `ConkerFontJapanese` 가 아니라 **`FrontendTitleJapanese`(370글리프)** 로
#   그린다. 이 폰트에 없는 코드포인트는 □(대체 글리프)로 나온다 — 2026-08-03 실기.
#   어떤 씬이 이 폰트를 쓰는지는 **원문이 그 370글리프로 전부 커버되는가**로 갈린다.
#   그래서 UI 씬의 음절은 **두 폰트 모두에 있는 코드포인트(공유 풀 288개)** 로만
#   배정하고, 두 폰트를 똑같이 칠한다. UI 필요 음절은 233개라 들어간다.
TITLE_SCENES = {
    'UIFrontend', 'UIPause', 'chapters_text', 'FrontendTable', 'mp_frontend',
    'MPBlitzkrieg', 'MPJungle', 'MPVolcanoRace', 'MPPopsicleDM', 'BrontoThroat',
    'DogFishNursery', 'FlameTunnel', 'HauntedHouseOutside', 'LocalisationSettings',
    'basic_characters', 'JP_basic_characters',
}

# ★반각 스페이스 U+0020 은 이 게임에서 **강제 개행**이다 (실기 확인 2026-08-03).
#   전각 U+3000 은 정상 공백이지만 29px 라 너무 넓다. 그래서 재활용 칸 하나를
#   **빈 글리프 + 좁은 advance** 로 만들어 한글 전용 공백으로 쓴다.
#   번역문에는 그냥 보통 스페이스를 쓰면 빌더가 알아서 이걸로 바꾼다.
SPACE = ' '
SPACE_ADV = 12
HANGUL_ADV = 28          # 한자 기본값 29 보다 1 좁게 — 자간을 붙인다

# ★번역하면 안 되는 씬 — 화면에 나오는 글이 아니라 **설정·문자셋 정의**다.
#   `LocalisationSettings` 는 값이 ['0','0','いいえ','0','0'] 인 플래그 덩어리고,
#   `*basic_characters` 는 폰트가 쓰는 문자 목록이다. 건드릴 이득이 없고 위험만 크다.
SKIP_SCENES = {'LocalisationSettings', 'basic_characters', 'JP_basic_characters'}

# ★크기 고정 모드: 모든 파일을 **원본과 정확히 같은 크기**로 낸다.
#   크기 변경이 부팅을 깨뜨리는지 가리기 위한 안전 모드. 들어가지 않는 엔트리는
#   원문(일본어)으로 되돌린다.
FIXED_SIZE = True


def is_hangul(ch):
    return 0xAC00 <= ord(ch) <= 0xD7A3


def needs_slot(ch):
    return is_hangul(ch) or ch == SPACE


def load_trans(paths):
    """씬 -> {엔트리번호: [조각별 ko]}.  빈 조각은 원문을 남긴다는 뜻이다."""
    out = {}
    for p in paths:
        doc = json.load(io.open(p, encoding='utf-8'))
        scene = doc['scene']
        for k, v in doc['entries'].items():
            if any(v['ko']):
                out.setdefault(scene, {})[int(k)] = v['ko']
    return out


def trans_paths():
    return sorted(glob.glob(os.path.join(project.ROOT, 'trans', '[!_]*.json')))


def load_slots():
    p = project.work(SLOTS)
    if os.path.exists(p):
        return json.load(io.open(p, encoding='utf-8'))
    return {}


def save_slots(m):
    with io.open(project.work(SLOTS), 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(m, ensure_ascii=False, indent=1, sort_keys=True))


def allocate(f, syllables, slots, shared=None, need_shared=()):
    """음절 -> 재활용 코드포인트. 기존 배정은 절대 바꾸지 않는다.

    ★`need_shared` 음절(=UI 화면에 나오는 것)은 **두 폰트 모두에 있는 코드포인트**
      로만 배정한다. 안 그러면 UI 에서 □ 로 나온다.
    """
    used = set(slots.values())
    shared = shared or set()

    def pool_of(cands):
        return [c for c in cands if c not in used]

    all_pool = [c for c, _ in f.reusable('kanji', 28, 28)]
    all_pool += [c for c, _ in f.reusable('kanji') if c not in set(all_pool)]
    all_pool += [c for c, _ in f.reusable('kana')]
    all_pool += [c for c, _ in f.reusable('wide')]

    fresh = [s for s in sorted(syllables) if s not in slots]
    # 공유 풀이 필요한 것부터 배정한다 (자리가 좁으므로)
    fresh.sort(key=lambda s: (s not in need_shared, s))
    n_shared = 0
    for s in fresh:
        if s in need_shared:
            cands = pool_of([c for c in all_pool if c in shared])
            if not cands:
                raise SystemExit('공유 칸 부족 — UI 음절 %r 을 배정할 수 없다' % s)
            n_shared += 1
        else:
            cands = pool_of([c for c in all_pool if c not in shared]) or pool_of(all_pool)
            if not cands:
                raise SystemExit('재활용 칸 부족 — 음절 %r' % s)
        slots[s] = cands[0]
        used.add(cands[0])
    return slots, len(fresh), n_shared


def backup(path):
    rel = os.path.relpath(path, project.game_dir())
    dst = project.work('orig', rel)
    if not os.path.exists(dst):
        d = os.path.dirname(dst)
        if not os.path.isdir(d):
            os.makedirs(d)
        shutil.copy2(path, dst)
    return dst


def main(argv):
    paths = [a for a in argv if a.endswith('.json')] or trans_paths()
    trans = load_trans(paths)

    f = fontmod.Font(open(backup(project.font_path(FONT)), 'rb').read(), FONT)
    tf = fontmod.Font(open(backup(project.font_path(TITLE_FONT)), 'rb').read(), TITLE_FONT)
    shared = set(tf.code2glyph)                      # 타이틀 폰트가 가진 코드포인트

    syl = set(ch for ents in trans.values() for v in ents.values()
              for seg in v for ch in seg if needs_slot(ch))
    syl.add(SPACE)                                   # 공백은 항상 확보한다
    # ★UI 씬에 쓰이는 음절 — 공유 코드포인트로만 배정해야 한다
    need_shared = set(ch for sc, ents in trans.items() if sc in TITLE_SCENES
                      for v in ents.values() for seg in v for ch in seg if needs_slot(ch))
    need_shared.add(SPACE)

    slots, added, n_sh = allocate(f, syl, load_slots(), shared, need_shared)
    save_slots(slots)
    bad = [s for s in need_shared if slots[s] not in shared]
    if bad:
        raise SystemExit('UI 음절이 공유 밖에 배정됐다: %s' % ''.join(sorted(bad))[:40])
    print('음절 %d개 (신규 %d, 그중 UI공유 %d) / 공유 풀 %d개, UI 필요 %d개'
          % (len(syl), added, n_sh, len(shared & set(
              [c for c, _ in f.reusable('kanji')] + [c for c, _ in f.reusable('kana')]
              + [c for c, _ in f.reusable('wide')])), len(need_shared)))

    # --- 폰트: 배정된 칸을 한글로 다시 그린다 (본문·타이틀 두 폰트 모두) ---
    #   advance 는 폰트마다 셀 크기가 달라 정책이 다르다:
    #     본문(28x28 균일)  -> 고정값 28 / 공백 12
    #     타이틀(제각각)     -> 그 칸의 원래 폭을 그대로 둔다 (레이아웃을 안 흔든다)
    def paint(fo, which, fixed):
        n_paint = 0
        for s in sorted(syl):
            gi = fo.code2glyph.get(slots[s])
            if gi is None:            # 이 폰트엔 없는 코드포인트 = UI 밖 음절
                continue
            g = fo.glyphs[gi]
            x0, y0, _, _ = g.rect(fo.W, fo.H)
            if s == SPACE:
                fo.blit(x0, y0, g.w, g.h, render.blank(g.w, g.h))
                if fixed:
                    g.adv = SPACE_ADV
            else:
                fo.blit(x0, y0, g.w, g.h, render.cell(s, g.w, g.h))
                if fixed:
                    g.adv = HANGUL_ADV
            n_paint += 1
        n_b = fo.save(project.font_path(which))
        print('폰트 %-22s %7d B (크기 불변) — 글리프 %d개 다시 그림'
              % (which, n_b, n_paint))

    paint(f, FONT, True)
    paint(tf, TITLE_FONT, False)
    print('공백 글리프 U+%04X advance %d / 한글 advance %d (본문)'
          % (slots[SPACE], SPACE_ADV, HANGUL_ADV))

    # --- 텍스트: 한글을 배정 코드포인트로 치환 ---
    total = n_seg = n_drop = 0
    for scene, ents in sorted(trans.items()):
        if scene in SKIP_SCENES:
            continue
        p = os.path.join(project.text_root(), LANG, scene, 'default.bin')
        c = caff.Caff.load(backup(p))
        vals = list(c.values)
        made = {}                       # 엔트리 -> 번역 적용된 값
        for i, ko in sorted(ents.items()):
            ps, ss = extract.parts(vals[i]), extract.seps(vals[i])
            if len(ko) != len(ps):
                raise SystemExit('%s[%d] 조각 수 불일치 ko %d != jp %d'
                                 % (scene, i, len(ko), len(ps)))
            new_ps = []
            for k, (orig, t) in enumerate(zip(ps, ko)):
                if not t:                       # 빈 조각 = 아직 미번역, 원문 유지
                    new_ps.append(orig)
                    continue
                new_ps.append(encode(t, slots, f, '%s[%d].%d' % (scene, i, k)))
            made[i] = extract.join(new_ps, ss)
            vals[i] = made[i]

        # ★크기 고정: 안 들어가면 **가장 많이 늘어난 엔트리부터** 원문으로 되돌린다
        if FIXED_SIZE:
            while c.blob_size_of(vals) > c.blob_bytes:
                grow = {i: len(vals[i]) - len(c.values[i]) for i in made
                        if vals[i] != c.values[i]}
                if not grow:
                    raise SystemExit('%s: 되돌릴 게 없는데도 초과' % scene)
                worst = max(grow, key=lambda i: grow[i])
                vals[worst] = c.values[worst]
                n_drop += 1
        n_seg += sum(1 for i in made if vals[i] != c.values[i])

        size = c.save(p, vals, fixed_size=FIXED_SIZE)
        total += 1
        d = size - len(c.raw)
        print('  %-22s %6d B (%+d)' % (scene, size, d))
    print('텍스트 %d씬 / 번역 적용 엔트리 %d개 / 크기초과로 되돌림 %d개'
          % (total, n_seg, n_drop))

    if '--iso' in argv:
        build_iso()


def encode(t, slots, f, where):
    out = []
    for ch in t:
        if needs_slot(ch):
            out.append(unichr_(slots[ch]))
        else:
            if ch not in '\n\r' and ord(ch) not in f.code2glyph:
                raise SystemExit('폰트에 없는 문자 %r (U+%04X) — %s' % (ch, ord(ch), where))
            out.append(ch)
    return ''.join(out)


def unichr_(c):
    return chr(c)


def build_iso():
    """★extract-xiso 는 대상 파일이 이미 있으면 조용히 실패한다.
    지우지 않으면 **낡은 ISO 가 남아 성공으로 오인**된다 (한 번 당했다)."""
    cfg = project.local()
    out = os.path.join(project.out_dir(), 'Conker LR KR.iso')
    if os.path.exists(out):
        os.remove(out)
    print('ISO 빌드: %s' % out)
    r = subprocess.run([cfg['xiso_exe'], '-c', project.game_dir(), out],
                       capture_output=True, text=True)
    tail = (r.stdout or '')[-400:] + (r.stderr or '')[-400:]
    if not os.path.exists(out):
        raise SystemExit('ISO 생성 실패\n%s' % tail)
    print(tail.strip().splitlines()[-1] if tail.strip() else '')
    print('-> %s (%.2f GB)' % (out, os.path.getsize(out) / 1024.0 ** 3))


if __name__ == '__main__':
    main(sys.argv[1:])
