#!/usr/bin/env python3
"""UF2 -> raw bin 변환. openocd로 SWD 굽기를 하려면 .bin이 필요하다.

왜 필요한가: MicroPython은 .uf2로만 배포되고 openocd는 .uf2를 못 굽는다.
`picotool uf2 convert`는 출력이 UF2로 고정되어 있어서(ERROR: Output must be
a UF2 file) 쓸 수 없다. BOOTSEL 드래그로도 되지만, Probe가 붙어 있으면
버튼을 누르러 갈 이유가 없다.

연속된 플래시 이미지를 가정하고, 블록 사이에 틈이 있으면 소거값(0xff)으로
채운다. 시작 주소를 출력하므로 그대로 openocd에 넘기면 된다.

    python3 tools/uf2conv.py in.uf2 out.bin
    # base=0x10000000 size=874752 (854.2 KB)

    openocd -f interface/cmsis-dap.cfg -f target/rp2040.cfg \
      -c "adapter speed 5000" \
      -c "program out.bin 0x10000000 verify reset exit"
"""
import struct
import sys

MAGIC0, MAGIC1, MAGIC_END = 0x0A324655, 0x9E5D5157, 0x0AB16F30
FLAG_NOT_MAIN_FLASH = 0x00000001


def convert(src, dst):
    data = open(src, 'rb').read()
    assert len(data) % 512 == 0, "UF2는 512바이트 블록이어야 한다"

    base, out, prev = None, bytearray(), None
    for i in range(0, len(data), 512):
        b = data[i:i + 512]
        m0, m1, flags, addr, size, _blkno, _nblk, _fam = struct.unpack('<8I', b[:32])
        assert (m0, m1) == (MAGIC0, MAGIC1), f"블록 {i // 512} 매직 불일치"
        assert struct.unpack('<I', b[-4:])[0] == MAGIC_END, f"블록 {i // 512} 끝 매직 불일치"

        if flags & FLAG_NOT_MAIN_FLASH:
            continue

        if base is None:
            base = addr
        elif addr != prev:
            gap = addr - prev
            assert gap > 0, f"주소가 역행한다: {hex(prev)} -> {hex(addr)}"
            out.extend(b'\xff' * gap)

        out.extend(b[32:32 + size])
        prev = addr + size

    open(dst, 'wb').write(out)
    return base, len(out)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    base, n = convert(sys.argv[1], sys.argv[2])
    print(f"base=0x{base:08x} size={n} ({n / 1024:.1f} KB)")
