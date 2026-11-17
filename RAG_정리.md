# RAG 학습 정리

> 복습용 노트. 개념 → 파이프라인 → 청킹/토큰 → 임베딩 → 다국어 → 사내 문서 순서.

---

## 1. RAG란?

**Retrieval-Augmented Generation** — LLM이 답하기 전에 관련 문서를 **검색**해서 프롬프트에 넣고, 그 근거로 **생성**하는 방식.

| LLM 단독의 한계 | RAG로 해결 |
|---|---|
| 학습 이후의 최신 정보를 모름 | 최신 문서를 검색해서 넣음 |
| 사내 데이터를 모름 | 사내 문서를 검색 대상으로 사용 |
| 환각 | "이 문서 안에서만 답해" + 출처 표시 |
| 파인튜닝은 비싸고 느림 | 문서만 교체하면 바로 반영 |

---

## 2. 전체 파이프라인

### ① 인덱싱 (오프라인, 미리)
```
문서(PDF, 위키, DB)
 → 로딩/파싱   : 텍스트 추출 품질 확인 + 메타데이터 수집 (출처, 날짜, 권한)
 → 청킹        : 임베딩 모델의 토크나이저로 크기 측정, 문장·구조 경계에서 자르기, 오버랩
 → 임베딩      : 모델 규칙(query:/passage: 등) 적용
 → 벡터DB 저장 : 벡터 + 원문 + 메타데이터 함께 저장 (+ 선택: BM25 인덱스)
```
**임베딩 모델을 먼저 고르고, 그 모델에 맞춰 청킹한다.** 모델을 바꾸면 청킹부터 다시 해야 한다.

### ② 질의 (온라인, 질문마다)
```
질문 → (쿼리 재작성) → 같은 모델로 임베딩 → 검색 Top-K → 리랭킹 → 프롬프트에 삽입 → LLM 답변 + 출처
```

### 최소 코드
```python
import numpy as np
from sentence_transformers import SentenceTransformer

embedder = SentenceTransformer("BAAI/bge-m3")
vectors = embedder.encode(chunks, normalize_embeddings=True)

def retrieve(query, k=3):
    q = embedder.encode([query], normalize_embeddings=True)[0]
    top = np.argsort(vectors @ q)[::-1][:k]          # 코사인 유사도
    return [chunks[i] for i in top]

prompt = f"""아래 문서만 근거로 답하고, 없으면 "모르겠습니다"라고 답하세요. 출처 번호를 표시하세요.
<문서>
{context}
</문서>
질문: {query}"""
```

---

## 3. 임베딩 모델 접두어 (`query:` / `passage:`)

- **모델이 학습할 때 쓴 입력 형식을 맞춰 주는 것**이다. 성능을 올리는 마법의 문자열이 아니다.
- 질문(짧은 의문문)과 문서(긴 서술문)를 구분하는 **비대칭 검색**용이다.

| 모델 | 질문 | 문서 |
|---|---|---|
| E5 계열 | `query: ` 필수 | `passage: ` 필수 |
| BGE v1.5 | instruction 권장 | 없음 |
| BGE-M3, OpenAI | 없음 | 없음 |

**효과가 없거나 나빠지는 경우**
- 접두어 없이 학습한 모델에 붙이는 경우 → 노이즈
- 질문↔질문 비교, 클러스터링 같은 대칭 작업 → E5도 양쪽 `query:`
- 인덱싱과 검색의 규칙이 다른 경우 → 최악
- 접두어 없이 파인튜닝한 모델

**원칙:** 모델 카드를 따른다 → 확신이 없으면 평가셋으로 비교 → 일관되게 적용한다.

---

## 4. 청킹

### 단위
| 방식 | 특징 |
|---|---|
| 글자 수 | 간단하지만 문장이 잘림 |
| **토큰 수** | 모델 한도에 정확히 맞음 → **크기 측정용** |
| 문장/문단 | 문장이 깨지지 않음 → **자르는 위치용** |
| 문서 구조 | 제목, 조항, 슬라이드, 시트 → 의미 덩어리 유지 |
| 의미 기반 | 주제가 바뀌는 지점에서 자름. 비용이 큼 |

**정석: 크기는 토큰으로 재고, 자르는 위치는 문장·구조 경계로 정한다.** 형태소 개수로 자르는 경우는 거의 없다.

