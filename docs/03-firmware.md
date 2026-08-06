# Phase 3 — C 펌웨어 온디바이스 추론

> 상태: **온디바이스 추론까지 돈다** (2026-08-06) — 우리 모델 + BH1750 fusion 센서로
> DSP 3 ms / 추론 1~2 ms. **다만 손을 대지 않아도 `cover`/`idle`이 오간다 — 원인 미상.**
> 다음: 실제 lux 실측 (`edge-impulse-daemon` → Studio Live classification)

포크 대상: `~/projects/firmware-pi-rp2xxx` (`008689d`, 2026-07-30)

## 0단계를 먼저 하는 이유

우리 코드가 하나도 안 들어간 상태로 먼저 굽는다. 목적은 정확도가 아니라
**"EI 공식 펌웨어가 이 보드에서 도는가"** 하나다.

여기서 성공해 두면 이후 실패는 전부 우리 변경 탓으로 좁혀진다.
Phase 2에서 부트스트랩으로 얻은 것과 같은 종류의 이득이다 (Ch.9).

**결과: 됐다.** 아래는 그 과정에서 막힌 것들이다.

---

## 환경 구축 (Ubuntu 22.04, 2026-08-06)

### apt 툴체인

```bash
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential
sudo apt install libstdc++-arm-none-eabi-newlib   # Ubuntu/Debian 추가
```

이 노트북에는 이미 다 깔려 있었다.

### pico-sdk

```bash
git clone --recurse-submodules --depth 1 https://github.com/raspberrypi/pico-sdk.git ~/pico-sdk
echo 'export PICO_SDK_PATH="$HOME/pico-sdk"' >> ~/.bashrc
```

받은 버전은 **2.3.0**. `picotool`은 따로 설치하지 않아도 된다 —
SDK가 빌드 중에 `build/_deps/picotool/`로 받아온다 (경고는 뜬다).

### 펌웨어 빌드

```bash
cd ~/projects/firmware-pi-rp2xxx
mkdir -p build && cd build
cmake .. && make -j$(nproc)
```

| 산출물 | 크기 |
|---|---|
| `ei_rp2040_firmware.uf2` | 503 KB |
| `ei_rp2040_firmware.elf` | 8.0 MB |

**upstream을 하나도 안 고치고 통과했다.** 서브모듈도 없다
(FreeRTOS-Kernel이 vendored). `build/`는 이미 gitignore되어 있다.

---

## openocd — Ubuntu 22.04 패키지로는 안 된다

```
$ openocd --version
Open On-Chip Debugger 0.11.0
$ ls /usr/share/openocd/scripts/target/ | grep rp2
(없음)
```

apt의 0.11.0에는 **RP2040 타겟이 없다.** 22.04는 후보 버전도 0.11.0뿐이라
소스 빌드밖에 없다. Raspberry Pi 포크를 쓴다 (rp2040/rp2350 cfg가 들어 있다).

```bash
git clone --recurse-submodules https://github.com/raspberrypi/openocd.git ~/openocd
cd ~/openocd && ./bootstrap
./configure --prefix=$HOME/openocd-install \
  --enable-internal-jimtcl --enable-cmsis-dap --enable-picoprobe
make -j$(nproc) && make install
```

빌드 의존성: `texinfo libhidapi-dev libftdi1-dev` (나머지는 이미 있었다).

시스템 0.11.0은 **덮어쓰지 않고** `~/openocd-install`에 따로 두었다.
다른 프로젝트가 그것을 쓰고 있을 수 있다.

### 막힌 것 2건

**(1) `--depth 1` 클론에는 서브모듈이 안 딸려온다**

```
configure: error: jimtcl is required but not found via pkg-config and system includes
```

openocd는 jimtcl을 서브모듈로 갖는다. `git submodule update --init`으로 받고,
**`bootstrap`을 다시 돌려야 한다** (서브모듈 없이 돌린 bootstrap은 무효다).

**(2) 그래도 안 된다 — `--enable-internal-jimtcl`이 필요하다**

