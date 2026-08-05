"""Phase 1 - Edge Impulse data-forwarder용 조도 스트리머

BH1750의 lux 값을 16.6 Hz로 USB CDC에 한 줄씩 출력한다.
edge-impulse-data-forwarder가 이 줄을 읽어 Studio로 올린다.

준비:
  mpremote fs mkdir :lib
  mpremote fs cp src/lib/bh1750.py :lib/bh1750.py
  mpremote fs cp src/lib/bh1750_probe.py :lib/bh1750_probe.py

실행:
  mpremote cp src/ei_forwarder.py :main.py    # 부팅 시 자동 실행
  mpremote reset
  edge-impulse-data-forwarder --frequency 16  # 축 이름은 lux

--- 왜 버튼으로 녹화를 제어하지 않는가 ---

data-forwarder는 단방향이다. 장치는 계속 스트리밍하고, 어느 구간을 어떤 라벨로
저장할지는 Studio의 Data acquisition 탭이 정한다. 장치는 녹화 시작 시점을 알 수 없다.

그래서 클래스마다 **긴 연속 세션**을 녹화한다 (권장 30~60초). 녹화 전체가 한 라벨이므로
시작 정렬이 필요 없고, 창 분할은 EI가 알아서 한다.

--- 버튼의 실제 용도: 페이스 메트로놈 ---

wave와 swipe는 진폭 특성이 거의 같고 **동작 빈도만 다르다** (docs/00 4-1절).
따라서 swipe를 일정한 속도로 반복하는 것이 중요하다. 버튼을 누르면 부저가
일정 간격으로 울려 속도를 잡아준다. 스트리밍은 멈추지 않는다.

  버튼(GP20) 짧게 누름 → OFF → 0.8초 → 1.2초 → 1.6초 → OFF ...

idle과 cover를 녹화할 때는 메트로놈을 끌 것 (부저 소리는 조도에 영향이 없지만
불필요하다).

--- NeoPixel 영향 ---

GP21 NeoPixel이 BH1750 옆에 있지만, 실측 결과 흰색 최대 밝기에서도 +1.35 lux로
1 LSB(1.86 lux) 미만이다. 이 스크립트는 밝기 24 이하만 쓰므로 영향은 0.4 lux 이하다.
"""

from machine import PWM, Pin
from neopixel import NeoPixel
from utime import sleep_ms, ticks_diff, ticks_ms

from bh1750_probe import SAMPLE_PERIOD_MS, make_sensor, use_best_config

BUTTON_PIN = 20
NEOPIXEL_PIN = 21
BUZZER_PIN = 22

# 메트로놈 간격 (ms). None = 꺼짐. 버튼을 누를 때마다 순환한다.
PACE_INTERVAL_MS = (None, 800, 1200, 1600)

BEEP_MS = 25
BEEP_FREQ = 2000
BEEP_DUTY = 20000

# NeoPixel 색상 — 조도 오염을 피하려고 전부 어둡게 유지한다 (밝기 <= 24)
COLOR_IDLE = (0, 0, 3)      # 스트리밍 중 (아주 흐린 파랑)
COLOR_BEAT = (0, 24, 0)     # 메트로놈 박자 (흐린 초록)
DEBOUNCE_MS = 200


class Metronome:
    """부저·LED로 동작 속도를 잡아준다. 샘플 주기를 막지 않도록 전부 비차단이다."""

    def __init__(self, buzzer, pixels):
        self._buzzer = buzzer
        self._pixels = pixels
        self._index = 0
        self._next_beat = ticks_ms()
        self._beep_until = None

    @property
    def interval(self):
        return PACE_INTERVAL_MS[self._index]

    def cycle(self):
        self._index = (self._index + 1) % len(PACE_INTERVAL_MS)
        self._next_beat = ticks_ms()
        self._silence()
        return self.interval

    def _silence(self):
        self._buzzer.duty_u16(0)
        self._beep_until = None
        self._pixels[0] = COLOR_IDLE
        self._pixels.write()

    def tick(self):
        now = ticks_ms()

        # 울리고 있던 비프를 시간이 되면 끈다
        if self._beep_until is not None and ticks_diff(now, self._beep_until) >= 0:
            self._silence()

        if self.interval is None:
            return

        if ticks_diff(now, self._next_beat) >= 0:
            self._next_beat = now + self.interval
            self._buzzer.freq(BEEP_FREQ)
            self._buzzer.duty_u16(BEEP_DUTY)
            self._beep_until = now + BEEP_MS
            self._pixels[0] = COLOR_BEAT
            self._pixels.write()


def main():
    sensor = make_sensor()
    use_best_config(sensor)

    button = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
    pixels = NeoPixel(Pin(NEOPIXEL_PIN), 1)
    buzzer = PWM(Pin(BUZZER_PIN))
    buzzer.duty_u16(0)

    metronome = Metronome(buzzer, pixels)
    pixels[0] = COLOR_IDLE
    pixels.write()

    # 포워더가 붙기 전에 안내를 흘려보내면 첫 줄이 깨질 수 있다. 잠깐 기다린다.
    sleep_ms(1500)

    last_press = ticks_ms()
    was_down = False
    next_sample = ticks_ms()

    while True:
        # --- 버튼: 메트로놈 간격 순환 (눌렀다 뗄 때 1회) ---
        is_down = button.value() == 0
        if is_down and not was_down and ticks_diff(ticks_ms(), last_press) > DEBOUNCE_MS:
            last_press = ticks_ms()
            metronome.cycle()
        was_down = is_down

        metronome.tick()

        # --- 샘플 1개 출력: data-forwarder가 읽는 유일한 줄 ---
        print("{:.2f}".format(sensor.measurement))

        next_sample += SAMPLE_PERIOD_MS
        delay = ticks_diff(next_sample, ticks_ms())
        if delay > 0:
            sleep_ms(delay)
        else:
            # 주기를 놓쳤다 — 밀린 시각을 현재로 되돌려 계속 밀리는 것을 막는다
            next_sample = ticks_ms()


main()
