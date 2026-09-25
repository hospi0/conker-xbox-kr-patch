"""ConkerFont / ConkerFontJapanese — 글리프·charmap·아틀라스 파서 + 재조립기.

    python tools/font.py ConkerFontJapanese            요약
    python tools/font.py ConkerFontJapanese --atlas    아틀라스 PNG 로 덤프
    python tools/font.py ConkerFontJapanese --crop 万丈上下   글리프 잘라보기

파일 구조
    0x000 'CAFF' 헤더
    0x040 '.data' 서술자  — 크기 필드 0x50.  파일크기 = 0x180 + .data + .gpu
    0x068 '.gpu'  서술자  — 크기 필드 0x78
    0x180 'font' 청크 헤더 32B
    0x4C0 폰트 헤더 16 dword
            [1] 글리프배열 바이트 + 904   [5] 글리프 수   [6] 대체문자 U+25A1
    0x506 글리프 엔트리 배열 ★18바이트 고정
            u16 ?, u8 xoff, u8 yoff, u8 w, u8 h, u16 u0,u1,v0,v1, u16 advance, u16 FFFF
    +2    charmap ★2048슬롯 × (u16 유니코드, u16 글리프인덱스), FFFF FFFF = 빈칸
    끝    'texture' 청크
    .gpu  아틀라스 ★8bpp 선형(스위즐 없음)

★UV 의 분모는 65536 이 아니라 **16384** 다 (2.14 고정소수점).
  65536 으로 잡으면 아틀라스가 4배로 계산돼 4248x3208 같은 헛값이 나온다.
      픽셀x = u/16384 * 아틀라스폭 - 0.5   (반텍셀 보정)
  글리프 엔트리의 w,h 와 UV 폭이 서로 일치해 검증된다.

★charmap 은 **해시표**다 (일본어 폰트는 코드 오름차순이 아니다). 해시 함수는 아직
  복원하지 못했다. 그래서 문자를 **추가하지 않고**, 이미 있는 한자·가나 코드포인트의
  글리프를 한글로 다시 그려 쓴다 (슬롯 재활용). charmap 은 손대지 않는다.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project

GLYPH_BASE = 0x506
GLYPH_STRIDE = 18
HDR = 0x4C0
SEC_DATA_SIZE = 0x50
SEC_GPU_SIZE = 0x78
UV_DENOM = 16384.0
SLOTS = 2048

SIZES = {'ConkerFont': (256, 240), 'ConkerFontJapanese': (1024, 772),
         'FrontendTitle': (512, 203), 'FrontendTitleJapanese': (1024, 335)}


class Glyph(object):
    __slots__ = ('a', 'xoff', 'yoff', 'w', 'h', 'u0', 'u1', 'v0', 'v1', 'adv')

    def __init__(self, *v):
        (self.a, self.xoff, self.yoff, self.w, self.h,
         self.u0, self.u1, self.v0, self.v1, self.adv) = v

    def rect(self, W, H):
        """아틀라스 픽셀 사각형 (x0, y0, x1, y1)."""
        x0 = int(round(self.u0 / UV_DENOM * W - 0.5))
        y0 = int(round(self.v0 / UV_DENOM * H - 0.5))
        return x0, y0, x0 + self.w, y0 + self.h

    def pack(self):
        return struct.pack('<HBBBBHHHHHH', self.a, self.xoff, self.yoff, self.w,
                           self.h, self.u0, self.u1, self.v0, self.v1, self.adv, 0xFFFF)


class Font(object):
    def __init__(self, data, name):
        self.raw = bytearray(data)
        self.name = name
        self.W, self.H = SIZES[name]
        d = self.raw
        assert bytes(d[:4]) == b'CAFF'
        self.dsize = struct.unpack_from('<I', d, SEC_DATA_SIZE)[0]
        self.gsize = struct.unpack_from('<I', d, SEC_GPU_SIZE)[0]
        assert 0x180 + self.dsize + self.gsize == len(d), '섹션 크기 합이 파일과 다르다'
        assert self.W * self.H == self.gsize, '아틀라스 %dx%d 가 .gpu %d B 와 다르다' % (
            self.W, self.H, self.gsize)
        self.hdr = list(struct.unpack_from('<16I', d, HDR))
        self.n = self.hdr[5]
        self.fallback = self.hdr[6]
        self.glyphs = []
        for i in range(self.n):
            v = struct.unpack_from('<HBBBBHHHHH', d, GLYPH_BASE + i * GLYPH_STRIDE)
            self.glyphs.append(Glyph(*v))
        self.tab = GLYPH_BASE + self.n * GLYPH_STRIDE + 2
        self.slots = []
        self.code2glyph = {}
        for i in range(SLOTS):
            c, g = struct.unpack_from('<HH', d, self.tab + i * 4)
            self.slots.append((c, g))
            if c != 0xFFFF:
                self.code2glyph[c] = g
        self.atlas = bytearray(d[0x180 + self.dsize:])

    @classmethod
    def load(cls, name):
        return cls(open(project.font_path(name), 'rb').read(), name)

    # --- 아틀라스 픽셀 ---
    def get_px(self, x, y):
        return self.atlas[y * self.W + x]

    def blit(self, x0, y0, w, h, pixels):
        """pixels = bytes(w*h) 를 아틀라스에 덮어쓴다."""
        assert len(pixels) == w * h
        for r in range(h):
            o = (y0 + r) * self.W + x0
            self.atlas[o:o + w] = pixels[r * w:(r + 1) * w]

    def crop(self, code):
        g = self.glyphs[self.code2glyph[code]]
        x0, y0, x1, y1 = g.rect(self.W, self.H)
        return g, bytes(bytearray(
            b for r in range(y0, y1) for b in self.atlas[r * self.W + x0:r * self.W + x1]))

    def build(self):
        out = bytearray(self.raw[:0x180 + self.dsize])
        for i, g in enumerate(self.glyphs):
            out[GLYPH_BASE + i * GLYPH_STRIDE:GLYPH_BASE + (i + 1) * GLYPH_STRIDE] = g.pack()
        for i, (c, g) in enumerate(self.slots):
            struct.pack_into('<HH', out, self.tab + i * 4, c, g)
        out += self.atlas
        assert len(out) == len(self.raw), '크기가 바뀌면 안 된다'
        return bytes(out)

    def save(self, path):
        b = self.build()
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        open(path, 'wb').write(b)
        return len(b)

    # --- 재활용 후보 ---
    def reusable(self, kind='kanji', w=None, h=None):
        """한글로 덮어쓸 수 있는 (코드, 글리프인덱스) 목록.

        kind: kanji(U+4E00~) / kana(U+3040~U+30FF) / wide(U+FF00~)
        w,h 를 주면 그 셀 크기인 것만 — 균일한 정사각 칸을 고를 때 쓴다.
        """
        rng = {'kanji': (0x4E00, 0xA000), 'kana': (0x3040, 0x3100),
               'wide': (0xFF00, 0xFFF0)}[kind]
        out = []
        for c, gi in sorted(self.code2glyph.items()):
            if not (rng[0] <= c < rng[1]):
                continue
            g = self.glyphs[gi]
            if (w is None or g.w == w) and (h is None or g.h == h):
                out.append((c, gi))
        return out


def _png(path, W, H, data):
    from PIL import Image
    Image.frombytes('L', (W, H), bytes(data)).save(path)


if __name__ == '__main__':
    name = sys.argv[1]
    f = Font.load(name)
    print('%s  글리프 %d  아틀라스 %dx%d (%d B)  대체문자 U+%04X'
          % (name, f.n, f.W, f.H, f.gsize, f.fallback))
    print('charmap 등록 %d / %d 슬롯' % (len(f.code2glyph), SLOTS))
    print('재활용 후보  한자 %d  가나 %d  전각 %d  (28x28 한자 %d)'
          % (len(f.reusable('kanji')), len(f.reusable('kana')),
             len(f.reusable('wide')), len(f.reusable('kanji', 28, 28))))
    assert f.build() == bytes(f.raw), '왕복 불일치'
    print('폰트 왕복 일치 OK')
    if '--atlas' in sys.argv:
        p = project.work(name + '.png')
        _png(p, f.W, f.H, f.atlas)
        print('->', p)
    if '--crop' in sys.argv:
        from PIL import Image
        s = sys.argv[sys.argv.index('--crop') + 1]
        strip = Image.new('L', (32 * len(s), 32), 0)
        for i, ch in enumerate(s):
            g, px = f.crop(ord(ch))
            strip.paste(Image.frombytes('L', (g.w, g.h), px), (i * 32 + 2, 2))
        p = project.work('crop.png')
        strip.resize((strip.width * 4, strip.height * 4), Image.NEAREST).save(p)
        print('->', p)
