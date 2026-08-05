"""Phase 0 - BH1750 변환 시간·잡음 측정

목적: 손동작 제스처를 시간축 패턴으로 담아낼 만큼 이 센서가 빠른지 확인한다.
      ("AI at the Edge" Ch.6 - Technological Feasibility)

제스처별 동적 범위 측정은 src/gesture_range.py로 분리했다.
이 스크립트는 손동작이 필요 없으므로 조도가 고정된 상태에서 그냥 돌리면 된다.

준비:
  mpremote fs mkdir :lib
  mpremote fs cp src/lib/bh1750.py :lib/bh1750.py
  mpremote fs cp src/lib/bh1750_probe.py :lib/bh1750_probe.py

실행:
  mpremote run src/characterize.py
"""

from utime import sleep_ms, ticks_diff, ticks_us

from bh1750 import BH1750
from bh1750_probe import BEST_MT, BEST_RESOLUTION, make_sensor, read_raw

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

NOISE_SAMPLES = 300
CONV_TRIALS = 8


def measure_conversion_time(sensor, resolution, measurement_time, trials=CONV_TRIALS):
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


def measure_noise(sensor, resolution, measurement_time, n=NOISE_SAMPLES):
    """조도가 고정된 상태에서 raw 레지스터가 얼마나 흔들리는지 잰다."""
    sensor.configure(BH1750.MEASUREMENT_MODE_CONTINUOUSLY, resolution, measurement_time)
    sleep_ms(300)

    values = []
    for _ in range(n):
        values.append(read_raw(sensor))
        sleep_ms(2)

    jitter = sum(abs(values[i] - values[i - 1]) for i in range(1, n)) / (n - 1)
    return min(values), max(values), jitter


def main():
    print("DataPi v0.3 - BH1750 변환 시간·잡음 측정")
    print("조도가 고정된 상태에서 측정하세요 (손을 센서 근처에 두지 말 것).")
    sensor = make_sensor()

    print()
    print("=" * 76)
    print("{:<12} {:>10} {:>8} {:>8} {:>12} {:>10}".format(
        "설정", "변환ms", "최대Hz", "이론ms", "raw 범위", "지터cnt"))
    print("-" * 76)

    for name, resolution, mt in CONFIGS:
        theory = (16 if resolution == BH1750.RESOLUTION_LOW else 120) * mt / 69
        conv_ms = measure_conversion_time(sensor, resolution, mt)
        lo, hi, jitter = measure_noise(sensor, resolution, mt)
        max_hz = 1000.0 / conv_ms if conv_ms else 0.0
        print("{:<12} {:>10.1f} {:>8.1f} {:>8.1f} {:>12} {:>10.2f}".format(
            name, conv_ms, max_hz, theory, "{}~{}".format(lo, hi), jitter))

    print()
    print("판정 기준:")
    print("  - 변환ms가 이론값보다 크게 짧으면 그 설정은 완결되지 않은 값을 돌려주고 있다.")
    print("  - 지터는 조도가 고정된 상태의 잡음. 이것이 제스처 신호보다 크면 쓸 수 없다.")
    print()
    print("확정 설정: HIGH mt={} → 다음은 src/gesture_range.py로 제스처를 측정한다.".format(BEST_MT))


main()
