# Conker: Live & Reloaded (Xbox) 구조 조사

대상 = `Conker - Live & Reloaded (Japan, Korea) (En,Ja,Fr,De,Es,It)`
(지역은 Japan/Korea 지만 **수록 언어에 한국어는 없다**. En, Ja, Fr, De, Es, It 6종.)

## 1. 디스크 배치

```
default.xbe                     7.7 MB   실행 파일
media/ArialUni.Ttf             23 MB     ★함정. XBE 어디서도 참조 안 함(XDK 대시보드용)
media/{Sound.xsb,Wave.xwb,dlcustom.xpr}
dvddata/aid/text/<언어>/<씬>/default.bin    ★대사
dvddata/aid/font/<폰트>/default.bin        ★폰트
dvddata/aid/texture/{Avatars,frontend}     팁 화면·MP 레벨 그림
dvddata/aid/zpackage/{Anims,Characters,Effects,General,Level,TimeZone}
dvddata/{Audio,fmv}
```

언어별 텍스트 분량: English 69씬 677 KB / Fr·De·Es·It 각 78씬 ~770 KB /
**Japanese 77씬 581 KB** / LanguageAgnostic 9씬 80 KB.
전체 엔트리 3,664개, `{PMARKER}`·`{PARAGRAPH}` 로 나눈 대사 5,545개, 영문 134,983자.

## 2. 텍스트 컨테이너 (CAFF / LSBL) — 해독 완료

```
0x000 'CAFF' + 버전
0x040 '.data' 서술자   크기 필드 0x50   → 파일크기 = 0x180 + 이 값
0x180 'text' 청크      크기 필드 0x194
      키 풀(UTF-16, `cutscene_W1_BARN_OUTSIDE_11_0` 꼴)
      'LSBL' 청크 = magic(4)+hdr_len(4)+hdr(hdr_len)+count(4)
                    +(u16 idx, u32 off)*count + 종단 6B + UTF-16LE 블롭
```

- ★`off` 는 바이트가 아니라 **문자 수**. 블롭 시작 = 표 끝 + 6.
- 블롭은 **빈틈 없이 연속**, `idx` 는 0..n-1 순차 → 재배치가 단순하다.
- ★**텍스트를 늘릴 수 있다** (N64판의 "줄이는 건 되고 늘리는 건 안 된다" 제약 없음).
  늘리면 델타를 더할 곳: `.data`(0x50) / `text`(0x194) / LSBL hdr[2]·hdr[5](청크 크기)
  / LSBL hdr[3]·hdr[4](LSBL 기준 절대 오프셋). 6개 언어 교차 대조로 확인.
- 언어 디렉터리끼리 엔트리 순서가 같아 인덱스로 영↔일 대응이 된다.

**검증: 전 언어 전 씬 467개 파일 파싱→재조립 바이트 100% 일치** (`tools/caff.py --roundtrip`).

## 3. 폰트 — 해독 완료

```
ConkerFont           74 KB   글리프 199   아틀라스 256x240
ConkerFontJapanese  821 KB   글리프 1187  아틀라스 1024x772
FrontendTitle / FrontendTitleJapanese
```

XBE 문자열 `LocalisationSettings` 밑에 `FrontendTitleJapanese`/`ConkerFontJapanese`/
`FrontendTitle`/`ConkerFont` 가 나란히 있다 → **언어=일본어면 CJK 폰트 세트로 갈아끼운다.**

```
0x4C0 폰트 헤더 16 dword   [1] 글리프배열바이트+904  [5] 글리프 수  [6] 대체문자 U+25A1
0x506 글리프 엔트리 ★18바이트
      u16 ?, u8 xoff, u8 yoff, u8 w, u8 h, u16 u0,u1,v0,v1, u16 advance, u16 FFFF
  +2  charmap ★2048슬롯 x (u16 유니코드, u16 글리프인덱스), FFFF FFFF = 빈칸
 끝   'texture' 청크
.gpu  아틀라스 ★8bpp **선형**(스위즐 없음). W*H 가 .gpu 크기와 오차 0.
```

- ★**UV 분모는 65536 이 아니라 16384** (2.14 고정소수점).
  `픽셀x = u/16384 * 폭 - 0.5`. 65536 으로 잡으면 4248x3208 같은 헛값이 나온다.
- 검증: 万丈上下人日本語時間 을 잘라내 **픽셀 단위로 정확히** 재현했다.
- 일본어 폰트 내역: 한자 803 / 가타카나 84 / 히라가나 80 / 전각 18 / ASCII 99 / Latin-1 96.
  그중 **28x28 균일 셀 한자 185개** (advance 29, xoff 1, yoff 4).

### ★charmap 은 해시표이고, 해시 함수는 아직 못 풀었다
영문 폰트는 코드 오름차순처럼 보이지만 일본어 폰트는 아니다(U+7C21→슬롯 4,
U+96F7→6, U+0020→35). `c % 2048` 도, 곱셈 해시도 맞지 않는다.
→ **문자를 추가할 수 없다.** 대신 **이미 등록된 한자·가나의 글리프를 한글로 다시
그려 재활용**한다. charmap·크기 필드를 하나도 안 건드리므로 위험이 0 이다.

**한글 상한 = 재활용 가능한 칸 = 한자 803 + 가나 164 + 전각 18 = 985자.**
번역문의 고유 음절이 이 수를 넘으면 그때 해시를 풀거나 XBE 를 패치해야 한다.

## 4. 언어 슬롯

XBE 의 언어 목록은 English, Japanese, German, French, Spanish, Italian 6종.
`Korean` 은 Xbox Live 매치메이킹 옵션 문자열로만 등장하고 게임 언어가 아니다.
→ 한글 패치는 **일본어 슬롯에 얹는다**. 실기/xemu 에서 **Xbox 시스템 언어를
일본어로 설정**해야 보인다. 영문 슬롯은 재활용 칸이 Latin-1 96개뿐이라 불가능하다.

## 5. ISO 재빌드

`extract-xiso.exe -c <디렉터리> <출력.iso>` 로 재구성한다.
원본 7.8 GB → 최적화 xiso 4.43 GB (원본에 패딩이 많다).

## 6. 부수 소득 — N64판 번역 품질 오라클

리메이크가 원작 대사를 거의 그대로 썼다. N64판 자막의 **85.1%(2,211/2,597)** 가
공식 일본어 로컬라이즈와 1:1로 붙는다. N64 프로젝트의 `tools/xbox_ref.py` 참조.

## 7. 아직 안 푼 것

1. charmap 해시 함수 (문자 추가에 필요. 재활용으로 우회 중)
2. `FrontendTitleJapanese` 아틀라스 (타이틀 로고용, 크기 미확인)
3. `aid/texture/frontend/tips` — 팁 화면 텍스처 한글화
4. 말풍선 폭/줄바꿈 규칙 (N64판처럼 폭 예산이 있는지)
