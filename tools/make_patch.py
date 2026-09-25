"""배포용 xdelta 패치 묶음 생성 — 파일 단위.

    python tools/make_patch.py

★ISO 통짜로 diff 뜨면 안 된다. `extract-xiso -c` 는 원본의 패딩을 전부 벗겨
  **레이아웃을 완전히 새로 짠다**(이 프로젝트에서 7.8GB→4.43GB). 그래서 건드리지
  않은 바이트까지 오프셋이 통째로 밀려 ISO 단위 xdelta 는 사실상 원본 크기만큼
  커진다. 대신 **건드린 파일 하나하나에 대해서만** xdelta 를 뜬다 — 그 파일들은
  ISO 안에서의 위치와 무관하게 항상 자기 완결적인 바이트열이다.

`work/orig/` 에 있는 원본 백업(빌드가 처음 건드릴 때 자동으로 뜬 것) 대
`game_dir` 의 현재(패치된) 상태를 diff 한다. 출력은 `work/patch/<원본과 같은
상대경로>.xdelta` 로, 대상 게임 트리 구조를 그대로 반영한다.
"""
import hashlib
import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project


def sha1(path):
    h = hashlib.sha1()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def xdelta_exe():
    return project.local().get('xdelta_exe', r'C:\claude\utils\xdelta.exe')


def main():
    orig_root = project.work('orig')
    patch_root = project.work('patch')
    manifest = []
    total_src = total_patch = 0
    for dirpath, _, files in os.walk(orig_root):
        for fn in files:
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, orig_root)
            dst = os.path.join(project.game_dir(), rel)
            if not os.path.exists(dst):
                print('  !! 대상 없음: %s' % rel)
                continue
            out = os.path.join(patch_root, rel + '.xdelta')
            d = os.path.dirname(out)
            if not os.path.isdir(d):
                os.makedirs(d)
            r = subprocess.run([xdelta_exe(), '-f', '-e', '-s', src, dst, out],
                               capture_output=True, text=True)
            if not os.path.exists(out):
                print('  !! xdelta 실패: %s\n%s' % (rel, r.stderr or r.stdout))
                continue
            sp = os.path.getsize(src)
            pp = os.path.getsize(out)
            total_src += sp
            total_patch += pp
            manifest.append({'path': rel.replace('\\', '/'), 'orig_size': sp,
                             'patch_size': pp, 'new_size': os.path.getsize(dst),
                             'orig_sha1': sha1(src)})
            print('  %-70s %7d B -> 패치 %6d B' % (rel, sp, pp))

    with io.open(os.path.join(patch_root, 'manifest.json'), 'w',
                encoding='utf-8', newline='\n') as f:
        f.write(json.dumps({'files': manifest}, ensure_ascii=False, indent=1))

    # ★배치 파일이 읽을 수 있는 평문 체크섬 목록.
    #   크기 고정 빌드라 **크기로는 원본/패치본을 구분할 수 없다** — 해시가 유일한
    #   판별 수단이다. 이게 없으면 이미 패치한 폴더에 또 적용해 파일이 깨진다
    #   (2026-08-03 실제로 재현: 79개 중 16개가 이중 적용됐다).
    with io.open(os.path.join(patch_root, 'checksums.txt'), 'w',
                 encoding='ascii', newline='\r\n') as f:
        for e in manifest:
            f.write('%s %s\n' % (e['orig_sha1'], e['path'].replace('/', '\\')))

    print('\n파일 %d개, 원본 합계 %.1f KB, 패치 합계 %.1f KB'
          % (len(manifest), total_src / 1024.0, total_patch / 1024.0))
    print('-> %s' % patch_root)


if __name__ == '__main__':
    main()