```python
from transformers import AutoTokenizer
from langchain_text_splitters import RecursiveCharacterTextSplitter

tok = AutoTokenizer.from_pretrained("BAAI/bge-m3")   # 임베딩 모델과 같은 토크나이저
splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
    tok, chunk_size=400, chunk_overlap=60,
    separators=["\n\n", "\n", "다. ", "요. ", ". ", "? ", "! ", " ", ""],
)
```

### 크기 기준
- 상한: 임베딩 모델 `max_seq_length`보다 여유 있게 잡는다 (헤더와 접두어도 토큰을 차지함).
- 시작값: **200~600토큰**. 한도가 8192라도 크게 넣으면 주제가 섞여서 검색이 나빠진다.
- 문서 성격: FAQ/조항은 작게, 기술 문서는 중간, 서사형 글은 크게.
- 최종 결정은 평가(Recall@K)로 한다.

### 오버랩
- **경험적인 값**이다. 경계에 걸친 문장을 살리려는 목적이다.
- 10~20% ≈ **문장 1~2개 분량**. 너무 크면 비용이 늘고 Top-K가 중복으로 찬다.
- 구조 기반 청킹이나 독립 항목(FAQ)이면 0~10%.
- 대안: 맥락 헤더, 검색된 청크의 앞뒤 청크 함께 가져오기 (window/parent retrieval).

---

## 5. 토큰과 토크나이저

- 토큰 = 서브워드 조각. 모델마다 토크나이저가 다르다 (BPE, WordPiece, SentencePiece).
- 한국어는 토크나이저에 따라 토큰 수 차이가 크다 (다국어 모델은 한 글자당 0.5~1토큰, 영어 중심 모델은 2~3토큰).
- **청크 크기는 임베딩 모델의 토크나이저로 잰다.** 한도를 넘으면 뒷부분이 경고 없이 잘린다.
- LLM 토크나이저는 "Top-K를 합친 길이가 컨텍스트에 들어가는가"만 대략 확인하면 된다.

---

## 6. 차원 vs 최대 토큰 수 (별개!)

| | 차원 (dimension) | 최대 토큰 수 |
|---|---|---|
| 뜻 | 출력 벡터의 길이 | 한 번에 읽는 입력 길이 |
| 영향 | 벡터DB 설정, 저장 공간, 속도 | 청크 크기의 상한 |
| 예: multilingual-e5-large | 1024 | 512 |
| 예: BGE-M3 | 1024 | 8192 |

- `encode()` 결과 `(n, d)`: n = 청크 개수, d = 차원.
- 내부 동작: 토큰별 벡터 `(토큰수 × d)` → **풀링** → `(d,)`. 길이와 상관없이 항상 d개의 숫자.
- 비유: 최대 토큰 = 읽을 수 있는 페이지 수, 차원 = 요약 메모 칸 수.
- 메모 칸이 고정이라 **청크가 길수록 내용이 뭉뚱그려진다** → 적당히 작게 자른다.

```python
m.get_sentence_embedding_dimension()  # 차원
m.max_seq_length                      # 최대 토큰
```

---

## 7. 한국어 / 영어 혼합

| 단계 | 할 일 |
|---|---|
| 임베딩 | **다국어 모델** 사용 (BGE-M3, multilingual-e5) → 교차 언어 검색 가능 |
| 청킹 | 두 언어의 문장 끝을 구분자에 모두 넣기, **토큰 기준** 크기 (글자 수 기준이면 2~3배 차이), 코드와 표는 통째로 |
| BM25 | 형태소 분석(Kiwi, Mecab) + 영어 소문자화. 교차 언어 검색은 불가 → **하이브리드 검색** |
| 병기 문서 | 한 언어만 인덱싱하거나 `lang` 메타데이터로 중복 제거 |
| 리랭커/LLM | 다국어 리랭커 사용, 프롬프트에서 출력 언어 지정 |

**역할 분담:** 청킹은 어디서 자를지, 임베딩 모델은 언어 이해, 형태소 분석은 BM25.

**하지 말 것:** 영어 전용 모델 사용, 번역본만 인덱싱(원문 유지 필수), 한국어 질문만으로 평가셋 구성.

---

## 8. 사내 문서 (md, docx, pdf, pptx, xlsx, csv)

**원칙: 파싱은 형식별로 → 공통 형식(Markdown + 메타데이터) → 임베딩 모델 1개 + 벡터DB 1개.**