서브모듈을 받고 bootstrap을 다시 해도 같은 에러가 났다.
`./configure --help`는 이 옵션을 **"deprecated"로 표시**하는데,
서브모듈로 받은 jimtcl을 쓰려면 이게 있어야 한다.
옵션 이름과 실제 필요성이 어긋나 있어 도움말만 봐서는 알기 어렵다.

결과: **0.12.0+dev**, CMSIS-DAP v2(USB bulk)·v1(HID) 둘 다 활성.

---

## Debug Probe 연결 — 케이블 두 개가 바뀌어 있었다

처음에는 SWD가 전혀 붙지 않았다.

```
Info : Using CMSIS-DAPv2 interface with VID:PID=0x2e8a:0x000c
Warn : Too long SWD WAIT, issuing DAPABORT
Error: Failed to connect multidrop rp2040.dap0
```

### 무엇을 배제했는가

| 시험 | 결과 |
|---|---|
| adapter speed 5000 / 1000 / 500 / 100 kHz | **전부 동일 실패** → 속도 문제 아님 |
| multidrop 안 쓰는 최소 설정으로 DP IDR 읽기 | `Error connecting DP: cannot read IDR` |
| Pico 분리 후 재연결 | 동일 |
| USB 열거 | Probe·Pico 둘 다 정상 |

`cannot read IDR`은 **타겟이 SWD로 한 바이트도 응답하지 않는다**는 뜻이다.
프로토콜이나 openocd 설정이 아니라 신호가 물리적으로 안 닿는다.

여기서 openocd 설정을 더 만지지 않고 **하드웨어 확인을 요청한 것**이 옳았다.
로그가 "속도 무관 + IDR 자체를 못 읽음"으로 이미 배선을 가리키고 있었다.

### 원인

**Probe의 `D`(SWD) 케이블과 `U`(UART) 케이블이 서로 반대로 꽂혀 있었다.**
두 3핀 커넥터는 생김새가 같아서 바꿔 꽂기 쉽다.

바로잡은 뒤:

```
Info : SWD DPIDR 0x0bc12477 DPv2
Info : multidrop DLPIDR 0x00000001 / 0x10000001
Info : [rp2040.core0] Cortex-M0+ r0p1 processor detected   Examination succeed
Info : [rp2040.core1] Cortex-M0+ r0p1 processor detected   Examination succeed
```

5000 kHz에서 바로 된다. Debugprobe 펌웨어가 1.0.3이라 openocd가
업데이트 경고를 띄우고 low-performance workaround로 도는데, **동작에는
지장이 없었다.** 갱신하면 빨라지는지는 확인하지 않았다.

udev 규칙은 따로 넣지 않았다. `sudo` 없이 접근됐다.

---

## 굽기

```bash
~/openocd-install/bin/openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg \
  -c "adapter speed 5000" \
  -c "program ~/projects/firmware-pi-rp2xxx/build/ei_rp2040_firmware.elf verify reset exit"
```

```
Info : RP2040 rev 2, QSPI Flash win w25q16jv id = 0x1540ef size = 2048 KiB
** Programming Finished **
** Verify Started **
** Verified OK **
```

### MicroPython으로 되돌리기 — .uf2는 openocd로 못 굽는다

C 펌웨어를 구우면 **MicroPython이 지워지고 `src/ei_forwarder.py`로 하던
데이터 수집이 막힌다.** 남은 학습 세션 수집이 여기 걸리므로 복구 경로를
먼저 확인하고 나서 구웠다.

MicroPython은 `.uf2`로만 배포되고 openocd는 `.uf2`를 못 굽는다.
`picotool uf2 convert`는 출력이 UF2로 고정이라 쓸 수 없다
(`ERROR: Output must be a UF2 file`). 그래서 변환기를 만들었다 —
`tools/uf2conv.py`.

```bash
python3 tools/uf2conv.py \
  ~/projects/Datapi_Bringup/RPI_PICO_W-20260406-v1.28.0.uf2 micropython.bin
# base=0x10000000 size=874752 (854.2 KB)

~/openocd-install/bin/openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg \
  -c "adapter speed 5000" \
  -c "program micropython.bin 0x10000000 verify reset exit"
```

> **이 복구 명령은 아직 실행해 보지 않았다.** 변환(base 0x10000000, 틈 없음)까지만
> 확인했다. 안 되면 BOOTSEL 드래그가 남아 있다.

