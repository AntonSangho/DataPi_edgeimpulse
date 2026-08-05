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
| GP20 | 버튼 SW1 (풀업, 눌림 = 0) | 녹화 시작/정지 |
| GP21 | NeoPixel WS2812B ×1 | 녹화·추론 상태 표시 |
| GP22 | 부저 MLT-7525 (PWM) | 녹화 시작/끝 비프 |

---

## 진행 단계

| 단계 | 내용 | 문서 |
|---|---|---|
| Phase 0 | 저장소 부트스트랩 + 센서 특성 파악 | [`docs/00-sensor-characterization.md`](docs/00-sensor-characterization.md) |
| Phase 1 | data-forwarder로 데이터 수집 | `docs/01-data-collection.md` |
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

## 파일

| 경로 | 설명 |
|---|---|
| `src/lib/bh1750.py` | BH1750 드라이버 (vendored, 해상도 판별 버그 수정) |
| `src/characterize.py` | Phase 0 — 샘플레이트·동적 범위 실측 |
| `src/ei_forwarder.py` | Phase 1 — 25 Hz CSV 시리얼 출력 (data-forwarder용) |
| `firmware/` | Phase 3 — C / pico-sdk 펌웨어 |

---

## 실행

### 준비

```bash
# MicroPython 펌웨어는 Datapi_Bringup 저장소의 UF2 사용 (v1.28.0)
mpremote fs mkdir :lib
mpremote fs cp src/lib/bh1750.py :lib/
```

### Phase 0 — 센서 특성 측정

```bash
mpremote run src/characterize.py
```

### Phase 1 — 데이터 수집

```bash
mpremote cp src/ei_forwarder.py :main.py
mpremote reset
edge-impulse-data-forwarder --frequency 25
```

---

## 알려진 이슈

### BH1750 드라이버의 해상도 판별 버그

원본 [`pico-bh1750`](https://github.com/flrrth/pico-bh1750)은 `_write_measurement_mode()`와
`measurements()`에서 해상도를 판별할 때 `self._measurement_time`(31~254)을
`RESOLUTION_LOW`(2) 상수와 비교합니다. 항상 거짓이 되므로 저해상도 모드에서도
120~180 ms를 대기하고, 결과적으로 ~8 Hz에 묶입니다.

제스처 인식에는 25 Hz 이상이 필요하므로 `src/lib/bh1750.py`에서 `self._resolution`을
비교하도록 수정했습니다. 상세는 파일 상단 주석 참고.

### DataPi v0.3 배터리 전압 분배 회로

`Datapi_Bringup` README의 "알려진 이슈" 참고 — R9가 GND 대신 VBAT에 연결된 배선 오류가 있습니다.
이 프로젝트는 배터리 ADC를 사용하지 않으므로 영향이 없습니다.

---

## 라이선스

MIT — [`LICENSE`](LICENSE)
`src/lib/bh1750.py`는 [flrrth/pico-bh1750](https://github.com/flrrth/pico-bh1750)에서 가져왔습니다.
