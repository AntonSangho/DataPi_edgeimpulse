# RP2040 + Edge Impulse 개발 리서치

작성일: 2026-08-04
기준 저장소: `~/projects/firmware-pi-rp2xxx` (Edge Impulse 공식 펌웨어, commit `008689d` / 2026-07-30 릴리스)

이 문서는 위 공식 펌웨어의 코드를 직접 읽고 정리한 것으로, DataPi 프로젝트에서
RP2040 기반 Edge Impulse 작업을 진행하기 위한 참조 자료입니다.

---

## 1. 참조 저장소 구조

```
src/main.cpp                     ← 진입점 (FreeRTOS 태스크 1개 + AT 명령 루프)
ei-model/                        ← Edge Impulse Studio에서 내보낸 "모델" (교체 대상)
  edge-impulse-sdk/              ← DSP + TFLite Micro + CMSIS-NN
  model-parameters/              ← model_metadata.h, model_variables.h, anomaly_metadata.h
  tflite-model/                  ← tflite_learn_43_3_compiled.cpp (EON 컴파일 결과)
edge-impulse/
  ingestion-sdk-platform/raspberry-rp2xxx/  ← 보드 포팅 (device, flash, AT handlers)
  ingestion-sdk-platform/sensors/           ← 센서별 EI 래퍼 (센서 추가 지점)
  ingestion-sdk-c/                          ← 데이터 수집(ingestion)
  inference/                                ← ei_run_audio_impulse.cpp / ei_run_fusion_impulse.cpp
firmware-sdk/                    ← AT 서버, sensor_aq(CBOR 포맷), 공통 유틸
Sensors/                         ← 순수 드라이버 (ADXL345, DHT11, PDM 마이크, LSM6DSOX 등)
FreeRTOS-Kernel/                 ← FreeRTOS (configNUMBER_OF_CORES=2)
```

**핵심 설계 원칙**

- 저수준 드라이버(`Sensors/`)와 EI 인터페이스(`edge-impulse/.../sensors/`)가 분리되어 있다.
- 모델(`ei-model/`)은 파일 단위로 손대지 않고 **폴더 통째로 교체**한다.
- `CMakeLists.txt`가 `RECURSIVE_FIND_FILE` 매크로로 소스를 자동 수집하므로,
  파일을 추가해도 빌드 스크립트의 소스 목록을 수정할 필요가 없다.

---

## 2. 빌드 환경

```bash
sudo apt install cmake gcc-arm-none-eabi libnewlib-arm-none-eabi build-essential
# Ubuntu/Debian은 libstdc++-arm-none-eabi-newlib 추가 설치가 필요할 수 있음

git clone --recurse-submodules https://github.com/raspberrypi/pico-sdk ~/pico-sdk
export PICO_SDK_PATH=~/pico-sdk

mkdir build && cd build
cmake ..                      # RP2040 (Pico 1)  → ei_rp2040_firmware.uf2
# cmake .. -DPICO_BOARD=pico2    # RP2350 (Pico 2)   → ei_rp2350_firmware.uf2
# cmake .. -DPICO_BOARD=pico2_w  # RP2350 + WiFi
# cmake .. -DDEFINE_DEBUG=ON     # 디버그 로그 활성화 (데이터 수집/플래시 I/O 상세 출력)
make -j$(nproc)
```

산출물 이름은 `CMakeLists.txt:13-17`에서 `PICO_BOARD` 값에 따라 결정된다.

**플래싱**: BOOTSEL 버튼을 누른 채 USB 연결 → USB 대용량 저장장치로 인식됨 →
`.uf2` 파일을 드래그 앤 드롭.

---

## 3. 시나리오 A — 자체 학습 모델 올리기 (가장 흔한 작업)

1. Edge Impulse Studio → **Deployment → C++ library** 내보내기
2. 압축 해제 후 `edge-impulse-sdk/`, `model-parameters/`, `tflite-model/`
   세 폴더로 기존 `ei-model/` 내용을 교체
