/* BH1750 ambient light sensor - DataPi v0.3
 * 포팅 근거와 버그 2건은 BH1750.h 주석 참고. */

#include "BH1750.h"

/* I2C0에 OLED(0x3C)·AHT20(0x38)·DS3231(0x68)이 함께 붙어 있다.
 * 400 kHz는 셋 다 견디는 값이고, DataPi 보드에 풀업이 있다. */
#define BH1750_I2C_BAUD 400000

/* 데이터시트 최대 변환 시간(MTreg=69 기준). MTreg에 비례해 조정한다.
 * H-Resolution 180 ms / L-Resolution 24 ms. */
#define BH1750_CONV_MS_HIGH 180
#define BH1750_CONV_MS_LOW  24

BH1750 bh1750_light(i2c0);

BH1750::BH1750(i2c_inst_t *i2cport, uint8_t address)
    : _i2c(i2cport)
    , _address(address)
    , _mode(BH1750_MODE_ONE_TIME)
    , _resolution(BH1750_RES_HIGH)
    , _measurement_time(BH1750_MT_DEFAULT)
{
}

bool BH1750::init(void)
{
    i2c_init(_i2c, BH1750_I2C_BAUD);
    gpio_set_function(I2C0_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(I2C0_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(I2C0_SDA_PIN);
    gpio_pull_up(I2C0_SCL_PIN);

    /* 존재 확인: power_on이 ACK되지 않으면 배선이나 주소가 틀린 것이다.
     * 여기서 걸러야 "스트림은 도는데 값이 전부 0"이 되지 않는다. */
    if (!power_on()) {
        return false;
    }
    return reset();
}

bool BH1750::write_opcode(uint8_t opcode)
{
    int ret = i2c_write_blocking(_i2c, _address, &opcode, 1, false);
    return ret == 1;
}

bool BH1750::write_measurement_time(void)
{
    /* MTreg는 두 번에 나눠 쓴다: 상위 3비트(0x40 | mt>>5), 하위 5비트(0x60 | mt&0x1F) */
    uint8_t high = 0x40 | (_measurement_time >> 5);
    uint8_t low = 0x60 | (_measurement_time & 0x1F);

    return write_opcode(high) && write_opcode(low);
}

bool BH1750::write_measurement_mode(void)
{
    uint8_t opcode = (uint8_t)((_mode << 4) | _resolution);

    if (!write_opcode(opcode)) {
        return false;
    }

    /* FIX(1): 원본은 여기서 _measurement_time(31~254)을 RESOLUTION_LOW(2)와
     * 비교했다. 항상 거짓이라 저해상도에서도 180 ms를 기다렸다. */
    uint32_t conv_ms = (_resolution == BH1750_RES_LOW) ? BH1750_CONV_MS_LOW
                                                       : BH1750_CONV_MS_HIGH;
    /* MTreg에 비례해 늘어난다. MTreg를 줄이면 변환도 빨라진다
     * (mt=31 실측 52.6 ms — docs/00 1절). 넉넉하게 데이터시트 상한을 쓴다. */
    conv_ms = conv_ms * _measurement_time / BH1750_MT_DEFAULT;
    sleep_ms(conv_ms);

    return true;
}

bool BH1750::configure(uint8_t mode, uint8_t resolution, uint8_t measurement_time)
{
    if (measurement_time < BH1750_MT_MIN || measurement_time > BH1750_MT_MAX) {
        return false;
    }

    _mode = mode;
    _resolution = resolution;
    _measurement_time = measurement_time;

    return write_measurement_time() && write_measurement_mode();
}

bool BH1750::read_lux(float &out)
{
    /* 원샷 모드는 읽기 전마다 모드를 다시 써야 하고 변환을 기다린다.
     * 이 프로젝트는 연속 모드만 쓰므로 이 경로는 타지 않는다. */
    if (_mode == BH1750_MODE_ONE_TIME) {
        if (!write_measurement_mode()) {
            return false;
        }
    }

    uint8_t buffer[2];
    if (i2c_read_blocking(_i2c, _address, buffer, 2, false) != 2) {
        return false;
    }

    uint16_t raw = (uint16_t)((buffer[0] << 8) | buffer[1]);

    /* FIX(2): 원본은 (69 / mt)로 나눴다. MTreg를 줄이면 감도가 낮아져 같은
     * 밝기에서 raw가 작아지므로 (mt / 69)로 나눠야 한다. mt=69에서는 두 식이
     * 같아 기본 설정으로만 쓰면 드러나지 않는다.
     * 실측(배경 130 lx): mt=31 raw=70 → 129.9 lx (원본 식은 26.3 lx). */
    float lux = raw / (1.2f * ((float)_measurement_time / (float)BH1750_MT_DEFAULT));

    if (_resolution == BH1750_RES_HIGH_2) {
        lux /= 2.0f;
    }

    out = lux;
    return true;
}
