"""Phase 1 - Edge Impulse data-forwarder용 조도 스트리머

BH1750의 lux 값을 정확히 16 Hz(62.5 ms)로 USB CDC에 한 줄씩 출력한다.
edge-impulse-data-forwarder가 이 줄을 읽어 Studio로 올린다.

주기가 62.5 ms인 이유는 bh1750_probe.py의 SAMPLE_PERIOD_US 주석 참고 —
Studio가 기록하는 간격과 장치의 실제 간격을 일치시켜야 한다.

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

그래서 클래스마다 **긴 연속 세션**을 녹화한다 (60초). 녹화 전체가 한 라벨이므로
시작 정렬이 필요 없고, 창 분할은 EI가 알아서 한다.

--- 페이스 메트로놈을 넣었다가 뺀 이유 ---

wave와 swipe가 빈도로만 갈릴까 봐 부저로 박자를 잡아주는 기능을 넣었었다.
1차 수집 실측 결과 불필요했다.

  자연스럽게 한 wave ~1.9 Hz  vs  swipe ~0.5 Hz  →  3.5~4배 차이
  게다가 골 깊이도 다르다 (wave 30~70 lux, swipe 5~20 lux)

오히려 해로울 수 있다. 0.8초 박자에 맞춰 찍은 데이터로 학습하면 모델이 그 경직된
박자를 배우는데, 실사용에서 사람은 메트로놈 없이 제스처를 한다. 학습 데이터가
배포 조건과 어긋난다 ("AI at the Edge" Ch.7 - representative dataset).

또 녹화 중 버튼을 실수로 누르면 부저·LED가 켜져 세션을 오염시킬 수 있었다.
자연스러운 제스처를 그대로 찍는 것이 더 나은 데이터다. 그래서 들어냈다.

--- NeoPixel ---

GP21 NeoPixel이 BH1750 옆에 있지만, 실측 결과 흰색 최대 밝기에서도 +1.35 lux로
1 LSB(1.86 lux) 미만이다. 여기서는 밝기 3만 쓰므로 영향은 측정 한계 아래다.
스크립트가 돌고 있다는 것만 알려주는 용도.
"""

from machine import Pin
from neopixel import NeoPixel
from utime import sleep_ms, sleep_us, ticks_diff, ticks_us

from bh1750_probe import SAMPLE_PERIOD_US, make_sensor, use_best_config

NEOPIXEL_PIN = 21
COLOR_RUNNING = (0, 0, 3)   # 아주 흐린 파랑 — 조도에 영향 없는 밝기


def main():
    sensor = make_sensor()
    use_best_config(sensor)

    pixels = NeoPixel(Pin(NEOPIXEL_PIN), 1)
    pixels[0] = COLOR_RUNNING
    pixels.write()

    # 포워더가 붙기 전에 안내를 흘려보내면 첫 줄이 깨질 수 있다. 잠깐 기다린다.
    sleep_ms(1500)

    next_sample = ticks_us()
    while True:
        # data-forwarder가 읽는 유일한 줄
        print("{:.2f}".format(sensor.measurement))

        next_sample += SAMPLE_PERIOD_US
        delay = ticks_diff(next_sample, ticks_us())
        if delay > 0:
            sleep_us(delay)
        else:
            # 주기를 놓쳤다 — 밀린 시각을 현재로 되돌려 계속 밀리는 것을 막는다
            next_sample = ticks_us()


main()
