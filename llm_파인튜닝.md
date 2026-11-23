# LLM 파인튜닝 핵심 정리

> 학습 단계 → 토큰·채팅 템플릿 → 평가 규칙 → 학습 데이터 만들기 → LoRA/PEFT → 학습 한 스텝(손실·학습률·에포크)

---

## 1. LLM 학습 단계

| 단계 | 약자 풀이 | 데이터 | 하는 일 | 얻는 능력 |
|---|---|---|---|---|
| 사전학습 | Pre-training | 대량의 텍스트 | 다음 토큰 예측 | 언어 능력, 지식 (베이스 모델) |
| SFT | Supervised Fine-Tuning | (지시, 모범 답변) 쌍 | 지도학습 | 지시를 따르는 대화 형식 |
| RLHF | Reinforcement Learning from Human Feedback | 사람의 선호 순위 | 보상 모델 + 강화학습(PPO) | 유용하고 안전한 응답 |
| DPO | Direct Preference Optimization | 선호/비선호 답변 쌍 | 보상 모델 없이 직접 최적화 | RLHF와 비슷한 효과를 더 간단히 |

- **사전학습 예시**: `대한민국의 수도는` → `서울`. 베이스 모델은 질문에 답하기보다 글을 이어 쓰려는 경향이 있습니다.
- **SFT 예시**: `{"instruction": "오늘 날씨가 좋다를 영어로", "output": "The weather is nice today."}`
- **DPO 예시**: `{"prompt": "피곤해", "chosen": "많이 지치셨군요. 잠깐 쉬어보는 건 어때요?", "rejected": "그렇군요."}`

> 비유: 사전학습은 도서관의 책을 모두 읽는 것, SFT는 모범 답안으로 답하는 법을 배우는 것, RLHF·DPO는 "이 답이 더 좋다"는 피드백으로 태도를 다듬는 것입니다.

---

## 2. 토큰과 채팅 템플릿

### 토큰
- 모델이 글을 읽고 쓰는 **단위 조각**입니다. 단어 하나가 토큰 여러 개로 나뉘기도 합니다.
- 모델이 한 번에 읽는 길이와 API 요금이 모두 **토큰 수**로 정해집니다.
- `<eos>`, `<|turn>` 같은 **특수 토큰**은 문장의 끝이나 역할 경계를 표시합니다.

### 역할
| 역할 | 의미 |
|---|---|
| system | 모델의 성격, 규칙, 말투 지정 |
| user | 사용자 입력 |
| assistant (Gemma는 `model`) | 모델의 응답 |

### 채팅 템플릿과 `apply_chat_template`
- 채팅 템플릿은 **누가 말하는 차례인지 표시해 둔 형식**입니다. 모델이 SFT 때 본 형식 그대로 넣어야 제대로 답합니다.
- 모델마다 형식이 다르므로 직접 외우지 않고 토크나이저의 `apply_chat_template`을 씁니다.

```python
messages = [
    {"role": "system", "content": "너는 친절한 선생님이야."},
    {"role": "user", "content": "광합성이 뭐야?"},
]
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,              # 문자열로 확인 (True면 토큰 ID)
    add_generation_prompt=True,  # 추론 시 필수: 이제 모델이 답할 차례임을 표시
)
```

---

## 3. 평가: 점수를 내기 전에 채점 규칙부터 정한다

- 규칙(루브릭)을 **먼저 고정**해야 일관되고, 재현 가능하고, 모델끼리 공정하게 비교할 수 있습니다.
- 루브릭 구성: **평가 기준 / 척도 / 점수별 정의 / 참고 답안 / 집계 방식**
- 채점 방식: 규칙 기반(정확 일치, 키워드), LLM-as-a-Judge(루브릭을 프롬프트에 넣음), 사람 평가

### 형식 준수와 정답을 따로 집계한다
실패 원인이 다르고, 고치는 방법도 다르기 때문입니다.

| 실패 | 원인 | 개선 |
|---|---|---|
| 형식 실패 | 지시 따르기 부족, 템플릿 불일치 | 프롬프트, 예시, SFT |
| 정답 실패 | 지식·추론 부족 | 모델, 데이터 보강 |

