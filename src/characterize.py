"""BH1750 조도 센서 특성 측정 (Phase 0)

목적: 손동작 제스처를 시간축 패턴으로 담아낼 만큼 이 센서가 빠르고 민감한지
      먼저 확인한다. ("AI at the Edge" Ch.6 - Technological Feasibility)

하드웨어 (DataPi v0.3):
  BH1750  I2C0  주소 0x23,  GP4 = SDA,  GP5 = SCL

측정 항목:
  1. 설정별 실제 달성 샘플레이트 (Hz)
  2. 값이 실제로 갱신되는 속도 (연속 모드에서 레지스터가 바뀌는 빈도)
  3. 손 덮기 / 흔들기에서의 lux 동적 범위

실행:
  mpremote fs mkdir :lib
  mpremote fs cp src/lib/bh1750.py :lib/
  mpremote run src/characterize.py
"""

from machine import I2C, Pin
from utime import sleep, sleep_ms, ticks_diff, ticks_ms, ticks_us

from bh1750 import BH1750

I2C_SDA = 4
I2C_SCL = 5
BH1750_ADDR = 0x23

# 시험할 설정: (이름, 해상도, measurement_time)
# 연속 모드 변환 시간 ~= base * (mt / 69),  base = 저해상도 16 ms / 고해상도 120 ms
CONFIGS = (
    ("HIGH mt=31", BH1750.RESOLUTION_HIGH, 31),
    ("HIGH mt=45", BH1750.RESOLUTION_HIGH, 45),
    ("HIGH mt=69", BH1750.RESOLUTION_HIGH, 69),
    ("HIGH2 mt=31", BH1750.RESOLUTION_HIGH_2, 31),
    ("LOW  mt=31", BH1750.RESOLUTION_LOW, 31),
    ("LOW  mt=69", BH1750.RESOLUTION_LOW, 69),
)

# Phase 0 실측으로 확정된 설정 (docs/00-sensor-characterization.md 참고)
#   HIGH mt=31 → 변환 52.6 ms → 최대 19.0 Hz.  여유를 두고 60 ms 주기로 샘플링한다.
BEST_RESOLUTION = BH1750.RESOLUTION_HIGH
BEST_MT = 31
SAMPLE_HZ = 16.6
SAMPLE_PERIOD_MS = 60

SAMPLE_COUNT = 300  # 설정당 잡음 측정 샘플 수


def make_sensor():
    i2c = I2C(0, sda=Pin(I2C_SDA), scl=Pin(I2C_SCL))
    found = i2c.scan()
    print("I2C 스캔:", [hex(a) for a in found])
    if BH1750_ADDR not in found:
        raise RuntimeError("BH1750(0x23)을 찾지 못했습니다. GP4=SDA / GP5=SCL 배선을 확인하세요.")
    return BH1750(BH1750_ADDR, i2c)


def read_raw(sensor):
    buffer = bytearray(2)
    sensor._i2c.readfrom_into(sensor._address, buffer)
    return buffer[0] << 8 | buffer[1]