3. 재빌드. 소스 목록 수정 불필요 —
   `CMakeLists.txt:103-108`의 `RECURSIVE_FIND_FILE`이 해당 폴더의
   `.cpp/.cc/.c/.s`를 전부 자동 수집한다.

### 주의사항

| 항목 | 내용 |
|---|---|
| 포팅 레이어 | `ei-model/edge-impulse-sdk/porting/raspberry/`를 사용한다 (`CMakeLists.txt:108`). 내보낸 SDK에 이 디렉터리가 있는지 확인할 것. |
| 메모리 | RP2040은 SRAM 264KB / 플래시 2MB. `model_metadata.h`의 `EI_CLASSIFIER_TFLITE_ARENA_SIZE`가 크면 링크는 되지만 런타임 arena 할당에서 실패한다. |
| 양자화 | int8 양자화 + EON Compiler 사용을 기본으로 한다. |
| 연산 성능 | RP2040은 Cortex-M0+ (FPU/DSP 확장 없음) → CMSIS-NN 가속이 실질적으로 걸리지 않는다. 오디오 MFCC 같은 무거운 DSP는 추론 주기를 넉넉히 잡아야 한다. **RP2350(Cortex-M33)이 성능상 훨씬 유리**. |

---

## 4. 시나리오 B — 새 센서 추가하기

가장 짧은 참고 예제: `edge-impulse/ingestion-sdk-platform/sensors/ei_analogsensor.{h,cpp}`
(ADC 1축, 약 25줄).

### (1) 헤더에 fusion 디스크립터 정의

`edge-impulse/ingestion-sdk-platform/sensors/ei_mysensor.h`

```cpp
#include "ei_fusion.h"
#define MYSENSOR_AXIS_SAMPLED 3

bool ei_mysensor_init(void);
float *ei_fusion_mysensor_read_data(int n_samples);

static const ei_device_fusion_sensor_t mysensor = {
    "My sensor",                        // Studio 센서 목록에 표시될 이름
    MYSENSOR_AXIS_SAMPLED,              // 축 개수
    { 100.0f, 62.5f, 20.0f },           // 지원 샘플링 주파수
    { {"x","m/s2"}, {"y","m/s2"}, {"z","m/s2"} },  // 축 이름/단위 (읽는 순서와 동일해야 함)
    &ei_fusion_mysensor_read_data       // 읽기 함수 포인터
};
```

### (2) 구현부 — `ei_add_sensor_to_fusion_list()` 호출이 핵심

```cpp
static float data[MYSENSOR_AXIS_SAMPLED];

bool ei_mysensor_init(void) {
    /* Sensors/ 아래 저수준 드라이버 초기화 */
    ei_add_sensor_to_fusion_list(mysensor);
    return true;
}

float *ei_fusion_mysensor_read_data(int n_samples) {
    data[0] = ...; data[1] = ...; data[2] = ...;
    return data;   // 정적 버퍼를 반환할 것 (malloc 금지)
}
```

### (3) `src/main.cpp`의 `ei_init()`에 초기화 추가

```cpp
if (ei_mysensor_init() == false) {
    ei_printf("My sensor init failed\r\n");
}
```

### 부가 사항

- 저수준 드라이버는 `Sensors/` 아래에 두면
  `RECURSIVE_FIND_FILE(DRIVER_FILES "Sensors" "*.cpp")`로 자동 포함된다.
  새 include 경로가 필요할 때만 `CMakeLists.txt`의 `target_include_directories`에 한 줄 추가.
- 동시 사용 센서 모듈이 2개를 넘으면
  `ei_fusion_sensors_config.h`의 `NUM_MAX_FUSIONS`를 늘려야 한다 (기본값 2).
- 같은 파일의 `FUSION_FREQUENCY`는 기본 12.5f.
- **마이크(PDM)는 fusion 경로가 아니다.** `ei_microphone.cpp` +
  `ei_run_audio_impulse.cpp`의 별도 경로를 사용한다.