```python
import re

def check_format(output):
    m = re.search(r"정답:\s*(-?\d+)\s*$", output.strip())
    return m is not None, (m.group(1) if m else None)

def evaluate(samples):
    fmt_ok = correct = 0
    for s in samples:
        ok, pred = check_format(s["output"])
        fmt_ok += ok
        if ok and pred == s["answer"]:
            correct += 1
    n = len(samples)
    return {"형식 준수율": fmt_ok / n,
            "정답률(전체 기준)": correct / n,
            "정답률(형식 통과 기준)": correct / fmt_ok if fmt_ok else 0.0}
```

> 정답률을 보고할 때는 **분모가 전체인지 형식 통과분인지** 반드시 밝힙니다.

---

## 4. 학습 문장 만들기

**학습 데이터 = 채팅 형식으로 감싼 프롬프트 + 정답 + `<eos>`**

```text
제목: 주간회의 2026-06-02
유형:<turn|>
<|turn>model
회의록<eos>
```

- `<|turn>model`까지는 추론 때 넣는 입력과 **똑같습니다**. 그래서 학습한 형식이 추론에서도 재현됩니다.
- `<eos>`를 붙여야 모델이 답을 쓰고 **멈추는 법**을 배웁니다.
- `add_special_tokens=False`: 템플릿에 이미 시작 토큰이 있으므로 중복을 막습니다.

### 최대 길이 확인 (잘리면 정답이 사라짐)
```python
lengths = [len(tokenizer(build_text(r), add_special_tokens=False)['input_ids'])
           for r in train_rows]
MAX_LEN = 128
over = [i for i, n in enumerate(lengths) if n > MAX_LEN]
print(f'최소 {min(lengths)} / 평균 {sum(lengths)/len(lengths):.1f} / 최대 {max(lengths)}')
print(f'{MAX_LEN} 초과: {len(over)}건')
```
128을 넘는 문장은 뒷부분(정답과 `<eos>`)이 잘립니다. 줄여야 한다면 **프롬프트 쪽을 자릅니다.**

---

## 5. PEFT와 LoRA

### PEFT (Parameter-Efficient Fine-Tuning)
원래 모델은 얼려 두고 **일부만 학습**하는 방법입니다.

| 항목 | 전체 파인튜닝 | PEFT |
|---|---|---|
| 학습 파라미터 | 100% | 보통 1% 미만 |
| GPU 메모리 | 매우 큼 | 작음 |
| 저장물 | 모델 전체(GB 단위) | 어댑터만(MB 단위) |

- **LoRA**: 저랭크 행렬 B·A만 학습합니다.
- **QLoRA**: 고정된 원본 W를 4비트로 압축하고 LoRA를 학습합니다. 메모리가 가장 적게 듭니다.

### LoRA 동작 원리

```text
출력 = W·x + (alpha ÷ r) · B·A·x
       └ 원래 모델(고정)  └ 보정값 ΔW = B·A (학습)
```

| 기호 | 크기 | 의미 |
|---|---|---|
| W | d × d | 원래 가중치 (고정) |
| A | r × d | 입력을 r차원으로 압축 (학습, 작은 랜덤값으로 초기화) |
| B | d × r | 다시 d차원으로 복원 (학습, **0으로 초기화** → 처음에는 원래 모델과 동일) |
| r | 4~64 | 랭크 |
| alpha | 보통 r의 1~2배 | 보정값 세기. 실제 배율은 alpha/r |

- **파라미터 절약 예시** (d=4096, r=8): 전체는 약 1,677만 개, LoRA는 약 6.5만 개(0.4%)
- 학습이 끝나면 `merge_and_unload()`로 W에 합쳐서 추론 속도 손해가 없습니다.

### 랭크 r 이해하기
- r은 A와 B 사이의 **중간 차원(병목)** 입니다. 그래서 **rank(B·A) ≤ r**, 즉 r은 B·A 랭크의 **상한**입니다.
- 랭크 = 독립적인 변화 방향의 개수입니다. r이 클수록 더 복잡한 수정을 표현할 수 있습니다.
- r을 키우면 **전체 파인튜닝**에 가까워집니다. 원래 모델에 가까워지는 것이 **아닙니다**. 원래 모델에서 얼마나 멀어지는지는 학습량, 학습률, alpha가 정합니다.
- 작으면 덜 배우고(과소적합), 크면 무거워지고 외우기 쉽습니다(과적합). 단순 분류 작업은 4~8이면 보통 충분합니다.

