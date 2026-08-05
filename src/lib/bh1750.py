# https://github.com/flrrth/pico-bh1750
#
# DataPi_edgeimpulse용 vendored 사본.
# 원본 대비 수정 사항 (2건, 상세는 docs/00-sensor-characterization.md):
#
#   1. 해상도 판별 오류 — _write_measurement_mode() / measurements()가
#      self._measurement_time(31~254)을 RESOLUTION_LOW(2) 상수와 비교하고 있었다.
#      항상 거짓이므로 저해상도 모드에서도 120~180 ms를 대기했다.
#      → self._resolution과 비교하도록 수정.
#
#   2. MTreg lux 환산 방향이 반대 — (69 / mt)로 나누고 있었다.
#      MTreg를 줄이면 감도가 낮아져 같은 밝기에서 raw가 작아지므로 (mt / 69)여야 한다.
#      mt=69(기본값)에서는 두 식이 일치해 기본 설정으로만 쓰면 드러나지 않는다.
#      → 실측으로 확인: 배경 130 lx에서 mt=31 raw=70,
#        원본 식 26.3 lx / 수정 식 129.9 lx (mt=69 측정치 130.0 lx와 일치).

import math

from micropython import const
from utime import sleep_ms


class BH1750:
    """Class for the BH1750 digital Ambient Light Sensor

    The datasheet can be found at https://components101.com/sites/default/files/component_datasheet/BH1750.pdf
    """

    MEASUREMENT_MODE_CONTINUOUSLY = const(1)
    MEASUREMENT_MODE_ONE_TIME = const(2)

    RESOLUTION_HIGH = const(0)
    RESOLUTION_HIGH_2 = const(1)
    RESOLUTION_LOW = const(2)

    MEASUREMENT_TIME_DEFAULT = const(69)
    MEASUREMENT_TIME_MIN = const(31)
    MEASUREMENT_TIME_MAX = const(254)

    def __init__(self, address, i2c):
        self._address = address
        self._i2c = i2c
        self._measurement_mode = BH1750.MEASUREMENT_MODE_ONE_TIME
        self._resolution = BH1750.RESOLUTION_HIGH
        self._measurement_time = BH1750.MEASUREMENT_TIME_DEFAULT

        self._write_measurement_time()
        self._write_measurement_mode()

    def configure(self, measurement_mode: int, resolution: int, measurement_time: int):
        """Configures the BH1750.

        Keyword arguments:
        measurement_mode -- measure either continuously or once
        resolution -- return measurements in either high, high2 or low resolution
        measurement_time -- the duration of a single measurement
        """
        if measurement_time not in range(BH1750.MEASUREMENT_TIME_MIN, BH1750.MEASUREMENT_TIME_MAX + 1):
            raise ValueError("measurement_time must be between {0} and {1}"
                             .format(BH1750.MEASUREMENT_TIME_MIN, BH1750.MEASUREMENT_TIME_MAX))

        self._measurement_mode = measurement_mode
        self._resolution = resolution
        self._measurement_time = measurement_time

        self._write_measurement_time()
        self._write_measurement_mode()

    def _write_measurement_time(self):
        buffer = bytearray(1)

        high_bit = 1 << 6 | self._measurement_time >> 5
        low_bit = 3 << 5 | (self._measurement_time << 3) >> 3

        buffer[0] = high_bit
        self._i2c.writeto(self._address, buffer)

        buffer[0] = low_bit
        self._i2c.writeto(self._address, buffer)

    def _write_measurement_mode(self):
        buffer = bytearray(1)

        buffer[0] = self._measurement_mode << 4 | self._resolution
        self._i2c.writeto(self._address, buffer)
        # FIX: 원본은 self._measurement_time과 비교했다.
        sleep_ms(24 if self._resolution == BH1750.RESOLUTION_LOW else 180)

    def reset(self):
        """Clear the illuminance data register."""
        self._i2c.writeto(self._address, bytearray(b'\x07'))

    def power_on(self):
        """Powers on the BH1750."""
        self._i2c.writeto(self._address, bytearray(b'\x01'))

    def power_off(self):
        """Powers off the BH1750."""
        self._i2c.writeto(self._address, bytearray(b'\x00'))

    @property
    def measurement(self) -> float:
        """Returns the latest measurement."""
        if self._measurement_mode == BH1750.MEASUREMENT_MODE_ONE_TIME:
            self._write_measurement_mode()

        buffer = bytearray(2)
        self._i2c.readfrom_into(self._address, buffer)
        # FIX: 원본은 (69 / mt)로 나눴다. MTreg를 줄이면 감도가 낮아져 같은 밝기에서
        # raw 카운트가 작아지므로 (mt / 69)로 나눠야 한다. mt=69에서는 두 식이 같아
        # 기본 설정으로만 쓰면 드러나지 않는다.
        # 실측(배경 130 lx): mt=31 raw=70 → 70/1.2*(69/31) = 129.9 lx  (원본 식은 26.3 lx)
        lux = (buffer[0] << 8 | buffer[1]) / (1.2 * (self._measurement_time / BH1750.MEASUREMENT_TIME_DEFAULT))

        if self._resolution == BH1750.RESOLUTION_HIGH_2:
            return lux / 2
        else:
            return lux

    def measurements(self) -> float:
        """This is a generator function that continues to provide the latest measurement. Because the measurement time
        is greatly affected by resolution and the configured measurement time, this function attemts to calculate the
        appropriate sleep time between measurements.

        Example usage:

        for measurement in bh1750.measurements():  # bh1750 is an instance of this class
            print(measurement)
        """
        while True:
            yield self.measurement

            if self._measurement_mode == BH1750.MEASUREMENT_MODE_CONTINUOUSLY:
                # FIX: 원본은 self._measurement_time과 비교했다.
                base_measurement_time = 16 if self._resolution == BH1750.RESOLUTION_LOW else 120
                sleep_ms(math.ceil(base_measurement_time * self._measurement_time / BH1750.MEASUREMENT_TIME_DEFAULT))