### 공식 펌웨어에 이미 구현된 센서 (참고용)

`ei_accelerometer` (ADXL345), `ei_inertialsensor` (LSM6DSOX),
`ei_dht11sensor`, `ei_ultrasonicsensor` (Grove), `ei_analogsensor` (ADC),
`ei_rp2xxx_internal_temperature` (내장 온도센서), `ei_microphone` (PDM)

---

## 5. 시나리오 C — 독립 동작(standalone) 애플리케이션

현재 `src/main.cpp`는 **AT 명령 기반 펌웨어**다. USB CDC로 명령을 받아
Studio / `edge-impulse-daemon`과 대화하는 구조이며, 부팅 후 곧바로 추론하는
제품 코드가 아니다.

- **데이터 수집·모델 검증 단계**: 그대로 두고 `edge-impulse-daemon`으로 연결해 사용.
- **독립 동작 제품**: `ei_main()`의 AT 루프 대신
  `ei_start_impulse(false, false, false)` (`edge-impulse/inference/ei_run_impulse.h`)를
  호출하고 `ei_run_impulse()`를 루프에서 돌리거나, `run_classifier()`를 직접 호출하는
  태스크를 `xTaskCreate`로 추가한다.
- `main.cpp`의 `ei_main` 태스크 스택은 1024 워드로 생성되는데,
  **추론 태스크에는 부족할 수 있으므로 반드시 늘려야 한다.**

### main.cpp의 현재 흐름

```
main()
 ├─ stdio_init_all()
 ├─ (Pico 2 W인 경우) cyw43_arch_init()
 ├─ xTaskCreate(ei_main, "ei_main", 1024, ...)
 └─ vTaskStartScheduler()

ei_main()
 ├─ ei_init()
 │   ├─ ei_sleep(2000)              // 시리얼 포트 준비 대기
 │   ├─ 각 센서 init (실패해도 계속 진행)
 │   ├─ dev->init_device_id()       // RP2XXX는 main() 시작 전 device id 초기화 불가
 │   ├─ dev->load_config()
 │   └─ at = ei_at_init(dev)
 └─ while(true) { 시리얼 바이트 읽어 at->handle(data) }
```

---

## 6. 개발 중 확인 방법

```bash
edge-impulse-daemon          # 보드를 Studio 프로젝트에 연결, 데이터 수집
edge-impulse-run-impulse     # 보드에서 추론 결과 스트리밍
```

직접 확인하려면 USB CDC 시리얼에 접속한다
(`pico_enable_stdio_usb`=1, `pico_enable_stdio_uart`=0으로 설정되어 있음).
`AT+HELP`를 입력하면 지원 명령 목록이 출력된다.
지원 센서 목록은 `AT+SAMPLESETTINGS` / `AT+SENSORS` 계열 명령으로 확인 가능하며,
구현은 `edge-impulse/ingestion-sdk-platform/raspberry-rp2xxx/ei_at_handlers.cpp`에 있다.

---

## 7. DataPi 프로젝트 적용 시 검토 항목

- [ ] 타깃 보드 확정: RP2040(Pico W) vs RP2350(Pico 2) — 모델 크기·DSP 부하에 따라 결정
- [ ] DataPi 온보드 센서(I2C 센서, 마이크 등)를 fusion 리스트에 등록할 래퍼 작성
- [ ] `NUM_MAX_FUSIONS` 값을 DataPi 센서 개수에 맞게 조정
- [ ] AT 펌웨어 모드 / standalone 추론 모드 중 어느 쪽으로 갈지 결정
- [ ] arena size 실측 (RP2040 264KB SRAM 제약 확인)

---

## 참고 링크

- 공식 문서: https://docs.edgeimpulse.com/docs/raspberry-pi-rp2040
- 데이터 포워더(펌웨어 빌드 없이 임의 센서 수집): https://docs.edgeimpulse.com/docs/cli-data-forwarder
- Pico 시작 가이드(Windows/macOS 툴체인): https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf
