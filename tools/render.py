"""한글 음절을 글리프 셀 크기로 래스터라이즈한다.

아틀라스가 8bpp 알파 선형이라 그레이스케일 그대로 써 넣으면 된다.
셀은 한자 자리를 재활용하므로 보통 28x28 이다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project

_cache = {}


def face(size, bold=True):
    from PIL import ImageFont
    key = (size, bold)
    if key not in _cache:
        d = project.local()['font_src']
        p = os.path.join(d, 'nanum-gothic',
                         'NanumGothicBold.ttf' if bold else 'NanumGothic.ttf')
        _cache[key] = ImageFont.truetype(p, size)
    return _cache[key]


def cell(ch, w, h, size=None, bold=True):
    """(w x h) 그레이스케일 bytes. 글자를 셀 안에 꽉 채워 가운데 정렬한다."""
    from PIL import Image, ImageDraw
    size = size or int(h * 0.98)
    f = face(size, bold)
    # 실제 잉크 박스를 재서 가운데에 놓는다 (폰트 메트릭의 여백을 믿지 않는다)
    big = Image.new('L', (w * 3, h * 3), 0)
    ImageDraw.Draw(big).text((w, h), ch, fill=255, font=f)
    bb = big.getbbox()
    if bb is None:
        return bytes(w * h)
    ink = big.crop(bb)
    if ink.width > w or ink.height > h:
        r = min(float(w) / ink.width, float(h) / ink.height)
        ink = ink.resize((max(1, int(ink.width * r)), max(1, int(ink.height * r))),
                         Image.LANCZOS)
    out = Image.new('L', (w, h), 0)
    out.paste(ink, ((w - ink.width) // 2, (h - ink.height) // 2))
    return out.tobytes()


def blank(w, h):
    """빈 셀 — 공백 글리프용."""
    return bytes(w * h)


def ink_width(ch, w, h, size=None, bold=True):
    """셀 안에서 글자가 실제로 차지하는 가로 픽셀 수."""
    from PIL import Image
    px = cell(ch, w, h, size, bold)
    im = Image.frombytes('L', (w, h), px)
    bb = im.getbbox()
    return (bb[2] - bb[0]) if bb else 0


def preview(text, w=28, h=28, path=None):
    from PIL import Image
    im = Image.new('L', (w * len(text), h), 0)
    for i, ch in enumerate(text):
        im.paste(Image.frombytes('L', (w, h), cell(ch, w, h)), (i * w, 0))
    p = path or project.work('render_preview.png')
    im.resize((im.width * 3, im.height * 3), Image.NEAREST).save(p)
    return p


if __name__ == '__main__':
    print(preview(sys.argv[1] if len(sys.argv) > 1 else '난콩커의왕이다'))
