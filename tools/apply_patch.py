"""배포된 xdelta 패치 묶음을 깨끗한 추출본에 적용한다.

    python tools/apply_patch.py <extract-xiso 로 푼 디렉터리> [--iso]

1) 원본 게임을 `extract-xiso -x "Conker...iso"` 로 아무 폴더에 푼다.
2) 이 스크립트로 `work/patch/` 의 xdelta 를 그 폴더에 적용한다.
3) `--iso` 를 주면 이어서 `extract-xiso -c` 로 ISO 까지 만든다.

파일마다 원본 SHA1 을 대조해 **엉뚱한 파일에 패치를 씌우는 사고를 막는다.**
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    target_dir = argv[0]
    patch_root = project.work('patch')
    manifest = json.load(io.open(os.path.join(patch_root, 'manifest.json'), encoding='utf-8'))
    xdelta = project.local().get('xdelta_exe', r'C:\claude\utils\xdelta.exe')

    ok = bad = 0
    for e in manifest['files']:
        rel = e['path'].replace('/', os.sep)
        dst = os.path.join(target_dir, rel)
        patch = os.path.join(patch_root, rel + '.xdelta')
        if not os.path.exists(dst):
            print('  !! 대상에 파일이 없다: %s' % rel)
            bad += 1
            continue
        if os.path.getsize(dst) != e['orig_size']:
            print('  !! 크기가 원본과 다르다 (이미 패치됐거나 다른 리전?): %s' % rel)
            bad += 1
            continue
        fd, tmp = tempfile.mkstemp()
        os.close(fd)
        r = subprocess.run([xdelta, '-f', '-d', '-s', dst, patch, tmp],
                           capture_output=True, text=True)
        if not os.path.exists(tmp) or os.path.getsize(tmp) != e['new_size']:
            print('  !! 패치 실패: %s\n%s' % (rel, r.stderr or r.stdout))
            os.path.exists(tmp) and os.remove(tmp)
            bad += 1
            continue
        shutil.move(tmp, dst)
        ok += 1
    print('적용 %d / 실패 %d' % (ok, bad))
    if bad:
        raise SystemExit('일부 실패 — ISO 를 만들지 않는다')

    if '--iso' in argv:
        cfg = project.local()
        out = os.path.join(project.out_dir(), 'Conker LR KR.iso')
        if os.path.exists(out):
            os.remove(out)
        print('ISO 빌드: %s' % out)
        subprocess.run([cfg['xiso_exe'], '-c', target_dir, out], check=True)
        print('-> %s (%.2f GB)' % (out, os.path.getsize(out) / 1024.0 ** 3))


if __name__ == '__main__':
    main(sys.argv[1:])
