# Phase 2 — Impulse 설계·학습

> 상태: **부트스트랩 학습 대기** — 조명 1세트만으로 파이프라인을 먼저 통과시킨다

EI 프로젝트: `datapi light sensor` (ID `1079757`)

## 왜 데이터를 다 모으기 전에 학습하는가

*AI at the Edge* Ch.9 "Bootstrapping" — **최소 데이터로 파이프라인을 끝까지 한 번
통과시켜 근본 질문에 답을 받고 나서 투자하라.**

이 프로젝트의 근본 질문은 하나다: **`wave`와 `swipe`가 갈리는가.**

Phase 0부터 이 질문을 계속 추정만 해왔고, 그때마다 답이 바뀌었다.

| 시점 | 근거 | 판단 |
|---|---|---|
| Phase 0 (5초 측정) | 진폭 차이 2~7% | 주파수만이 유일한 근거, 위험 |
| 1차 수집 (10초 세션) | 주파수 3.5~4배 + 깊이 차이 | 넉넉히 갈림 |
| 2차 수집 (60초 세션) | 주파수 2배, 깊이 범위 겹침 | 다시 위험 |

**세 번 추정해서 세 번 다른 답이 나왔다.** 짧은 샘플과 한쪽 세션만 보고 판단한 탓이다.
이제 Studio에게 직접 물어본다. 혼동행렬이 답이다.

조명 4세트(16분)를 다 모은 뒤에 "안 갈린다"를 알게 되면 그 데이터가 전부 낭비다.

## 현재 데이터셋

| | 클래스 | 길이 | 조명 | 샘플 수 |
|---|---|---|---|---|
| Training | idle / cover / wave / swipe | 60초 | 배경 ~145 lux | 960 각 |
| Testing | idle / cover / wave / swipe | 30초 | **배경 ~90 lux** | 480 각 |

Test는 **다른 조명 조건**이다. 세션 단위로 완전히 분리되어 있으므로
"다른 환경에서도 되는가"를 실제로 측정한다 (Ch.7 — Splitting Your Data).

### 두 세션의 신호 특성

| | Training (145 lux) | Testing (90 lux) |
|---|---|---|
| `idle` | 140~150 | 87~91 |
| `cover` | 5.5~7.5 | 0~3.7 |
| `wave` | 70~140, ~1.2 Hz | 20~95, ~1.2 Hz |
| `swipe` | 75~150, ~0.6 Hz | 20~90, ~0.7 Hz |

**진폭 범위가 조명에 따라 크게 달라진다.** 모델이 절대 lux 값에 의존하면 test에서
무너진다. 이것도 이번 학습이 답할 질문이다.

`wave`와 `swipe`를 가르는 것은 이제 두 가지뿐이다:

- **주파수** — 약 2배 (1.2 Hz vs 0.6~0.7 Hz)
- **파형 모양** — `swipe`는 평평한 바탕에 좁은 스파이크가 띄엄띄엄,
  `wave`는 바탕이랄 게 없는 연속 진동

두 번째가 더 강한 신호다. 좁은 펄스는 스펙트럼에 고조파를 퍼뜨리고,
연속 진동은 기본 주파수에 에너지가 몰린다.

---

## Impulse 설정

### Create impulse

| 항목 | 값 |
|---|---|
| Window size | **2000 ms** |
| Window increase (stride) | **500 ms** |
| Frequency | **16 Hz** |
| Zero-pad data | 켜기 |

창당 32 샘플. **주파수 해상도는 1/2초 = 0.5 Hz**다.
`wave`(1.2 Hz)와 `swipe`(0.7 Hz)의 차이가 0.5 Hz — 정확히 1 bin이다. 빠듯하다.

그래도 2000 ms로 시작하는 이유: 신경망은 피크 위치만 보는 게 아니라 **스펙트럼 전체
모양**(고조파 분포)을 본다. 좁은 펄스와 연속 진동은 이 모양이 다르다.
안 되면 3000 ms로 늘린다 (해상도 0.33 Hz). 지연을 늘리기 전에 되는지부터 본다.

