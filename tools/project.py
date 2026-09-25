"""프로젝트 공통: 경로 해석과 원본 식별.

경로는 코드에 박지 않는다. `config/local.json` 이 유일한 진실이다.
"""
import hashlib
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, 'config')


def local():
    p = os.path.join(CONFIG, 'local.json')
    if not os.path.exists(p):
        raise SystemExit('config/local.json 이 없다. local.json.example 을 복사할 것.')
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def game_dir():
    d = local()['game_dir']
    if not os.path.isdir(d):
        raise SystemExit('game_dir 이 없다: %s' % d)
    return d


def text_root():
    return os.path.join(game_dir(), 'dvddata', 'aid', 'text')


def font_path(name):
    return os.path.join(game_dir(), 'dvddata', 'aid', 'font', name, 'default.bin')


def out_dir():
    d = local().get('out_dir') or os.path.join(ROOT, 'work')
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def work(*parts):
    return os.path.join(ROOT, 'work', *parts)


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()
