"""Phase 0 - 제스처별 동적 범위 측정 (재측정용)

characterize.py의 2번 파트만 떼어낸 것. 손동작을 다시 잡을 때 40초짜리
변환 시간 측정을 반복하지 않아도 된다.

준비:
  mpremote fs cp src/lib/bh1750.py :lib/bh1750.py
  mpremote fs cp src/lib/bh1750_probe.py :lib/bh1750_probe.py

실행:
  mpremote run src/gesture_range.py

측정 중에는 조명을 바꾸지 말 것. 모든 판정이 idle 대비 상대값이다.
"""

from bh1750_probe import (SAMPLE_HZ, countdown, make_sensor, sample, stats,
                          use_best_config)

SECONDS = 5

# (클래스, 안내문, 판정에 쓸 지표)
#   level    - 배경 대비 밝기 자체가 달라지는 동작 (cover)
#   dynamics - 밝기가 빠르게 오르내리는 동작 (wave, swipe)
GESTURES = (
    ("cover", "손으로 센서를 덮은 채 5초간 유지하세요", "level"),
    ("wave", "센서 위 10~20cm에서 손을 좌우로 계속 흔드세요", "dynamics"),
    ("swipe", "손을 센서 위로 한 번씩 지나가게 하세요 (5초에 3~4회)", "dynamics"),
)

# 판정 문턱
LEVEL_THRESHOLD = 0.3     # 배경 대비 평균 밝기가 30% 이상 달라지면 분리 가능
DYNAMICS_THRESHOLD = 3.0  # 최대 샘플간 변화가 idle의 3배를 넘으면 분리 가능

# idle 오염 판정: 이 값을 넘으면 손·그림자가 지나간 것으로 본다
IDLE_RANGE_RATIO = 0.25
IDLE_RETRIES = 3


def measure(sensor, label, instruction, seconds=SECONDS, lead=5):
    print()
    print("[{}] {}초간 측정합니다.".format(label, seconds))
    countdown(lead, instruction)
    st = stats(sample(sensor, seconds))
    print("  끝.")
    print("  min={:.1f}  max={:.1f}  mean={:.1f}  최대 샘플간 변화={:.1f} lux".format(
        st["min"], st["max"], st["mean"], st["max_delta"]))
    return st


def measure_idle(sensor):
    """idle은 모든 판정의 기준이므로 오염되면 다시 측정한다."""
    for attempt in range(1, IDLE_RETRIES + 1):
        st = measure(sensor, "idle", "센서에서 손을 완전히 치우고 가만히 두세요")
        ratio = st["range"] / st["mean"] if st["mean"] else 999.0

        if ratio <= IDLE_RANGE_RATIO:
            return st

        print()
        print("  !! idle 측정이 오염되었습니다 (변동폭이 평균의 {:.0f}%).".format(ratio * 100))
        print("     측정 중 손이나 그림자가 센서 위를 지나갔을 가능성이 큽니다.")
        if attempt < IDLE_RETRIES:
            print("     다시 측정합니다 ({}/{}).".format(attempt + 1, IDLE_RETRIES))
        else:
            print("     {}회 모두 실패했습니다. 이 값으로 진행하지만 판정은 신뢰할 수 없습니다.".format(IDLE_RETRIES))
            print("     조명이 깜빡이거나(형광등) 사람이 지나다니는 자리인지 확인하세요.")
    return st


def judge(idle, label, st, metric):
    """클래스마다 맞는 지표로 판정한다.

    cover처럼 '덮고 가만히 있는' 동작은 샘플간 변화가 작은 것이 정상이다.
    변화량으로 판정하면 가장 구분하기 쉬운 클래스를 놓친다. 레벨로 봐야 한다.
    """
    level_ratio = abs(st["mean"] - idle["mean"]) / idle["mean"] if idle["mean"] else 0.0
    delta_ratio = st["max_delta"] / idle["max_delta"] if idle["max_delta"] else 999.0

    if metric == "level":
        ok = level_ratio >= LEVEL_THRESHOLD
        detail = "레벨차 {:.0f}% (기준 {:.0f}%)".format(level_ratio * 100, LEVEL_THRESHOLD * 100)
    else:
        ok = delta_ratio >= DYNAMICS_THRESHOLD
        detail = "변화량 idle의 {:.1f}배 (기준 {:.0f}배)".format(delta_ratio, DYNAMICS_THRESHOLD)

    # 주 지표로 떨어져도 다른 지표로 분리되면 살려준다
    fallback = ""
    if not ok:
        if metric == "level" and delta_ratio >= DYNAMICS_THRESHOLD:
            ok, fallback = True, " [변화량으로 분리됨]"
        elif metric == "dynamics" and level_ratio >= LEVEL_THRESHOLD:
            ok, fallback = True, " [레벨로 분리됨]"

    print("  {:<8} {:<12} {}{}".format(
        label, "구분 가능" if ok else "구분 어려움", detail, fallback))
    return ok


def main():
    print("DataPi v0.3 - BH1750 제스처 동적 범위 측정")
    sensor = make_sensor()
    use_best_config(sensor)

    print()
    print("=" * 66)
    print("제스처별 동적 범위 (HIGH mt=31, {:.1f} Hz)".format(SAMPLE_HZ))
    print("=" * 66)
    print("측정 중 조명을 바꾸지 마세요. 모든 판정이 idle 대비 상대값입니다.")

    idle = measure_idle(sensor)
    results = [(label, measure(sensor, label, instruction), metric)
               for label, instruction, metric in GESTURES]

    print()
    print("=" * 66)
    print("판정  (배경 {:.1f} lux 기준)".format(idle["mean"]))
    print("=" * 66)
    for label, st, metric in results:
        judge(idle, label, st, metric)

    print()
    print("표에 옮길 값 — docs/00-sensor-characterization.md 4절")
    print("-" * 66)
    print("| {:<6} | {:>7} | {:>7} | {:>7} | {:>7} | {:>9} |".format(
        "클래스", "min", "max", "mean", "범위", "최대변화"))
    for label, st in [("idle", idle)] + [(l, s) for l, s, _ in results]:
        print("| {:<6} | {:>7.1f} | {:>7.1f} | {:>7.1f} | {:>7.1f} | {:>9.1f} |".format(
            label, st["min"], st["max"], st["mean"], st["range"], st["max_delta"]))


main()
