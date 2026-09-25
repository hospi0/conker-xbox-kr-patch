"""배포 꾸러미 생성 — 사용자가 받아서 바로 쓰는 형태.

    python tools/make_dist.py

    dist/
      한글패치_적용.bat     ← 실행할 것
      읽어주세요.txt
      patch/                ← work/patch 를 그대로 복사

사용자는 여기에 `xdelta3.exe` 와 **extract-xiso 로 푼 게임 폴더**를 같이 두고
배치 파일을 실행하면 된다.

★배치 파일은 반드시 **CP949(ANSI 한국어)** 로 써야 한다. UTF-8 로 쓰면 cmd 가
  기본 코드페이지로 읽어 파일 자체가 깨져 파싱 오류가 난다 — `chcp 65001` 을
  첫 줄에 넣어도 소용없다(줄 단위로 읽으면서 바이트가 어긋난다). 실제로 당했다.
"""
import io
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import project

BAT = r'''@echo off
setlocal EnableDelayedExpansion
title Conker Live and Reloaded - 한글 패치
cd /d "%~dp0"

echo.
echo ============================================================
echo    Conker: Live and Reloaded   한글 패치
echo ============================================================
echo.

rem ---------- 1) xdelta 찾기 ----------
set "XD="
for %%F in (xdelta3.exe xdelta.exe) do (
    if not defined XD if exist "%%~fF" set "XD=%%~fF"
)
if not defined XD (
    for %%F in (xdelta3*.exe) do (
        if not defined XD set "XD=%%~fF"
    )
)
if not defined XD (
    echo  [오류] xdelta3.exe 를 찾을 수 없습니다.
    echo.
    echo         이 배치 파일과 같은 폴더에 xdelta3.exe 를 넣어 주세요.
    echo         내려받기: https://github.com/jmacd/xdelta-gpl/releases
    goto :fail
)
echo  xdelta   : !XD!

rem ---------- 2) 패치 폴더 확인 ----------
set "PDIR=%~dp0patch"
if not exist "!PDIR!\manifest.json" (
    echo  [오류] patch 폴더가 없습니다.
    echo.
    echo         이 배치 파일과 같은 폴더에 patch 폴더를 통째로 두세요.
    goto :fail
)
echo  패치     : !PDIR!

rem ---------- 3) 게임 폴더 찾기 ----------
set "GAME=%~1"
if not defined GAME (
    for /d %%D in ("%~dp0*") do (
        if not defined GAME if exist "%%~fD\default.xbe" set "GAME=%%~fD"
    )
)
if not defined GAME (
    echo  [오류] 게임 폴더를 찾을 수 없습니다.
    echo.
    echo         원본 ISO 를 extract-xiso 로 푼 폴더를 이 배치 파일과
    echo         같은 위치에 두세요. 폴더 안에 default.xbe 가 있어야 합니다.
    echo         또는 그 폴더를 이 배치 파일 위로 끌어다 놓으세요.
    goto :fail
)
if not exist "!GAME!\default.xbe" (
    echo  [오류] 게임 폴더가 아닙니다. default.xbe 가 없습니다.
    echo         !GAME!
    goto :fail
)
echo  게임     : !GAME!
echo.

rem ---------- 4) 먼저 전체 검사 (아무것도 건드리지 않는다) ----------
rem  ★크기가 원본과 같아서 크기로는 패치 여부를 알 수 없다. 해시로만 판별된다.
rem    검사를 다 통과했을 때만 실제로 적용한다 - 중간에 멈춰 반만 패치되는
rem    사고와, 이미 패치한 폴더에 또 적용해 파일이 깨지는 사고를 막는다.
echo  1/2  원본 파일을 검사합니다...
set /a BAD=0
set /a TOT=0
for /f "usebackq tokens=1,* delims= " %%A in ("!PDIR!\checksums.txt") do (
    set /a TOT+=1
    set "WANT=%%A"
    set "REL=%%B"
    set "DST=!GAME!\!REL!"
    if not exist "!DST!" (
        echo       [없음] !REL!
        set /a BAD+=1
    ) else (
        set "GOT="
        for /f "skip=1 tokens=1 delims= " %%H in ('certutil -hashfile "!DST!" SHA1') do (
            if not defined GOT set "GOT=%%H"
        )
        if /i not "!GOT!"=="!WANT!" (
            echo       [불일치] !REL!
            set /a BAD+=1
        )
    )
)
if !BAD! NEQ 0 (
    echo.
    echo ------------------------------------------------------------
    echo  [중단] !TOT! 개 중 !BAD! 개가 원본과 다릅니다.
    echo         파일을 하나도 건드리지 않았습니다.
    echo.
    echo         원인은 대개 다음 중 하나입니다.
    echo           - 이미 패치한 폴더입니다  ^(가장 흔함^)
    echo           - 다른 버전이나 리전의 ISO 를 풀었습니다
    echo.
    echo         원본 ISO 를 다시 풀어서 처음부터 진행해 주세요.
    echo ------------------------------------------------------------
    goto :fail
)
echo       검사 통과 : !TOT! 개 모두 원본입니다.
echo.

rem ---------- 5) 적용 ----------
echo  2/2  패치를 적용합니다...
set /a OK=0
set /a NG=0
for /f "usebackq tokens=1,* delims= " %%A in ("!PDIR!\checksums.txt") do (
    set "REL=%%B"
    set "DST=!GAME!\!REL!"
    set "PF=!PDIR!\!REL!.xdelta"
    if exist "!DST!.tmp" del /q "!DST!.tmp"
    "!XD!" -f -d -s "!DST!" "!PF!" "!DST!.tmp" >nul 2>&1
    if exist "!DST!.tmp" (
        move /y "!DST!.tmp" "!DST!" >nul
        set /a OK+=1
    ) else (
        echo       [실패] !REL!
        set /a NG+=1
    )
)

echo.
echo ------------------------------------------------------------
if !NG! EQU 0 (
    echo    적용 완료 : !OK! / !TOT! 개 파일
    echo.
    echo    이제 extract-xiso 로 다시 ISO 를 만드세요.
    echo       extract-xiso.exe -c "게임폴더" "Conker LR KR.iso"
    echo.
    echo    [중요] 게임 실행 시 Xbox 본체 언어를 일본어로 설정해야
    echo           한글이 표시됩니다.
) else (
    echo    성공 !OK! / 실패 !NG! / 전체 !TOT!
    echo    xdelta3 가 맞는지 확인하고 원본부터 다시 진행해 주세요.
)
echo ------------------------------------------------------------
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
'''