| 형식 | 파서 | 청킹 단위 | 주의 |
|---|---|---|---|
| md | 그대로 | `#` 섹션 | 코드 블록 유지 |
| docx | python-docx, docling, markitdown | Heading 기준 섹션 | 표 → Markdown 표 |
| pdf | PyMuPDF, docling, Upstage, OCR | 페이지/섹션 + 토큰 | **가장 어려움.** 결과를 직접 확인 |
| pptx | python-pptx, markitdown | **슬라이드 1장 = 청크 1개** (+ 발표자 노트) | 덱/슬라이드 제목을 헤더로. 도표는 비전 LLM 설명 |
| xlsx/csv | pandas, openpyxl | 아래 참고 | 헤더, 병합 셀 |

### 표 데이터는 질문 유형에 따라
- **조회형** ("A100 보증 기간?") → 행을 `컬럼: 값 | ...` 문장으로 변환, 5~20행씩 묶고 헤더 반복.
- **집계형** ("3분기 매출 합계?") → 벡터 검색으로는 불가 → DB + **Text-to-SQL**. 질문을 분류하는 **라우터**를 둔다.
- **문서형 시트** → Markdown 표로 변환해서 일반 문서처럼 처리.

### 메타데이터 스키마 통일
```python
{"doc_id", "source", "file_type", "title", "section", "page",
 "updated_at", "department", "access", "url"}
```
→ 출처 표시, 권한 필터, 최신 우선, 형식 필터에 활용.

### 맥락 헤더
```
문서: 2026 영업전략 (pptx) > 슬라이드 7: 3분기 목표
---
본문...
```

### 자주 놓치는 것
파싱 결과 검수, 중복 및 버전 파일 정리, 증분 업데이트(해시/수정일), **권한 설계**.

---

## 9. 메타데이터 크기 걱정?

- **필터용 메타데이터(JSON)** → 벡터 옆에 별도 저장. 임베딩 입력이 아니므로 토큰과 무관하다.
  - 청크 1개 기준 크기: 벡터 약 4KB > 원문 약 1~2KB > 메타데이터 약 0.2~0.5KB
- **맥락 헤더** → 임베딩에 포함. 20~50토큰(5~10%) 정도로 짧게, 의미 있는 정보만 넣는다.
- **조심할 경우**
  - 청크가 아주 작으면(엑셀 1행) 헤더가 벡터를 지배한다 → 행을 묶거나 헤더를 줄인다.
  - LLM에는 출처 표시에 필요한 정보만 넘긴다.
  - 헤더와 접두어를 포함한 최종 길이가 모델 한도 이하인지 확인한다.

---

## 10. 실무 개선 체크리스트

- [ ] 하이브리드 검색 (벡터 + BM25)
- [ ] 리랭킹 (20~50개 검색 → Top 3~5)
- [ ] 쿼리 재작성 (대화 맥락 반영)
- [ ] 메타데이터 필터 (특히 권한)
- [ ] 출처 표시
- [ ] 평가셋 50~200개: Recall@K, Faithfulness (RAGAS)
- [ ] 증분 인덱싱

**답이 이상하면 LLM보다 검색과 파싱부터 의심하자.**

### 기술 스택
LangChain/LlamaIndex · markitdown/docling/Upstage · BGE-M3/e5/OpenAI · Chroma/Qdrant/pgvector/Pinecone · bge-reranker/Cohere Rerank · RAGAS/LangSmith

### 다음 학습
1. 최소 예제 직접 실행
2. Chroma + PDF 한 개 Q&A
3. 하이브리드 + 리랭커 → RAGAS로 개선 전후 비교
4. Agentic RAG


---

## 11. 하이브리드 검색 + 리랭커 → RAGAS로 개선 전후 비교

"검색을 개선하고, 정말 좋아졌는지 숫자로 확인하는 실습".

### ① 하이브리드 검색 = 벡터 + BM25
| | 벡터 검색 | BM25 (키워드) |
|---|---|---|
| 강점 | 의미가 비슷한 표현 ("재택" ↔ "원격근무") | 정확한 단어 (제품코드, 고유명사, 조항 번호) |
| 약점 | 고유명사, 숫자, 코드 | 동의어, 다른 표현 |

결과 합치기: **RRF (Reciprocal Rank Fusion)** — 점수가 아니라 **순위**로 합친다. 단위가 다른 점수를 맞출 필요가 없다.
```python
def rrf(rank_lists, k=60):
    scores = {}
    for ranks in rank_lists:                 # [벡터 결과 id 목록, BM25 결과 id 목록]
        for r, doc_id in enumerate(ranks):
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + r + 1)
    return sorted(scores, key=scores.get, reverse=True)
```

