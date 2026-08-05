"""BH1750 특성 측정 공용 루틴 (Phase 0)

characterize.py(전체 측정)와 gesture_range.py(제스처만 재측정)가 함께 쓴다.
Phase 1의 수집 스크립트도 여기의 샘플링 설정을 그대로 참조한다.

하드웨어 (DataPi v0.3): BH1750  I2C0  주소 0x23,  GP4 = SDA,  GP5 = SCL
"""

from machine import I2C, Pin
from utime import sleep, sleep_ms, ticks_diff, ticks_ms, ticks_us

from bh1750 import BH1750

I2C_SDA = 4
I2C_SCL = 5
BH1750_ADDR = 0x23

# Phase 0 실측으로 확정된 설정 (docs/00-sensor-characterization.md)
#   HIGH mt=31 → 변환 52.6 ms → 상한 19.0 Hz.  여유를 두고 60 ms 주기로 샘플링한다.
#   저해상도(LOW) 모드는 미완결 값을 반환하므로 쓰지 않는다.
BEST_RESOLUTION = BH1750.RESOLUTION_HIGH
BEST_MT = 31
SAMPLE_PERIOD_MS = 60
SAMPLE_HZ = 1000.0 / SAMPLE_PERIOD_MS


def make_sensor():
    i2c = I2C(0, sda=Pin(I2C_SDA), scl=Pin(I2C_SCL))
    found = i2c.scan()
    print("I2C 스캔:", [hex(a) for a in found])
    if BH1750_ADDR not in found:
        raise RuntimeError("BH1750(0x23)을 찾지 못했습니다. GP4=SDA / GP5=SCL 배선을 확인하세요.")
    return BH1750(BH1750_ADDR, i2c)


def use_best_config(sensor):
    sensor.configure(BH1750.MEASUREMENT_MODE_CONTINUOUSLY, BEST_RESOLUTION, BEST_MT)
    sleep_ms(300)


def read_raw(sensor):
    buffer = bytearray(2)
    sensor._i2c.readfrom_into(sensor._address, buffer)
    return buffer[0] << 8 | buffer[1]


def sample(sensor, seconds, period_ms=SAMPLE_PERIOD_MS):
    """고정 주기로 lux를 수집한다. 반환: lux 리스트"""
    n = int(seconds * 1000 / period_ms)
    values = []
    next_tick = ticks_ms()
    for _ in range(n):
        values.append(sensor.measurement)
        next_tick += period_ms
        delay = ticks_diff(next_tick, ticks_ms())
        if delay > 0:
            sleep_ms(delay)
    return values


def stats(values):
    n = len(values)
    lo, hi = min(values), max(values)
    mean = sum(values) / n
    # 인접 샘플 간 변화량 = 신호가 얼마나 '빠른가'
    deltas = [abs(values[i] - values[i - 1]) for i in range(1, n)]
    return {
        "n": n,
        "min": lo,
        "max": hi,
        "mean": mean,
        "range": hi - lo,
        "max_delta": max(deltas),
        "mean_delta": sum(deltas) / len(deltas),
    }


def countdown(seconds, message):
    print("  {}".format(message))
    for i in range(seconds, 0, -1):
        print("  {}...".format(i))
        sleep(1)
    print("  >>> 시작!")
