/* BH1750 조도 센서 - Edge Impulse fusion 등록 */

#include "ei_bh1750sensor.h"
#include "BH1750.h"
#include "ei_device_raspberry_rp2xxx.h"
#include "firmware-sdk/sensor-aq/sensor_aq.h"
/* upstream의 다른 센서 파일들은 ei_printf를 쓰지 않아 전이 include에 기대고 있다.
 * 여기서는 명시한다. */
#include "edge-impulse-sdk/porting/ei_classifier_porting.h"

static float bh1750_data[BH1750_AXIS_SAMPLED];

bool ei_bh1750_sensor_init(void)
{
    if (!bh1750_light.init()) {
        ei_printf("ERR: BH1750(0x23)을 찾지 못했습니다. GP4=SDA / GP5=SCL 배선 확인\n");
        return false;
    }

    if (!bh1750_light.use_best_config()) {
        ei_printf("ERR: BH1750 설정 실패 (연속 H-Resolution, MTreg 31)\n");
        return false;
    }

    ei_add_sensor_to_fusion_list(bh1750_sensor);

    return true;
}

float *ei_fusion_bh1750_sensor_read_data(int n_samples)
{
    /* 읽기에 실패하면 직전 값을 그대로 내보낸다.
     *
     * Phase 1에서 배운 것이다: 예외로 스트림이 끊기면 Studio는 60초를 요청하고
     * 25초만 받고도 "OK"로 업로드한다 (wave 401/960 샘플, swipe 0샘플 2회).
     * 조용히 잘린 데이터가 잘못된 값 하나보다 훨씬 해롭다.
     * src/ei_forwarder.py의 같은 판단 참고. */
    float lux;
    if (bh1750_light.read_lux(lux)) {
        bh1750_data[0] = lux;
    }

    return bh1750_data;
}