저장소 경로는 `Datapi_Bringup`이다 — **`p`가 소문자**.
`DataPi_edgeimpulse`와 대소문자가 어긋나 있어서 glob으로 한 번에 안 잡힌다.

---

## 확인 — stock 펌웨어가 돈다

굽고 나면 **USB 열거가 바뀐다.**

| | 굽기 전 | 굽기 후 |
|---|---|---|
| Pico | `2e8a:0005` MicroPython Board | **`2e8a:000a` Raspberry Pi Pico** |
| Debug Probe | `2e8a:000c` | `2e8a:000c` |
| 포트 | `/dev/ttyACM0` = Pico | **`/dev/ttyACM0` = Probe, `/dev/ttyACM1` = Pico** |

**포트 번호가 뒤바뀐다.** Probe가 먼저 꽂혀 있으면 ACM0을 가져간다.
`AT+INFO`를 ACM0에 보내면 응답이 없는데, 그건 펌웨어 문제가 아니다.

```
$ python3 at.py /dev/ttyACM1 AT+INFO
*************************
* Edge Impulse firmware *
*************************
Firmware build date  : Aug  6 2026
Firmware build time  : 16:48:18      ← 우리가 빌드한 그것
ML model name        : Demo: Continuous motion recognition
ML model ID          : 43
Edge Impulse version : v1.75.3
Used sensor          : accelerometer
```

빌드 시각이 우리 빌드와 일치한다. AT 서버까지 응답한다.
**0단계 통과.**

---

## 다음 — 고쳐야 할 곳 셋

### 1. 모델 교체 (`ei-model/`)

현재 들어 있는 것은 EI 데모다.

```
EI_CLASSIFIER_PROJECT_ID    43
EI_CLASSIFIER_PROJECT_NAME  "Demo: Continuous motion recognition"
EI_CLASSIFIER_INTERVAL_MS   16
EI_CLASSIFIER_LABEL_COUNT   4
```

Studio에서 우리 모델(ID `1079757`)을 C++ library로 배포해 `ei-model/`을 갈아끼운다.

> **`INTERVAL_MS`를 반드시 확인할 것.** 데모의 `16`은 가속도계 62.5 Hz라는 뜻이다.
> 우리는 16 Hz이므로 **`62.5`가 나와야 맞는다.** 숫자 `16`이 양쪽에 나오지만
> 의미가 정반대다. 여기가 어긋나면 스펙트럼이 통째로 밀린다
> (`docs/00` 4-1절에서 `--frequency`와 `SAMPLE_PERIOD_US`를 항상 같이 바꾸라고
> 적은 것과 같은 함정이다).

창이 3000 ms / 48 샘플로 바뀌었으므로 **온디바이스 리소스도 재측정**한다
(창 2000 ms 시절 3 ms / 1.4 KB / 14.7 KB).

### 2·3. BH1750 센서와 fusion 등록 — **초안 작성됨 (아직 빌드 안 함)**

upstream에 있는 센서는 ADXL345 / Arduino / DHT11 / PDM뿐이라 BH1750은 새로 썼다.

| 항목 | 값 |
|---|---|
| I2C | I2C0, GP4=SDA / GP5=SCL, 주소 `0x23` |
| 모드 | 연속 H-Resolution, **MTreg 31** |
| 주기 | 62500 us = 정확히 16 Hz |

**본보기는 `ei_analogsensor.{h,cpp}`다.** upstream 센서 중 유일한 단일 축이라
구조가 그대로 맞는다 (ADXL345는 3축이라 오히려 멀다).

이 저장소의 `firmware/`에 **upstream과 같은 경로 구조로** 두었다.
참조 저장소(`~/projects/firmware-pi-rp2xxx`)는 건드리지 않았다.

| 파일 | 내용 |
|---|---|
| `firmware/Sensors/BH1750/BH1750.{h,cpp}` | 드라이버. `src/lib/bh1750.py`를 C로 옮긴 것 |
| `firmware/edge-impulse/ingestion-sdk-platform/sensors/ei_bh1750sensor.{h,cpp}` | fusion 등록 + 읽기 함수 |

