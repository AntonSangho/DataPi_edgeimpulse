# Phase 3 — C 펌웨어 온디바이스 추론

> 상태: **0단계 완료** (2026-08-06) — 손대지 않은 EI 공식 펌웨어가 DataPi의
> Pico에서 빌드·굽기·부팅·AT 응답까지 전부 된다.
> 다음: 우리 모델 배포 → `ei-model/` 교체 → BH1750 센서 작성

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

### 2. BH1750 센서 (`Sensors/`)

현재 있는 것은 ADXL345 / Arduino / DHT11 / PDM뿐이다. BH1750은 새로 쓴다.

| 항목 | 값 |
|---|---|
| I2C | I2C0, GP4=SDA / GP5=SCL, 주소 `0x23` |
| 모드 | H-Resolution, **MTreg 31** |
| 주기 | 62500 us = 정확히 16 Hz |

`src/lib/bh1750.py`에서 고친 **버그 2건을 C로 옮길 때 같이 가져가야 한다.**
MTreg lux 환산이 반대로 되어 있던 것이 기본 설정에서는 안 드러난다.

### 3. fusion 디스크립터 — 축 이름 `lux`

`firmware-sdk/ei_fusion.h`에 등록한다.
Phase 1에서 축 이름 때문에 **세 번 재녹화**했다 (`docs/01` 참고).
Studio의 축 이름과 한 글자라도 다르면 조용히 실패한다.
