# Conker: Live & Reloaded (Xbox) 한글 패치

> **내려받기:** [릴리즈 페이지](https://github.com/hospi0/conker-xbox-kr-patch/releases/latest) — 최신 v0.8. 적용 방법·원본 MD5 는 패치 묶음의 readme 에 있습니다.
>
> 이 저장소에는 도구·번역 텍스트·작업 문서만 있습니다(ROM·빌드 결과물 없음).

---

# Conker: Live & Reloaded (Xbox) 한글 패치

대상 = `Conker - Live & Reloaded (Japan, Korea) (En,Ja,Fr,De,Es,It)`

**일본어 언어 슬롯에 얹는 방식이다.** 실기/xemu 에서 **Xbox 시스템 언어를 일본어로**
설정해야 한글이 보인다. (영문 슬롯은 재활용 가능한 글리프가 96개뿐이라 불가능하다.)

구조 조사 결과 전부 → `docs/survey.md`

## 준비

`config/local.json.example` 을 `local.json` 으로 복사하고 경로를 채운다.

| 키 | 뜻 |
|---|---|
| `game_dir` | extract-xiso 로 푼 게임 디렉터리 |
| `xiso_exe` | `extract-xiso.exe` |
| `out_dir` | 완성 ISO 를 놓을 곳 |
| `font_src` | 한글 TTF 모음 |

## 빌드

```
python tools/build_kr.py                 # 폰트 + 텍스트 패치 (game_dir 제자리 수정)
python tools/build_kr.py --iso           # 이어서 ISO 재빌드
```

원본 파일은 처음 만질 때 `work/orig/` 로 백업되고, 빌드는 **항상 백업본에서 시작**한다.
그래서 몇 번을 돌려도 결과가 같다.

## 도구

| 파일 | 역할 |
|---|---|
| `tools/project.py` | 경로 해석 (`config/local.json` 이 유일한 진실) |
| `tools/caff.py` | CAFF/LSBL 텍스트 컨테이너 파서·재조립기 (`--roundtrip` 검증) |
| `tools/font.py` | 글리프·charmap·아틀라스 (`--atlas`, `--crop 万丈` 로 확인) |
| `tools/render.py` | 한글 음절 → 셀 크기 래스터라이즈 |
| `tools/build_kr.py` | 빌더 |
| `tools/check.py` | 번역 검증 — 글리프·줄 폭·음절 예산 |
| `tools/selftest.py` | 컨테이너 왕복 + 폰트 왕복 + 글리프 크롭 |

## 번역 규칙 (전부 실기 확인)

- ★**반각 스페이스 U+0020 은 강제 개행이다.** 번역문엔 그냥 보통 스페이스를 쓰면
  빌더가 전용 공백 글리프(빈 셀 + advance 12)로 바꿔준다.
- ★**자동 줄바꿈도 글자 축소도 없다.** 줄바꿈은 `\n` 으로 직접 넣는다.
- ★**줄 폭 예산**: 한글 advance 28 + 공백 12.
  **상한 640단위 ≈ 한글 24자 / 권장 460단위 ≈ 17자.**
  근거 = 원본 일본어 말풍선 대사 2,879줄이 중앙 181 / 95% 338 / 99% 459 / 최대 639~719.

## 하드 룰

- ★**charmap 에 문자를 추가하지 않는다.** 해시 함수를 아직 못 풀었다.
  이미 등록된 한자·가나의 글리프를 한글로 다시 그려 쓴다.
  → **한글 상한 985자.** 번역하면서 고유 음절 수를 계속 세야 한다.
- ★음절→코드포인트 배정은 `work/slots.json` 에 영구 보존한다. 배정이 바뀌면
  이미 넣은 텍스트가 전부 깨진다. 새 음절은 **항상 뒤에 덧붙인다**.
- ★패치본 텍스트를 그냥 열면 **한자 낱말처럼 보인다. 정상이다.**
  검증은 원본↔패치본 바이트 대조나 `slots.json` 역매핑 되읽기로 한다.
- ★UV 분모는 65536 이 아니라 **16384**.
- 텍스트는 늘릴 수 있다. 늘리면 `caff.Caff.build()` 가 크기 필드를 자동으로 올린다.
  단 **아직 실기 확인 전**이라, 첫 검증까지는 문자 수를 맞춰 델타 0 으로 간다.