README = """Conker: Live and Reloaded  한글 패치
======================================

■ 준비물
  1. 원본 ISO
       Conker - Live & Reloaded (Japan, Korea) (En,Ja,Fr,De,Es,It).iso
  2. extract-xiso.exe   (ISO 풀기 / 다시 만들기)
       https://github.com/XboxDev/extract-xiso/releases
  3. xdelta3.exe        (패치 적용)
       https://github.com/jmacd/xdelta-gpl/releases

■ 순서
  1) 원본 ISO 를 폴더로 푼다
       extract-xiso.exe -x "Conker - Live & Reloaded ....iso"
     -> default.xbe 가 들어 있는 폴더가 생긴다

  2) 아래 4개를 같은 폴더에 둔다
       한글패치_적용.bat
       patch          (폴더 통째로)
       xdelta3.exe
       (1번에서 푼 게임 폴더)

  3) 한글패치_적용.bat 를 실행한다
     게임 폴더는 자동으로 찾는다. 못 찾으면 게임 폴더를
     배치 파일 위로 끌어다 놓아도 된다.

  4) 다시 ISO 로 묶는다
       extract-xiso.exe -c "게임폴더" "Conker LR KR.iso"

■ 반드시 확인
  ★ 게임 실행 시 Xbox 본체 언어를 [일본어] 로 설정해야 한글이 나옵니다.
    (한국어 슬롯이 없어서 일본어 슬롯에 얹는 방식입니다)

■ 주의
  - 패치는 원본에 한 번만 적용됩니다. 이미 적용한 폴더에 또 실행하면
    실패합니다. 그럴 땐 원본 ISO 를 다시 푸세요.
  - 패치는 텍스트와 폰트 파일만 건드립니다. 파일 크기는 원본과 같습니다.
"""


def main():
    dist = os.path.join(project.ROOT, 'dist')
    src = project.work('patch')
    if not os.path.exists(os.path.join(src, 'manifest.json')):
        raise SystemExit('work/patch 가 없다. tools/make_patch.py 를 먼저 돌릴 것.')
    dst = os.path.join(dist, 'patch')
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)

    # ★CP949 + CRLF — cmd 가 읽을 수 있는 유일한 형태
    with io.open(os.path.join(dist, '한글패치_적용.bat'), 'w',
                 encoding='cp949', newline='\r\n') as f:
        f.write(BAT)
    with io.open(os.path.join(dist, '읽어주세요.txt'), 'w',
                 encoding='cp949', newline='\r\n') as f:
        f.write(README)

    n = sum(len(fs) for _, _, fs in os.walk(dst))
    sz = sum(os.path.getsize(os.path.join(d, x))
             for d, _, fs in os.walk(dst) for x in fs)
    print('dist/ 준비 완료 — 패치 파일 %d개 (%.1f KB)' % (n, sz / 1024.0))
    for x in sorted(os.listdir(dist)):
        print('   ', x)


if __name__ == '__main__':
    main()