def measure_conversion_time(sensor, resolution, measurement_time, trials=8):
    """변환 시간 = 레지스터를 0으로 지우고 측정을 재시작한 뒤 새 값이 채워질 때까지의 시간.

    주의: reset()만으로는 연속 측정이 재개되지 않는다. 모드 명령을 다시 써야 한다.
    """
    sensor.configure(BH1750.MEASUREMENT_MODE_CONTINUOUSLY, resolution, measurement_time)
    sleep_ms(300)

    mode_cmd = bytes([resolution | (BH1750.MEASUREMENT_MODE_CONTINUOUSLY << 4)])
    times = []
    for _ in range(trials):
        sensor.reset()
        sensor._i2c.writeto(sensor._address, mode_cmd)
        start = ticks_us()
        while read_raw(sensor) == 0:
            if ticks_diff(ticks_us(), start) > 2000000:
                break
        times.append(ticks_diff(ticks_us(), start) / 1000.0)
        sleep_ms(50)

    times.sort()
    return times[len(times) // 2]


def measure_noise(sensor, resolution, measurement_time, n=SAMPLE_COUNT):
    """조도가 고정된 상태에서 raw 레지스터가 얼마나 흔들리는지 잰다.

    반환: (raw 최소, raw 최대, 인접 샘플 변화량의 평균 = 지터)
    """
    sensor.configure(BH1750.MEASUREMENT_MODE_CONTINUOUSLY, resolution, measurement_time)
    sleep_ms(300)

    values = []
    for _ in range(n):
        values.append(read_raw(sensor))
        sleep_ms(2)

    jitter = sum(abs(values[i] - values[i - 1]) for i in range(1, n)) / (n - 1)
    return min(values), max(values), jitter


def part1_sample_rate(sensor):
    print()
    print("=" * 76)
    print("1. 설정별 변환 시간과 잡음 (조도가 고정된 상태에서 측정할 것)")
    print("=" * 76)
    print("{:<12} {:>10} {:>8} {:>8} {:>12} {:>10}".format(
        "설정", "변환ms", "최대Hz", "이론ms", "raw 범위", "지터cnt"))
    print("-" * 76)

    results = []
    for name, resolution, mt in CONFIGS:
        theory = (16 if resolution == BH1750.RESOLUTION_LOW else 120) * mt / 69
        conv_ms = measure_conversion_time(sensor, resolution, mt)
        lo, hi, jitter = measure_noise(sensor, resolution, mt)
        max_hz = 1000.0 / conv_ms if conv_ms else 0.0
        results.append((name, conv_ms, max_hz, jitter))
        print("{:<12} {:>10.1f} {:>8.1f} {:>8.1f} {:>12} {:>10.2f}".format(
            name, conv_ms, max_hz, theory, "{}~{}".format(lo, hi), jitter))

    print()
    print("판정 기준:")
    print("  - 변환ms가 이론값과 크게 다르면 그 설정은 완결되지 않은 값을 돌려주고 있다.")
    print("  - 지터는 조도가 고정된 상태의 잡음. 이것이 제스처 신호보다 크면 쓸 수 없다.")
    return results


def part2_dynamic_range(sensor, label, seconds=5, period_ms=SAMPLE_PERIOD_MS):
    """지정한 동작을 하는 동안의 lux 변동 폭을 측정한다."""
    n = int(seconds * 1000 / period_ms)

    print()
    print("[{}] {}초간 동작하세요. 3초 뒤 시작합니다...".format(label, seconds))
    for i in (3, 2, 1):
        print("  {}...".format(i))
        sleep(1)
    print("  시작!")

    values = []
    next_tick = ticks_ms()
    for _ in range(n):
        values.append(sensor.measurement)
        next_tick += period_ms
        delay = ticks_diff(next_tick, ticks_ms())
        if delay > 0:
            sleep_ms(delay)
    print("  끝.")

    lo, hi = min(values), max(values)
    mean = sum(values) / len(values)
    # 인접 샘플 간 변화량의 최대치 = 제스처의 '빠르기'를 보여주는 지표
    max_delta = max(abs(values[i] - values[i - 1]) for i in range(1, len(values)))
    ratio = (hi / lo) if lo > 0 else float("inf")

    print("  min={:.1f}  max={:.1f}  mean={:.1f}  max/min={:.1f}배  최대 샘플간 변화={:.1f} lux".format(
        lo, hi, mean, ratio, max_delta))
    return {"label": label, "min": lo, "max": hi, "mean": mean,
            "ratio": ratio, "max_delta": max_delta}


def main():
    print("DataPi v0.3 - BH1750 특성 측정")
    sensor = make_sensor()

    part1_sample_rate(sensor)

    # 이후 측정은 Phase 0에서 확정한 설정으로 고정
    sensor.configure(BH1750.MEASUREMENT_MODE_CONTINUOUSLY, BEST_RESOLUTION, BEST_MT)

    print()
    print("=" * 62)
    print("2. 제스처별 동적 범위 (HIGH mt=31, {} Hz 샘플링)".format(SAMPLE_HZ))
    print("=" * 62)

    stats = [
        part2_dynamic_range(sensor, "idle - 아무것도 하지 않기"),
        part2_dynamic_range(sensor, "cover - 손으로 센서 덮고 유지하기"),
        part2_dynamic_range(sensor, "wave - 센서 위에서 손 흔들기"),
        part2_dynamic_range(sensor, "swipe - 손을 한 번씩 지나가게 하기"),
    ]

    print()
    print("=" * 62)
    print("3. 판정")
    print("=" * 62)
    idle = stats[0]
    for s in stats[1:]:
        # idle 대비 변동 폭이 충분히 큰가?
        separable = s["max_delta"] > max(idle["max_delta"] * 3, 1.0)
        print("  {:<40} {}".format(
            s["label"], "구분 가능" if separable else "구분 어려움 - 조명 조건 재검토"))

    print()
    print("결과를 docs/00-sensor-characterization.md 에 기록하세요.")


main()
