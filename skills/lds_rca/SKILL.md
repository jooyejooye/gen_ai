---
name: lds-rca
description: 제품 + rootid + 스텝을 받아 내부 DB(appdb/oracle)에서 starttime/endtime/eqpid 를 조회하고, 해당 설비의 LDS/TSC 로그에서 LDS PGM 구간을 추출해 ERRORCODE 를 해석(errorcode.h 매핑)한 뒤 원인 리포트를 메일로 보내고 history 에 저장한다. LDS PGM 오류 분석, rootid 로그 확인 요청 시 사용.
---

# LDS RCA

입력: `product`, `rootid`, `step` (없으면 사용자에게 물어볼 것)

## 규칙
- 설비에서는 **읽기 전용 명령(cat/grep)만** 사용한다. 설비에 쓰기/삭제/재시작 금지.
- 비밀번호는 환경변수로만 사용. 출력/메일/history 에 노출하지 않는다.
- 아래 스크립트는 모두 이 스킬의 `scripts/` 에 있고, 스킬 디렉터리에서 실행한다.
- 사외 테스트는 `--mock` (sample 데이터 사용).

## 워크플로우

1. 수집/해석 (DB 조회 → 로그 수집 → PGM 구간 스크랩 → ERRORCODE 해석):
   ```
   python scripts/run_pipeline.py --product <P> --rootid <R> --step <S> [--mock]
   ```
   결과는 stdout 과 `out/<rootid>.json` 에 저장된다.
   - `match_count == 0` 이면 원인 후보(rootid 오타, 로그 날짜, eqpid, window 설정)를 알려주고 중단.
   - 조회 실패 시 에러 메시지에 appdb/oracle 각각의 실패 사유가 나온다. 그대로 보고.

2. 분석 (Claude 가 수행). `findings[*]` 마다:
   - `errors[*].category`:
     - `pgm_defined` → `names` (errorcode.h 의 이름)와 로그 문맥으로 PGM 어디서 왜 실패했는지 설명
     - `memory` / `compile` → PGM 정의 외 오류. 로그 원문 근거를 들어 설명
     - `unknown` → 단정하지 말고 "미정의 코드"로 표기, 확인 필요 사항 제시
   - TSC 로그 구간이 있으면 LDS 와 시간순으로 대조
   - 같은 rootid 의 구간이 여러 개면 타임라인으로 정리

3. 리포트 작성 → `out/<rootid>.md` (제목, 입력/설비/시간, 에러코드 표, 원인 추정, 근거 로그 발췌, 권장 대응)

4. 메일: 먼저 dry-run 으로 미리보기하고 **사용자 확인 후** 실제 발송.
   ```
   python scripts/send_mail.py --result out/<R>.json --body-file out/<R>.md          # dry-run
   python scripts/send_mail.py --result out/<R>.json --body-file out/<R>.md --send   # 실제 발송
   ```

5. history 저장:
   ```
   python scripts/save_history.py --result out/<R>.json --summary "<원인 한 줄 요약>" [--mailed]
   ```
   저장 전에 `out/history.sqlite` 에서 같은 errorcode 의 과거 건이 있는지 확인해 리포트에 "재발 여부"를 덧붙여도 좋다.

## 설정
`config.example.json` 을 `config.json` 으로 복사 후 사내 값으로 수정 (`mode`: `mock` → `real`).
- `db.order`: DB 조회 순서 (기본 appdb → oracle, 먼저 결과가 나온 쪽 사용)
- `equipment.transport`: `etelnet`
- `errorcode_header`: errorcode.h 경로 (로컬 사본 경로 또는 설비에서 가져오는 방식으로 변경)