### Processing block: Spectral Analysis

| 항목 | 값 | 이유 |
|---|---|---|
| Scaling | 1 | |
| Input decimation ratio | 1 | 16 Hz도 이미 낮다 |
| Filter type | **none** 또는 low-pass 5 Hz | 잡음이 1 LSB뿐이라 필터 실익이 없다 |
| Analysis type | FFT | |
| FFT length | **32** | 창 샘플 수와 동일 |
| Take log of spectrum | 켜기 | 진폭 차이를 압축 → 조명 변화에 덜 민감 |
| Overlap FFT frames | 켜기 | |

**`Take log of spectrum`이 중요하다.** train과 test의 진폭 범위가 2배 가까이 다르므로,
선형 스펙트럼을 그대로 쓰면 모델이 절대 크기에 붙는다. 로그를 취하면 배율 차이가
덧셈 오프셋이 되어 훨씬 견딘다.

### Learning block: Classification

- 기본 제안 구조(Dense 20 → Dense 10)로 먼저 돌린다
- Training cycles 100, Learning rate 0.0005
- **Data augmentation 끄기** — 1축 시계열에는 적절한 증강이 없다

RP2040 예산 (`RESEARCH.md` §3):

| 항목 | 목표 |
|---|---|
| RAM | < 100 KB |
| Flash | < 500 KB |
| Latency | < 100 ms |

이 규모 문제에서는 여유가 많을 것이다. 문제는 크기가 아니라 분리 가능성이다.

---

## 1차 학습 결과 (작성 대기)

### Feature explorer

Spectral Analysis 탭의 Feature explorer에서 **학습 전에** 클래스 분포를 먼저 본다.
`wave`와 `swipe` 군집이 겹쳐 보이면 학습해도 안 갈린다 — 바로 창 길이를 늘린다.

- [ ] `cover`가 확실히 떨어져 있는가
- [ ] `idle`이 확실히 떨어져 있는가
- [ ] **`wave`와 `swipe`가 갈리는가**

### 혼동행렬 (Training)

| 실제 \ 예측 | idle | cover | wave | swipe |
|---|---|---|---|---|
| idle | | | | |
| cover | | | | |
| wave | | | | |
| swipe | | | | |

### 혼동행렬 (Model testing — 다른 조명)

| 실제 \ 예측 | idle | cover | wave | swipe |
|---|---|---|---|---|
| idle | | | | |
| cover | | | | |
| wave | | | | |
| swipe | | | | |

**Training과 Testing의 격차가 핵심 지표다.** 격차가 크면 모델이 조명 조건에
의존하고 있다는 뜻이고, 조명 조건을 더 모아야 한다.

### On-device 성능 추정

| 항목 | 실측 | 목표 |
|---|---|---|
| RAM | | < 100 KB |
| Flash | | < 500 KB |
| Latency | | < 100 ms |

---

## 판단 규칙

평가 관점은 Ch.10 — 전체 정확도 하나로 보지 않는다.

- **클래스별 recall** — 어떤 제스처를 놓치는가
- **`idle` → 제스처 오검출** — 실사용에서 가장 거슬리는 실패 모드
- `wave` / `swipe` 혼동 — 이 프로젝트의 핵심 질문

### `wave`/`swipe`가 혼동될 때 조치 순서

1. **창 2000 → 3000 ms** (주파수 해상도 0.5 → 0.33 Hz, 지연 감수)
2. **Raw Data + 1D Conv 시도** — 판별 특징이 미세한 주파수가 아니라 **펄스 모양**이라면,
   거친 FFT bin보다 CNN이 시간축 모양을 직접 배우는 편이 나을 수 있다.
   (계획에 적었던 Raw + Flatten과는 다르다. Flatten은 창 단위 요약통계라 반드시 실패한다)
3. **3-class로 축소** — `swipe`를 뺀다

### 조명 일반화가 안 될 때

Training은 좋은데 Testing이 나쁘면 조명 조건을 더 모은다
(주광 / 스탠드 / 어두움). 이때가 나머지 12분을 쓸 때다.
