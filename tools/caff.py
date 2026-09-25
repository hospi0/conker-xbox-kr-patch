"""CAFF/LSBL 텍스트 컨테이너 — 파서 + 재조립기.

    python tools/caff.py <파일> --dump      문자열 목록
    python tools/caff.py --roundtrip        전 언어 전 씬 왕복 검증

구조 (`dvddata/aid/text/<언어>/<씬>/default.bin`)
    0x000 'CAFF' + 버전
    0x040 '.data' 섹션 서술자   — 크기 필드 0x50, 파일크기 = 0x180 + 이 값
    0x180 'text' 청크           — 크기 필드 0x194
          키 풀(UTF-16, `cutscene_W1_BARN_OUTSIDE_11_0` 꼴) → 'LSBL' 청크
    LSBL  magic(4) + hdr_len(4) + hdr(hdr_len) + count(4)
          + (u16 idx, u32 off)*count + 종단 6B + UTF-16LE 블롭

★`off` 는 바이트가 아니라 **문자 수**다. 여기서 한 번 틀렸다.
★블롭은 빈틈 없이 연속이고 idx 는 0..n-1 순차다 — 그래서 재배치가 단순하다.
★N64판과 달리 **텍스트를 늘릴 수 있다.** 늘리면 아래 필드를 델타만큼 올린다:
    .data 크기(0x50) / text 청크 크기(0x194) / LSBL hdr[2] · hdr[5](청크 크기)
    / LSBL hdr[3] · hdr[4](LSBL 기준 절대 오프셋)
  6개 언어 교차 대조로 전부 블롭 바이트수에 정확히 비례함을 확인했다.

언어 디렉터리끼리 엔트리 순서가 같아서 인덱스로 영↔일 대응이 된다.
한 엔트리는 씬 전체이고 `{PMARKER}` `{PARAGRAPH}` 로 대사가 나뉜다.
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project

# ★★크기를 바꾸면 **파일 앞쪽 4곳**을 전부 손봐야 한다. 6개 언어가 같은 씬을
#   서로 다른 크기로 갖고 있어, 언어별 헤더를 교차 대조하면 크기에 연동되는 필드를
#   빠짐없이 뽑아낼 수 있다(이 방법으로 0x34 를 뒤늦게 찾았다).
#     0x34  경로 청크 오프셋 (0x180 기준) — 블롭 **뒤**에 있어 델타만큼 밀린다
#     0x50  `.data` 섹션 크기            ┐ 같은 값이 두 곳에 중복 보관된다
#     0x64  `.data` 섹션 크기            ┘ (서술자 시작 +0x10 과 +0x24)
#     0x194 `text` 청크 크기             — 여긴 중복 없이 하나뿐
#   하나라도 빠뜨리면 파일은 멀쩡해 보여도 **게임이 부팅되지 않는다**(2026-08-03 실기).
SEC_DATA_SIZE = (0x50, 0x64)
TEXT_CHUNK_SIZE = 0x194
PATH_CHUNK_OFF = 0x34               # 467개 원본 전수 확인 (0x180+이 값 = 경로 청크)
ALIGN = 4                           # ★원본 467개가 전부 4의 배수 — 뒤 청크가 dword 배열이다
GROW_FIELDS = (2, 3, 4, 5)          # LSBL 헤더에서 델타를 더해야 하는 인덱스
# ★hdr[3]·hdr[4] 는 파일에 따라 **한쪽만 실제 오프셋이고 다른 쪽은 0(=미사용)이다**
#   (21/146 파일이 둘 다 0). 0인 필드에 델타를 더치면 축소 시 음수·오염값이 된다.
#   그래서 GROW_FIELDS 중에서도 **0인 필드는 건드리지 않는다.**


class Caff(object):
    def __init__(self, data):
        self.raw = bytearray(data)
        d = self.raw
        assert bytes(d[:4]) == b'CAFF', 'CAFF 아님'
        self.p = d.find(b'LSBL')
        assert self.p > 0, 'LSBL 청크 없음'
        self.hlen = struct.unpack_from('<I', d, self.p + 4)[0]
        self.hdr = list(struct.unpack_from('<6I', d, self.p + 8))
        t = self.p + 4 + self.hlen
        self.n = struct.unpack_from('<I', d, t)[0]
        self.tab = t + 4
        self.blob = self.tab + self.n * 6 + 6
        ents = [struct.unpack_from('<HI', d, self.tab + i * 6) for i in range(self.n)]
        self.idx = [e[0] for e in ents]
        self.values = []
        for _, off in ents:
            s = self.blob + off * 2
            e = s
            while e < len(d) - 1 and not (d[e] == 0 and d[e + 1] == 0):
                e += 2
            self.values.append(bytes(d[s:e]).decode('utf-16-le'))
        self.blob_bytes = sum(len(v) + 1 for v in self.values) * 2
        self.tail = bytes(d[self.blob + self.blob_bytes:])

    @classmethod
    def load(cls, path):
        return cls(open(path, 'rb').read())

    def blob_size_of(self, values):
        """그 값들로 조립했을 때 블롭이 몇 바이트가 되는가 (패딩 전)."""
        return sum(len(v) + 1 for v in values) * 2

    def build(self, values=None, fixed_size=False):
        """fixed_size=True 면 **원본과 완전히 같은 크기**로 맞춰 낸다.

        블롭 꼬리를 널로 메워 크기를 맞춘다. 엔트리마다 오프셋이 명시적이라
        꼬리 여분은 무해하다. 들어가지 않으면 예외 — 호출자가 번역을 덜어내야 한다.
        """
        vals = self.values if values is None else values
        assert len(vals) == self.n, '엔트리 수는 바꿀 수 없다 (키 풀이 따로 있다)'
        if fixed_size:
            need = self.blob_size_of(vals)
            if need > self.blob_bytes:
                raise ValueError('원본 크기 초과: 블롭 %d > %d B' % (need, self.blob_bytes))
        out = bytearray(self.raw[:self.tab])
        cum = 0
        blob = bytearray()
        for i, v in enumerate(vals):
            out += struct.pack('<HI', self.idx[i], cum)
            blob += v.encode('utf-16-le') + b'\x00\x00'
            cum += len(v) + 1
        # ★블롭 뒤 청크들이 dword 배열이라 **4바이트 정렬을 반드시 지킨다.**
        #   UTF-16 이라 글자 수가 홀수만큼 바뀌면 델타가 ±2 가 되어 정렬이 깨진다.
        #   널 문자를 덧대 메운다 — 오프셋이 엔트리마다 명시적이라 꼬리 여분은 무해하다.
        delta = len(blob) - self.blob_bytes
        pad = (self.blob_bytes - len(blob)) if fixed_size else ((-delta) % ALIGN)
        blob += b'\x00' * pad
        delta += pad

        out += self.raw[self.tab + self.n * 6:self.blob]     # 종단 엔트리 6B
        out += blob
        out += self.tail
        if delta:
            for off in SEC_DATA_SIZE + (TEXT_CHUNK_SIZE, PATH_CHUNK_OFF):
                struct.pack_into('<I', out, off,
                                 struct.unpack_from('<I', out, off)[0] + delta)
            for i in GROW_FIELDS:
                if self.hdr[i] == 0:
                    continue
                struct.pack_into('<I', out, self.p + 8 + i * 4, self.hdr[i] + delta)
        self._verify(out)
        return bytes(out)

    @staticmethod
    def _verify(buf):
        """구조 불변식 재검사 — 부팅불가를 조립 단계에서 잡는다."""
        assert len(buf) % ALIGN == 0, '파일 크기가 %d 정렬이 아니다 (%d)' % (ALIGN, len(buf))
        want = len(buf) - 0x180
        for off in SEC_DATA_SIZE:
            got = struct.unpack_from('<I', buf, off)[0]
            assert got == want, ('.data 크기 필드 0x%02X 가 %d, 실제 %d'
                                 % (off, got, want))
        p = 0x180 + struct.unpack_from('<I', buf, PATH_CHUNK_OFF)[0]
        assert 0 <= p < len(buf) and buf[p + 8:p + 10].lower() in (b'd:', b'c:'), \
            '0x34 가 경로 청크를 안 가리킨다 (0x%X)' % p

    def save(self, path, values=None, fixed_size=False):
        b = self.build(values, fixed_size=fixed_size)
        d = os.path.dirname(path)
        if d and not os.path.isdir(d):
            os.makedirs(d)
        open(path, 'wb').write(b)
        return len(b)


def orig_path(lang, scene):
    """★원문은 반드시 `work/orig/` 에서 읽는다.

    game_dir 은 빌드가 제자리에서 덮어쓰므로, 거기서 읽으면 **패치본(한자로 뒤섞인
    한글)** 을 원문으로 오인한다. 한 번 당해서 사전에 깨진 항목이 들어갔다.
    """
    rel = os.path.join('dvddata', 'aid', 'text', lang, scene, 'default.bin')
    o = project.work('orig', rel)
    return o if os.path.exists(o) else os.path.join(project.game_dir(), rel)


def scenes(lang):
    root = os.path.join(project.text_root(), lang)
    return sorted(n for n in os.listdir(root)
                  if os.path.exists(os.path.join(root, n, 'default.bin')))


def load(lang, scene):
    return Caff.load(orig_path(lang, scene))


def roundtrip(root=None, verbose=True):
    root = root or project.text_root()
    ok = bad = 0
    for dirpath, _, files in os.walk(root):
        for fn in files:
            if not fn.endswith('.bin'):
                continue
            p = os.path.join(dirpath, fn)
            src = open(p, 'rb').read()
            try:
                out = Caff(src).build()
            except Exception as ex:
                bad += 1
                print('  실패 %s: %s' % (os.path.relpath(p, root), ex))
                continue
            if out == src:
                ok += 1
            else:
                bad += 1
                print('  불일치 %s' % os.path.relpath(p, root))
    if verbose:
        print('컨테이너 왕복 일치 %d / 불일치 %d' % (ok, bad))
    return bad == 0


if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] == '--roundtrip':
        sys.exit(0 if roundtrip() else 1)
    c = Caff.load(a[0])
    print('엔트리 %d, 블롭 %d B' % (c.n, c.blob_bytes))
    for i, v in enumerate(c.values):
        print('%4d %r' % (i, v))
