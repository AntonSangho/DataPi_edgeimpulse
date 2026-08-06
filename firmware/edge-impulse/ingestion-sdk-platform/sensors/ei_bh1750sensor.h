/* BH1750 조도 센서 - Edge Impulse fusion 등록
 *
 * 본보기는 upstream의 ei_analogsensor.{h,cpp} (단일 축이라 구조가 같다).
 *
 * ⚠️ 축 이름 "lux"는 Studio의 축 이름과 정확히 같아야 한다.
 * Phase 1에서 축 이름 때문에 세 번 재녹화했다 (docs/01-data-collection.md).
 * 한 글자라도 다르면 조용히 실패한다 — 에러가 아니라 데이터가 안 붙는다.
 */

#ifndef EI_BH1750SENSOR_H
#define EI_BH1750SENSOR_H

#include "ei_fusion.h"
#include "ei_sampler.h"

/** 축 1개 (lux) */
#define BH1750_AXIS_SAMPLED 1

bool ei_bh1750_sensor_init(void);
float *ei_fusion_bh1750_sensor_read_data(int n_samples);

static const ei_device_fusion_sensor_t bh1750_sensor = {
    // Studio의 fusion 목록에 표시될 이름
    "Light sensor",
    // 축 개수
    BH1750_AXIS_SAMPLED,
    // 샘플링 주파수 목록.
    //
    // 16.0f가 이 프로젝트의 확정값이다 (62500 us = 정확히 16 Hz).
    // 데이터셋 전체가 이 주파수로 수집됐으므로 바꾸면 스펙트럼이 밀린다.
    // 나머지는 다른 실험을 위해 남겨 둔 값이고, 지금 쓰면 모델과 어긋난다.
    { 16.0f, 12.5f, 10.0f, 8.0f, 1.0f },
    // 축 이름과 단위 (읽는 순서와 같아야 한다)
    {
        { "lux", "lx" },
    },
    // 읽기 함수
    &ei_fusion_bh1750_sensor_read_data
};

#endif /* EI_BH1750SENSOR_H */