#### 옮겨온 것들

**버그 2건을 그대로 가져왔다** (`docs/00` 3절). 주석에 `FIX(1)`, `FIX(2)`로 표시했다.
특히 MTreg 환산은 `mt=69`에서만 원본과 일치하므로, MTreg 31을 쓰는 우리
설정에서는 안 고치면 **lux가 1/5 가까이 나온다** (130 lx → 26.3 lx).

**읽기 실패 시 직전 값을 유지하는 것**도 가져왔다 (`src/ei_forwarder.py`의 판단).
Phase 1에서 스트림이 조용히 끊겨 60초 녹화가 401/960 샘플로 잘린 채 "OK"로
업로드된 적이 있다. 잘못된 값 하나보다 조용히 잘린 데이터가 훨씬 해롭다.

**축 이름은 `"lux"`, 단위는 `"lx"`.** Studio의 축 이름과 한 글자라도 다르면
조용히 실패한다 — 에러가 아니라 데이터가 안 붙는다. Phase 1에서 이것 때문에
세 번 재녹화했다 (`docs/01`).

**주파수 목록의 첫 값은 `16.0f`.** 데이터셋 전체가 이 주파수로 수집됐다.

#### 통합에 필요한 변경 — 두 군데뿐

소스 파일은 **CMake가 알아서 잡는다.** `RECURSIVE_FIND_FILE`이 `Sensors`와
`edge-impulse/ingestion-sdk-platform/sensors`를 재귀로 훑기 때문에
파일을 두기만 하면 빌드에 들어간다.

**(1) `CMakeLists.txt`의 `INCLUDES`에 헤더 경로 추가** — `#include "BH1750.h"`가
풀리려면 필요하다.

```cmake
    ${DRIVERS}/DHT11
    ${DRIVERS}/ADXL345
+   ${DRIVERS}/BH1750
    ${DRIVERS}/PDM/src/include
```

**(2) `src/main.cpp`의 `ei_init()`에 초기화 호출 추가**

```cpp
    if (ei_analog_sensor_init() == false) {
        ei_printf("ADC sensor initialization failed\r\n");
    }

+   if (ei_bh1750_sensor_init() == false) {
+       ei_printf("BH1750 initialization failed\r\n");
+   }
```

> **초안 그대로 컴파일이 통과했다** (2026-08-06). BH1750 관련 경고도 없었다.
> 통합에 필요한 변경도 예상대로 위 두 곳뿐이었다.

---

## 통합과 실측 (2026-08-06)

작업 위치: `~/projects/firmware-pi-rp2xxx`의 **`datapi` 브랜치** (`146a728`).
upstream `main`은 건드리지 않았다.

### 모델 배포본 확인 — `INTERVAL_MS` 함정을 피했다

Studio → Deployment → C++ library로 받은 zip을 풀어 **교체 전에** 값부터 봤다.

| 항목 | 값 | |
|---|---|---|
| `EI_CLASSIFIER_PROJECT_ID` | 1079757 | ✓ |
| `EI_CLASSIFIER_PROJECT_NAME` | `datapi light sensor` | ✓ |
| **`EI_CLASSIFIER_INTERVAL_MS`** | **62.5** | ✓ 데모는 `16`이었다 |
| `EI_CLASSIFIER_FREQUENCY` | 16 | ✓ |
| `EI_CLASSIFIER_RAW_SAMPLE_COUNT` | **48** | ✓ 3000 ms × 16 Hz |
| `EI_CLASSIFIER_LABEL_COUNT` | 3 | ✓ |
| 라벨 | `cover`, `idle`, `wave` | ✓ |
| `EI_CLASSIFIER_SENSOR` | `FUSION` | ✓ |

`NN_INPUT_FRAME_SIZE`는 21이다 — 48 샘플이 스펙트럼 특징 21개로 줄어든다.

### fusion 목록에 `Light sensor`가 뜬다

센서 목록은 `AT+SENSORS`가 아니라 **`AT+CONFIG?`** 안에 있다.

```
Name: Light sensor, Max sample length: 144s,
      Frequencies: [16.000000Hz, 12.500000Hz, 10.000000Hz, 8.000000Hz, 1.000000Hz]
```

