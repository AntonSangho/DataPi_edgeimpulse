/* BH1750 ambient light sensor - DataPi v0.3 (Raspberry Pi Pico W)
 *
 * src/lib/bh1750.py를 C로 옮긴 것. 원본은 https://github.com/flrrth/pico-bh1750.
 * MicroPython 사본에서 고친 버그 2건을 그대로 가져왔다 —
 * 상세는 docs/00-sensor-characterization.md 3절.
 *
 *   1. 해상도 판별 오류 — 대기 시간을 고를 때 measurement_time(31~254)을
 *      RESOLUTION_LOW(2)와 비교하고 있었다. 항상 거짓이라 저해상도에서도
 *      180 ms를 기다렸다.
 *   2. MTreg lux 환산 방향이 반대 — (69 / mt)로 나눴으나 (mt / 69)여야 한다.
 *      mt=69(기본값)에서만 두 식이 일치해 기본 설정으로는 드러나지 않는다.
 *
 * 이 프로젝트는 L-Resolution을 쓰지 않는다 (미완결 값 반환).
 */

#ifndef BH1750_H
#define BH1750_H

#include <hardware/i2c.h>
#include <pico/stdlib.h>
#include <stdint.h>

/* DataPi v0.3 배선 — RP2040에서 I2C0의 GP4/GP5는 하드웨어 고정이다 */
#define BH1750_I2C_ADDR 0x23
#define I2C0_SDA_PIN    4
#define I2C0_SCL_PIN    5

/* 측정 모드 (opcode 상위 니블) */
#define BH1750_MODE_CONTINUOUS 1
#define BH1750_MODE_ONE_TIME   2

/* 해상도 (opcode 하위 니블) */
#define BH1750_RES_HIGH   0
#define BH1750_RES_HIGH_2 1
#define BH1750_RES_LOW    2

/* MTreg */
#define BH1750_MT_DEFAULT 69
#define BH1750_MT_MIN     31
#define BH1750_MT_MAX     254

class BH1750 {
public:
    BH1750(i2c_inst_t *i2cport, uint8_t address = BH1750_I2C_ADDR);

    /* I2C 초기화 + 센서 존재 확인. 배선이 틀렸으면 false. */
    bool init(void);

    /* 측정 모드/해상도/MTreg를 설정하고 첫 변환이 끝날 때까지 기다린다. */
    bool configure(uint8_t mode, uint8_t resolution, uint8_t measurement_time);

    /* 이 프로젝트의 확정 설정: 연속 H-Resolution, MTreg 31.
     * 변환 시간 실측 52.6 ms < 샘플 주기 62.5 ms. */
    bool use_best_config(void) {
        return configure(BH1750_MODE_CONTINUOUS, BH1750_RES_HIGH, BH1750_MT_MIN);
    }

    /* 최신 측정값(lux). 연속 모드에서는 블로킹하지 않는다.
     * 실패하면 false를 반환하고 out은 건드리지 않는다. */
    bool read_lux(float &out);

    bool power_on(void) { return write_opcode(0x01); }
    bool power_off(void) { return write_opcode(0x00); }
    bool reset(void) { return write_opcode(0x07); }

private:
    bool write_opcode(uint8_t opcode);
    bool write_measurement_time(void);
    bool write_measurement_mode(void);

    i2c_inst_t *_i2c;
    uint8_t _address;
    uint8_t _mode;
    uint8_t _resolution;
    uint8_t _measurement_time;
};

extern BH1750 bh1750_light;

#endif /* BH1750_H */
