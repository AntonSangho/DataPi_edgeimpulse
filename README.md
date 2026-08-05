# DataPi × Edge Impulse

DataPi v0.3(Raspberry Pi Pico W)에 **Edge Impulse를 어떻게 적용할지 그 방법을 찾는** 프로젝트입니다.
제품을 만드는 것이 목적이 아니라, 워크플로를 한 번 끝까지 통과시키고 **재현 가능한 절차서로 남기는 것**이 산출물입니다.

첫 과제는 반응이 가장 빠른 **조도 센서(BH1750) 기반 손동작 제스처 인식**입니다.

참고서: *AI at the Edge* (Daniel Situnayake & Jenny Plunkett, O'Reilly 2023)
사전 조사: [`RESEARCH.md`](RESEARCH.md) — Edge Impulse 공식 RP2040 펌웨어 코드 리딩 결과

---

## 왜 2단계인가

| | DataPi 브링업 | Edge Impulse 공식 RP2040 |
|---|---|---|
| 스택 | MicroPython v1.28.0 + mpremote | C / pico-sdk + FreeRTOS |
| 저장소 | [`Datapi_Bringup`](https://github.com/AntonSangho/Datapi_Bringup) | [`firmware-pi-rp2xxx`](https://github.com/edgeimpulse/firmware-pi-rp2xxx) |

두 스택이 갈리기 때문에 한 번에 가지 않습니다.

1. **1단계** — MicroPython을 그대로 두고 `edge-impulse-data-forwarder`로 수집·학습까지 통과 (펌웨어 빌드 0)
2. **2단계** — C 펌웨어에 BH1750 fusion 센서를 추가해 온디바이스 추론 완성

1단계에서 얻은 데이터셋과 모델은 2단계에서 그대로 재사용됩니다.

---

## 하드웨어 연결 정보

### I2C0 (GP4 = SDA, GP5 = SCL — RP2040 하드웨어 고정)

| 주소 | 부품 | 용도 | 이 프로젝트에서 |
|---|---|---|---|
| `0x23` | BH1750 | 조도 (lux) | **주 센서** |
| `0x3C` | SSD1306 | OLED 128×64 | 추론 결과 표시 |
| `0x38` | AHT20 | 온습도 | 미사용 |
| `0x68` | DS3231 | RTC | 미사용 |

### GPIO

| 핀 | 부품 | 이 프로젝트에서 |
|---|---|---|
| GP21 | NeoPixel WS2812B ×1 | 동작 표시 (밝기 3 — 조도 영향 없음) |

---

## 진행 단계

| 단계 | 내용 | 문서 |
|---|---|---|
| Phase 0 | 저장소 부트스트랩 + 센서 특성 파악 | [`docs/00-sensor-characterization.md`](docs/00-sensor-characterization.md) |
| Phase 1 | data-forwarder로 데이터 수집 | [`docs/01-data-collection.md`](docs/01-data-collection.md) |
| Phase 2 | Impulse 설계·학습 | `docs/02-model.md` |
| Phase 3 | C 펌웨어 온디바이스 추론 | `docs/03-firmware.md` |
| Phase 4 | 평가와 회고 → **최종 절차서** | `docs/DATAPI_EI_GUIDE.md` |

---

## 분류 클래스

| 클래스 | 동작 |
|---|---|
| `idle` | 무동작 (밝은 실내 / 어두운 방 / 형광등 깜빡임 포함) |
| `wave` | 센서 위에서 손 좌우로 흔들기 |
| `cover` | 손으로 덮어 가린 채 유지 |
| `swipe` | 손이 한 번 지나감 |

`idle`은 실사용 오검출을 좌우하므로 여러 조명 조건에서 넉넉히 수집합니다 (Ch.7 representative dataset).

---

## 확정 파라미터 (Phase 0 실측 결과)

| 항목 | 값 | 근거 |
|---|---|---|
| 해상도 | H-Resolution | 저해상도는 미완결 값 반환 (아래 이슈 참고) |
| MTreg | 31 | 데이터시트 최솟값 = 최고 속도 |
| 변환 시간 | 52.6 ms (상한 19.0 Hz) | 실측 |
| 샘플 주기 | **62.5 ms (16 Hz)** | Studio 기록 간격과 일치 (여유 19%) |
| 창 길이 | **2000 ms (32 샘플)** | 3초 지연은 제스처에 너무 느림 |
| stride | 500 ms | |

### 제스처 분리도 (배경 129.8 lx)

| 클래스 | mean | 최대 샘플간 변화 | 판정 근거 |
|---|---:|---:|---|
| `idle` | 129.8 | 1.9 | 기준 (1.9 lx = 1 LSB, 잡음 바닥) |
| `cover` | 5.7 | 1.9 | 레벨차 **96%** |
| `wave` | 107.8 | 57.5 | 변화량 idle의 **31배** |
| `swipe` | 124.6 | 53.8 | 변화량 idle의 **29배** |

세 제스처 모두 분리 가능합니다. 다만 **`wave`와 `swipe`는 진폭 특성이 거의 같아
(차이 2~7%) 주파수 성분만이 유일한 분리 근거**입니다 — Phase 2에서 Spectral Analysis가
선택이 아니라 필수인 이유입니다.

---

## 파일

| 경로 | 설명 |
|---|---|
| `src/lib/bh1750.py` | BH1750 드라이버 (vendored, 버그 2건 수정) |
| `src/lib/bh1750_probe.py` | 공용 샘플링·통계 루틴 (Phase 1에서도 재사용) |
| `src/characterize.py` | Phase 0 — 변환 시간·잡음 실측 (손동작 불필요) |
| `src/gesture_range.py` | Phase 0 — 제스처별 동적 범위 실측 (손동작 필요) |
| `src/ei_forwarder.py` | Phase 1 — 16 Hz lux 스트리머 |
| `firmware/` | Phase 3 — C / pico-sdk 펌웨어 |

---

## 실행

### 준비

```bash
# MicroPython 펌웨어는 Datapi_Bringup 저장소의 UF2 사용 (v1.28.0)
mpremote fs mkdir :lib
mpremote fs cp src/lib/bh1750.py :lib/
mpremote fs cp src/lib/bh1750_probe.py :lib/
```

### Phase 0 — 센서 특성 측정

```bash
mpremote run src/characterize.py    # 변환 시간·잡음 (조도 고정, 약 40초)
mpremote run src/gesture_range.py   # 제스처별 동적 범위 (손동작 필요)
```

### Phase 1 — 데이터 수집

```bash
mpremote cp src/ei_forwarder.py :main.py
mpremote reset
edge-impulse-data-forwarder --frequency 16
```

---

## 알려진 이슈

### BH1750 드라이버 버그 2건 (수정됨)

원본 [`pico-bh1750`](https://github.com/flrrth/pico-bh1750)에서 발견해 `src/lib/bh1750.py`에서 수정했습니다.

1. **해상도 판별 오류** — `self._measurement_time`(31~254)을 `RESOLUTION_LOW`(2) 상수와 비교.
   항상 거짓이라 저해상도 모드에서도 180 ms를 대기합니다.
2. **MTreg lux 환산 방향이 반대** — `(69 / mt)`로 나누고 있으나 `(mt / 69)`여야 합니다.
   `mt = 69`(기본값)에서만 우연히 일치해서 드러나지 않습니다.
   실측: 배경 128 lx에서 원본 식은 `mt=31`일 때 **26.3 lx**를 반환합니다.

상세와 검증 데이터는 [`docs/00-sensor-characterization.md`](docs/00-sensor-characterization.md) 3절 참고.

### 저해상도 모드는 사용 불가

L-Resolution 모드는 변환이 끝나기 전의 미완결 값을 반환합니다. 조도가 고정된 상태에서도
raw가 `0~128`을 오가며, 지터가 고해상도의 500배입니다. 자세한 측정치는 위 문서 1절 참고.

### DataPi v0.3 배터리 전압 분배 회로

`Datapi_Bringup` README의 "알려진 이슈" 참고 — R9가 GND 대신 VBAT에 연결된 배선 오류가 있습니다.
이 프로젝트는 배터리 ADC를 사용하지 않으므로 영향이 없습니다.

---

## 라이선스

MIT — [`LICENSE`](LICENSE)
`src/lib/bh1750.py`는 [flrrth/pico-bh1750](https://github.com/flrrth/pico-bh1750)에서 가져왔습니다.