16 Hz가 첫 값으로 들어갔다. 다른 센서와의 조합(`ADC sensor + Light sensor` 등)도
자동으로 생성된다.

### 온디바이스 성능 — 창을 늘려도 그대로다

```
AT+RUNIMPULSE
Interval: 62.500000ms.   Frame size: 48   Sample length: 3000.000000 ms.
Timing: DSP 3 ms, inference 1 ms, anomaly 0 ms, postprocessing 57 us
```

| 항목 | 창 2000 ms (Phase 2 추정) | 창 3000 ms (실측) |
|---|---|---|
| DSP | 1 ms | **3 ms** |
| 추론 | 3 ms | **1~2 ms** |
| 후처리 | — | 57~62 us |

**창을 1.5배로 늘렸는데 합계는 여전히 5 ms 미만이다.** 목표 100 ms의 5%.
Phase 2에서 "병목은 모델 크기가 아니다"라고 한 것이 온디바이스에서도 확인됐다.

### ⚠️ 미해결 — 손을 대지 않아도 `cover`와 `idle`이 오간다

정지 상태에서 5회 연속:

| 회차 | cover | idle | wave |
|---|---:|---:|---:|
| 1 | 0.664 | 0.332 | 0.004 |
| 2 | 0.008 | **0.992** | 0.000 |
| 3 | **0.996** | 0.000 | 0.000 |
| 4 | 0.500 | 0.500 | 0.000 |
| 5 | 0.027 | **0.973** | 0.000 |

`wave`는 한 번도 오검출되지 않았다. **흔들리는 것은 `cover`↔`idle`뿐**이고,
이는 Studio 테스트에서 남은 유일한 오분류 쌍과 같다 (8/165창).
다만 **여기서의 흔들림은 그 비율보다 훨씬 크다.**

`AT+RUNIMPULSEDEBUG=0`으로 특징값을 봤지만 전부 정규화 후 값이라
(-0.7 ~ 0.2 범위) **실제 lux를 알 수 없다.** `Normalize features`를 켠 결과다.

**원인은 아직 모른다. 추정하지 않는다.** 떠오른 후보는 셋이고 전부 가설이다:

1. 지금 조명이 학습(배경 145 lux)·테스트(90 lux) 어느 쪽과도 다르다.
   사용자 확인: **위치는 그대로지만 "날에 따라 환경 조명이 다를 수 있다".**
   그렇다면 이것은 버그가 아니라 **학습 세션이 1개뿐인 문제가 실제 동작에서
   드러난 것**이다 — Phase 2에서 미해결로 남긴 바로 그 문제다.
2. C 드라이버의 lux 값이 MicroPython 쪽과 다르다 (포팅 오류).
3. `Normalize features`가 `cover`/`idle`을 가르던 절대 레벨을 약화시켰다.
   Studio 2-A에서 이 쌍의 오분류가 12 → 14창으로 **늘었던 것**과 방향이 맞는다.

센서가 가려지지는 않았음을 사용자가 확인했다.

**다음 단계는 실측이다.** `edge-impulse-daemon`으로 Studio에 붙이면 Live
classification에서 실제 lux 파형과 분류를 동시에 볼 수 있다. 코드 변경이 없고,
1·2번 가설을 한 번에 가른다 — MicroPython 수집 때의 파형과 비교하면 된다.

### 굽고 나서 바로 AT를 보내면 응답이 없다

굽기 직후 `AT+INFO`가 빈 응답이었다. 재열거가 끝나기 전이었을 뿐이고,
**몇 초 기다리면 정상이다.**

이때 SWD로 halt해서 core0가 FreeRTOS idle task에 있는 것을 보고
"AT 서버가 안 올라왔다"고 판단했는데 **틀렸다.** FreeRTOS에서 idle task는
정상 상태다. I2C0 레지스터를 읽어보니 `TAR=0x23`(우리 코드가 돌았다는 증거),
버스 idle, `TX_ABRT` 없음 — I2C는 처음부터 멀쩡했다.

> 굽기 직후에는 몇 초 기다린다. 그 전의 무응답으로 원인을 찾기 시작하면
> 멀쩡한 곳을 뒤지게 된다.