### 설정 예시
```python
from peft import LoraConfig, get_peft_model

config = LoraConfig(
    r=8,
    lora_alpha=16,                          # 배율 16/8 = 2
    lora_dropout=0.05,
    target_modules=["q_proj", "v_proj"],    # 또는 "all-linear"
    task_type="CAUSAL_LM",
)
model = get_peft_model(model, config)
model.print_trainable_parameters()
```

- **target_modules**: LoRA를 붙일 Linear 층입니다.
  - 어텐션: `q_proj`, `k_proj`, `v_proj`, `o_proj` (단어 사이 관계)
  - MLP: `gate_proj`, `up_proj`, `down_proj` (지식, 변환)
  - 층이 많을수록 강력하지만 무겁습니다. `"all-linear"`가 최근 많이 쓰이며, `lm_head`는 제외합니다.
  - r은 한 층에서 고칠 수 있는 방향의 수, target_modules는 고칠 수 있는 위치를 정합니다.
- **lora_dropout**: 학습 중 LoRA 경로 입력의 일부를 무작위로 0으로 만들어 과적합을 막습니다. 추론 때는 꺼집니다. 0~0.1을 많이 씁니다.

---

## 6. 학습 한 스텝: 손실과 학습률의 역할

```text
① 문장 4건(배치) 입력 → 다음 토큰마다 확률 출력
② 손실 계산: 정답 토큰 확률이 낮을수록 손실이 큼
③ 기울기 계산: 손실이 줄어드는 방향
④ LoRA 행렬(A, B)만 학습률(2e-4)만큼 업데이트 → 다음 스텝
```

```python
outputs = model(**batch)   # ①
loss = outputs.loss        # ②
loss.backward()            # ③
optimizer.step()           # ④
optimizer.zero_grad()
```

### 세 개념

| | 손실 | 학습률 | 에포크 |
|---|---|---|---|
| 정의 | 답과 정답의 차이를 숫자 하나로 | 가중치를 한 번 고칠 때 움직이는 크기 | 데이터 전체를 한 번 학습하는 단위 |
| 쉬운 예 | 받아쓰기에서 틀린 글자 수 | 걸음 보폭. 너무 크면 목표를 지나침 | 문제집 한 권을 한 번 = 1 에포크 |
| 볼 것 | 꾸준히 감소하는가 | 손실이 출렁이면 너무 큰 것 | 평가셋 정확도가 오르는가 |

### 손실 = -log(정답 확률)

| 정답 확률 | 손실 |
|---|---|
| 0.9 | 0.11 |
| 0.5 | 0.69 |
| 0.2 | 1.61 |
| 0.01 | 4.61 |

```python
import torch, torch.nn.functional as F
logits = torch.tensor([[2.0, 1.0, 0.1]])
target = torch.tensor([0])
print(F.cross_entropy(logits, target))   # 0.417 = -log(0.659)
```

**실습 예시 해석**: 손실이 에포크 1의 2.47(정답 확률 약 8%)에서 에포크 3의 0.3대(약 74%)로 내려갔습니다.

### 스텝과 에포크
```text
1 에포크 스텝 수 = 데이터 수 ÷ 배치 크기
예) 3 에포크 = 108스텝 → 1 에포크 = 36스텝 → 배치 4면 약 144건
```

### 학습률과 에포크 비교 (미션)
| 바꾼 값 | 예상 |
|---|---|
| lr 5e-5 | 손실이 천천히 줄어듦 |
| lr 2e-4 | 기준. 부드럽게 감소 |
| lr 1e-3 | 빠르게 줄다가 출렁이거나 다시 오를 수 있음 |
| epoch 1 | 덜 배움 |
| epoch 5 | 학습 손실은 더 낮아지지만 평가셋 정확도가 떨어질 수 있음(과적합) |

> 비교할 때는 **한 가지만 바꾸고 나머지는 고정**합니다.

### 결과 읽는 법
- 손실 ↓, 평가셋 정확도 ↑ → 잘 배우는 중
- 손실 ↓, 평가셋 정확도 정체 또는 하락 → 외우는 중. 에포크나 학습률을 줄입니다.
- 손실이 출렁임 → 학습률이 너무 큽니다.
- **학습 손실은 학습 데이터 기준**입니다. 실제 성능은 평가셋으로, 형식과 정답을 따로 집계해 확인합니다.