### ② 리랭커
1차 후보 20~50개를 정밀한 모델로 다시 채점 → Top 3~5개.
- **bi-encoder (임베딩):** 질문과 문서를 따로 벡터화한 뒤 비교 → 빠르지만 대략적
- **cross-encoder (리랭커):** 질문과 문서를 함께 입력해서 관련도 판단 → 느리지만 정확
- 1차는 빠르게 넓게, 2차는 정확하게.
```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("BAAI/bge-reranker-v2-m3")
scores = reranker.predict([(query, c) for c in candidates])
top5 = [c for _, c in sorted(zip(scores, candidates), reverse=True)[:5]]
```

### ③ RAGAS 지표
| 지표 | 의미 | 대상 |
|---|---|---|
| Context Recall | 정답에 필요한 정보가 검색 결과에 있나 | 검색 |
| Context Precision | 상위권에 관련 문서가 있나 | 검색 |
| Faithfulness | 답변이 문서에 근거하나 (환각 여부) | 생성 |
| Answer Relevancy | 답변이 질문에 맞나 | 생성 |

### 실험 설계
```
평가셋 (질문 + 정답) 50~100개
 → A: 벡터만  /  B: 하이브리드  /  C: 하이브리드 + 리랭커
 → 같은 평가셋으로 점수 비교
```
| 구성 (가상의 숫자) | Context Recall | Faithfulness |
|---|---|---|
| A. 벡터만 | 0.68 | 0.81 |
| B. 하이브리드 | 0.77 | 0.84 |
| C. + 리랭커 | 0.85 | 0.90 |

→ "지연 시간 +300ms 대비 Recall +8%p"처럼 **근거 있는 결정**을 내릴 수 있다.

---

## 12. Agentic RAG

LLM이 **에이전트**로서 검색을 **도구**처럼 스스로 판단해서 사용하는 방식.

| | 기본 RAG | Agentic RAG |
|---|---|---|
| 검색 여부 | 항상 | 필요할 때만 |
| 검색 횟수 | 1번 | 여러 번 (부족하면 재검색) |
| 검색어 | 질문 그대로 | LLM이 만들고 수정 |
| 검색 대상 | 벡터DB 1개 | 여러 도구 중 선택 (문서, SQL, 웹, API) |
| 검증 | 없음 | 결과가 충분한지 스스로 확인 |

### 예시
"작년 대비 올해 연차 규정 변화 + 우리 팀 평균 사용률?"
```
 → search_docs("2026 연차 규정")
 → search_docs("2025 연차 규정")
 → run_sql("SELECT AVG(...) FROM leave WHERE team='영업1팀'")
 → 정보가 충분한지 확인 → 비교해서 답변
```
기본 RAG는 한 번만 검색해서 정보를 놓치고, 집계는 아예 못 한다. (→ 8장의 엑셀 집계형 질문 해결)

### 구현 뼈대 (도구 호출 반복)
```python
tools = [
    {"name": "search_docs", "description": "사내 문서를 검색한다",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "run_sql", "description": "인사 DB에 SQL을 실행한다",
     "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}, "required": ["sql"]}},
]
messages = [{"role": "user", "content": question}]
while True:
    res = client.messages.create(model="claude-sonnet-5-5", max_tokens=1024,
                                 tools=tools, messages=messages)
    if res.stop_reason != "tool_use":
        break
    messages.append({"role": "assistant", "content": res.content})
    results = [{"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b.name, b.input)}
               for b in res.content if b.type == "tool_use"]
    messages.append({"role": "user", "content": results})
print(res.content[0].text)
```
프레임워크: LangGraph, LlamaIndex Agents.

### 장단점과 실무 팁
- 장점: 비교, 여러 단계, 여러 출처가 필요한 복잡한 질문에 강하다.
- 단점: LLM을 여러 번 호출하므로 **느리고 비싸며**, 동작 예측과 디버깅이 어렵다.
- **기본 RAG를 먼저 잘 만들고**, 그것으로 해결되지 않는 질문 유형이 확인되면 도입한다. 검색 품질이 나쁘면 에이전트도 나쁘다.

**한 줄 요약:** 11장 = 검색을 더 정확하게 + 효과 측정 / 12장 = 검색을 언제, 어떻게, 몇 번 할지 LLM이 결정.

