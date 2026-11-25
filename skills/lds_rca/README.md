# lds-rca

제품 + rootid + 스텝을 입력하면 내부 DB(appdb / oracle)에서 starttime, endtime, eqpid 를 조회하고,
해당 설비의 `LDS_{날짜}.log`, `TSC_{날짜}.log` 에서 `{rootid}` 와 `LDS PGM` 이 근처에 같이 있는 구간
(해당 `LDS PGM` 줄 ~ 다음 `LDS PGM` 줄)을 스크랩해서 ERRORCODE 를 `errorcode.h` 로 해석한 뒤,
원인 리포트를 메일로 보내고 history(SQLite)에 저장하는 Claude Code 스킬.

> 상태: 뼈대 (사외에서 mock 데이터로 검증 완료). **사내 연동(DB / etelnet / 로그 형식)은 미검증.**

## 역할 분담

| 단계 | 담당 |
|---|---|
| DB 조회, 로그 수집, PGM 구간 스크랩, errorcode.h 파싱, 메일, history | 스크립트 (결정적) |
| ERRORCODE 해석, 원인 분석, 리포트 작성 | Claude (SKILL.md 지침) |

## 구성

| 파일 | 역할 |
|---|---|
| `SKILL.md` | Claude 워크플로우, 규칙(설비 읽기 전용), 분석 지침 |
| `scripts/query_root.py` | DB 조회. `db.order`(기본 appdb → oracle) 순서로 시도, 먼저 결과가 나온 쪽 사용. 한쪽 장애 시 다음으로 폴백 |
| `scripts/fetch_logs.py` | 시작~종료 날짜 범위의 LDS/TSC 로그 수집. transport: `mock` / `etelnet` |
| `scripts/extract_pgm.py` | rootid + `LDS PGM` 근접(window) 매칭 → 다음 `LDS PGM` 줄까지 스크랩 |
| `scripts/parse_errorcode.py` | `errorcode.h` 의 `#define NAME 숫자` 파싱(0x 지원). 미정의 시 memory / compile / unknown 분류 |
| `scripts/run_pipeline.py` | 위 단계 일괄 실행 → JSON (`out/<rootid>.json`) |
| `scripts/send_mail.py` | 메일 발송. 기본 dry-run(.eml 저장), `--send` 로 실제 발송 |
| `scripts/save_history.py` | SQLite(`out/history.sqlite`) 저장 |
| `config.example.json` | 설정 예시 (`config.json` 으로 복사해서 사용, git 제외) |
| `sample/` | mock 데이터 (roots.json, errorcode.h, 로그 3개) |

## 사용

사외 테스트 (mock):

```
cd .claude/skills/lds-rca
python scripts/run_pipeline.py --product PRODA --rootid ROOT12345 --step STEP10 --mock
```

Claude Code 에서는 "PRODA ROOT12345 STEP10 분석해줘" 처럼 요청하면 스킬이 동작한다.
(단계별: 수집 → 분석 → `out/<rootid>.md` 리포트 → 메일 dry-run → 확인 후 발송 → history 저장)

## 사내 적용 체크리스트

1. `config.example.json` → `config.json` 복사, `mode` 를 `real` 로 변경
   - 비밀번호는 환경변수: `LDS_ORACLE_PW`, `LDS_APPDB_PW`, `LDS_SMTP_PW`
2. `scripts/query_root.py`
   - SQL 의 테이블/컬럼명(`ROOT_HIST` 등)은 임의 값 → 실제 이름으로 수정
   - appdb 는 접속 방식 미확정(ODBC 가정한 자리표시자 `_query_appdb`) → 실제 방식에 맞게 수정
   - Oracle: `pip install oracledb`
   - 시간 컬럼 형식이 `TIME_FMTS` 에 없으면 추가
3. `scripts/fetch_logs.py` 의 `EtelnetSession`
   - 로그인/프롬프트 방식에 맞춰 `equipment.prompt_regex`, `equipment.log_dir`, `etelnet_cmd` 조정
   - 안 되면 이 부분만 따로 실행해서 먼저 확인
4. `scripts/extract_pgm.py` 의 `ERRCODE_RE`
   - 실제 로그의 ERRORCODE 표기에 맞게 수정 (현재 `ERRORCODE=2001` 형태 가정)
5. `errorcode_header` 경로 확정 (현재는 로컬 파일. 설비에서 가져오려면 코드 추가 필요)
6. 메일: `mail.smtp_host`, `to` 등 설정. 처음에는 dry-run 으로 확인

## 알려진 한계 / TODO

- rootid 는 단순 문자열 검색 → 다른 rootid 에 포함된 부분 문자열 오탐 가능 (필요 시 단어 경계 매칭)
- starttime~endtime 으로 로그 줄을 시간 필터링하지 않음 (로그 타임스탬프 형식 확인 후 추가 가능)
- 같은 종류(LDS끼리, TSC끼리) 날짜별 로그는 이어붙여서 처리하므로 `start_line`/`end_line` 은 이어붙인 기준
- 큰 로그는 설비에서 `grep -n` 으로 rootid 주변만 가져오도록 최적화 가능
- history 에서 같은 errorcode 재발 여부 조회 기능 (현재는 SKILL.md 의 제안 수준)
- 설비에서는 읽기 전용 명령(cat/grep)만 사용할 것
