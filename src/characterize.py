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
from utime import sleep, sleep_ms, ticks_diff, ticks_ms

from bh1750 import BH1750

I2C_SDA = 4
I2C_SCL = 5
BH1750_ADDR = 0x23

# 시험할 설정: (이름, 해상도, measurement_time)
# 연속 모드 변환 시간 ~= base * (mt / 69),  base = 저해상도 16 ms / 고해상도 120 ms
CONFIGS = (
    ("LOW  mt=31", BH1750.RESOLUTION_LOW, 31),
    ("LOW  mt=69", BH1750.RESOLUTION_LOW, 69),
    ("HIGH mt=31", BH1750.RESOLUTION_HIGH, 31),
    ("HIGH mt=69", BH1750.RESOLUTION_HIGH, 69),
)

SAMPLE_COUNT = 200  # 설정당 측정 샘플 수


def make_sensor():
    i2c = I2C(0, sda=Pin(I2C_SDA), scl=Pin(I2C_SCL))
    found = i2c.scan()
    print("I2C 스캔:", [hex(a) for a in found])
    if BH1750_ADDR not in found:
        raise RuntimeError("BH1750(0x23)을 찾지 못했습니다. GP4=SDA / GP5=SCL 배선을 확인하세요.")
    return BH1750(BH1750_ADDR, i2c)


def measure_rate(sensor, resolution, measurement_time, n=SAMPLE_COUNT):
    """대기 없이 최대한 빨리 읽었을 때의 읽기 속도와 값 갱신 속도를 잰다.

    반환: (읽기 Hz, 값이 바뀐 횟수, 최소 lux, 최대 lux)
    """
    sensor.configure(BH1750.MEASUREMENT_MODE_CONTINUOUSLY, resolution, measurement_time)

    values = []
    start = ticks_ms()
    for _ in range(n):
        values.append(sensor.measurement)
    elapsed_ms = ticks_diff(ticks_ms(), start)

    read_hz = n * 1000.0 / elapsed_ms if elapsed_ms else 0.0
    changes = sum(1 for i in range(1, n) if values[i] != values[i - 1])
    update_hz = changes * 1000.0 / elapsed_ms if elapsed_ms else 0.0
    return read_hz, update_hz, min(values), max(values)


def part1_sample_rate(sensor):
    print()
    print("=" * 62)
    print("1. 설정별 샘플레이트")
    print("=" * 62)
    print("{:<12} {:>10} {:>10} {:>12} {:>12}".format(
        "설정", "읽기Hz", "갱신Hz", "min lux", "max lux"))
    print("-" * 62)

    results = []
    for name, resolution, mt in CONFIGS:
        read_hz, update_hz, lo, hi = measure_rate(sensor, resolution, mt)
        results.append((name, read_hz, update_hz))
        print("{:<12} {:>10.1f} {:>10.1f} {:>12.1f} {:>12.1f}".format(
            name, read_hz, update_hz, lo, hi))

    print()
    print("주의: '읽기Hz'는 I2C 전송 속도, '갱신Hz'는 센서가 실제로 새 값을 내놓는 속도.")
    print("      학습에 의미 있는 것은 '갱신Hz' 쪽이다. 목표는 25 Hz 이상.")
    return results


def part2_dynamic_range(sensor, label, seconds=5, hz=25):
    """지정한 동작을 하는 동안의 lux 변동 폭을 측정한다."""
    period_ms = int(1000 / hz)
    n = seconds * hz

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

    # 이후 측정은 가장 빠른 설정(저해상도 + 짧은 측정시간)으로 고정
    sensor.configure(BH1750.MEASUREMENT_MODE_CONTINUOUSLY, BH1750.RESOLUTION_LOW, 31)

    print()
    print("=" * 62)
    print("2. 제스처별 동적 범위 (LOW mt=31, 25 Hz 샘플링)")
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
