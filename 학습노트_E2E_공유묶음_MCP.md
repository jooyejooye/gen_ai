# 학습 노트: 한 줄 실행(E2E) · 공유 묶음 · MCP

## 0. `claude -p` 명령어

```powershell
claude -p (Get-Content prompts\e2e.txt -Raw -Encoding UTF8) --permission-mode acceptEdits
```

| 부분 | 뜻 |
|---|---|
| `claude -p` | `--print`. 대화창 없이 프롬프트를 한 번 실행하고, 결과를 출력한 뒤 종료하는 비대화형 모드 |
| `Get-Content ... -Raw -Encoding UTF8` | 파일 전체를 하나의 문자열로, 한글이 깨지지 않게 읽어서 프롬프트로 전달 |
| `--permission-mode acceptEdits` | 파일 수정·생성을 묻지 않고 자동으로 허용 |

### 주의할 점
- `prompts\e2e.txt`는 **상대 경로**라서, 명령을 실행하는 **현재 폴더**를 기준으로 파일을 찾는다.
  - 파일 위치: `day08\day08-m1\prompts\e2e.txt`
  - 따라서 먼저 `cd C:\Users\User\Desktop\day08\day08-m1`로 이동한 뒤 실행해야 한다.
- 이 명령은 **PowerShell 터미널**에서 실행한다. Claude 대화창에 입력하면 Claude가 그 문장을 지시로 읽는다. `!`를 붙여 Bash로 실행하면 PowerShell 문법인 `(Get-Content ...)`가 동작하지 않는다.
- `acceptEdits`를 쓰면 **실행한 폴더의 파일**이 확인 없이 수정된다.

---

## 1. 한 줄 실행(E2E)

**E2E = End-to-End(처음부터 끝까지).** 사람이 중간에 끼어들지 않고, 명령 한 줄로 업무 전체가 끝까지 처리되는지 확인하는 시험이다.

`e2e.txt`의 내용:

> DB-04 2월 9일 검사 결과를 정리해서 검토받고 결재함에 올려 주세요.

Claude가 혼자 처리해야 하는 흐름 (day08-m1 기준):

| 단계 | 담당 |
|---|---|
| ① 데이터 읽기 | `data/DB-04_20260209.csv` |
| ② 보고서 작성 | 스킬 `tilt-report`, 에이전트 `report-writer` |
| ③ 검토 | 에이전트 `report-reviewer` |
| ④ 결재함에 올리기 | `outbox/` 폴더에 저장 |
| 안전장치 | 훅 `check_review.py`(검토 없이 진행하는 것을 막음), `log_tool.py`(모든 동작 기록) |

**성공 기준:** 지시 한 줄만으로 결과물이 `outbox/`에 생기면 성공이다.

---

## 2. 2팀이 그대로 쓰는 공유 묶음

`.claude/` 폴더와 `CLAUDE.md`를 한 세트로 만든 것이다. 이 세트만 넘겨주면 누가 Claude를 켜든 같은 규칙과 같은 도구로 일하게 된다.

```
team2/
├─ CLAUDE.md               ← 팀 규칙 설명서 (Claude가 항상 먼저 읽음)
└─ .claude/
   ├─ settings.json        ← 권한(허용/금지) + 훅
   ├─ skills/              ← 업무 매뉴얼
   │   ├─ drafting-chamber-report      월간 보고서 초안
   │   ├─ checking-report-compliance   규정 R1~R5 검사
   │   ├─ ranking-chamber-defects      불량 원인 Top 3
   │   └─ summarizing-meeting-minutes  회의록 정리
   └─ agents/              ← 역할을 나눈 담당자
       ├─ ncr-researcher       조사 담당
       ├─ report-writer        작성 담당
       └─ compliance-reviewer  검토 담당
```

| 구성 요소 | 역할 |
|---|---|
| **스킬** | "이 일은 이런 순서로 해"라는 업무 매뉴얼 |
| **에이전트** | 조사·작성·검토를 서로 다른 담당자에게 맡김. 작성자가 자기 글을 직접 검토하지 않게 하려는 구조 |
| **권한** (`settings.json`) | `allow`: `python tools/*` 등 / `deny`: `data/` 읽기·수정, `rules/` 수정, `query_db.py` 직접 실행 |
| **훅** | 실행 전에는 `guard_rules.py`로 규칙 검사, 실행 후에는 `log_tool.py`로 `logs/tool_log.jsonl`에 기록 |

---

## 3. MCP (Model Context Protocol)

Claude를 **외부 시스템에 연결하는 표준 규격**이다. 흔히 "AI용 USB 포트"에 비유한다.

```
Claude ──(MCP 규격)── MCP 서버 ── 실제 시스템(DB, 메일, 결재, Slack…)
```

- MCP 서버는 "DB 조회하기", "메일 보내기" 같은 **도구 목록**을 Claude에게 알려 주고, Claude는 그 도구를 호출해서 쓴다.
- 스킬과 에이전트는 Claude가 **폴더 안에서** 일하는 방법이고, MCP는 **폴더 밖의 시스템**을 쓰게 해 주는 연결이다.
- 프로젝트에 `.mcp.json` 파일을 두면 팀원 모두가 같은 연결을 공유한다. 공유 묶음에 포함할 수 있다.

**지금 실습과 비교하면:**
- 현재는 DB 조회를 `tools/query_db.py` 같은 파이썬 스크립트로 하고, 결재함도 `outbox/` 폴더다.
- MCP를 쓰면 이 부분이 실제 사내 DB나 결재 시스템 연결로 바뀐다.
- 현재 `team2`와 `day08-m1`에는 `.mcp.json`이 없어서 MCP는 연결되어 있지 않다.

---

## 4. E2E와 권한: 허락이 필요하면 어떻게 되나?

`-p` 모드에는 승인 버튼을 누를 사람이 없다. 그래서 허락이 필요한 동작은 **멈춰서 기다리지 않고 자동으로 거부**된다. Claude는 다른 방법을 찾거나 "권한이 없어 못 했다"고 출력하고 끝난다. 그래서 **명령은 정상 종료됐는데 `outbox/`에 결과물이 없는** 상황이 생긴다. E2E가 실패하는 대표적인 이유다.

| 동작 | 결과 | 이유 |
|---|---|---|
| 파일 읽기, 검색 | ✅ 통과 | 원래 허락이 필요 없음 |
| 파일 수정·생성 | ✅ 통과 | `--permission-mode acceptEdits` |
| `python tools/...` 실행 | ✅ 통과 | `settings.json`의 `allow` |
| 그 외 셸 명령 (`pip install` 등) | ❌ 거부 | 허락이 필요한데 물어볼 수 없음 |
| `deny`에 적힌 동작 | ❌ 항상 거부 | 어떤 모드에서도 막힘 |
| 훅이 막은 동작 | ❌ 거부 | 훅은 권한 모드와 관계없이 동작 |

### E2E가 끝까지 돌게 하는 방법
1. **`settings.json`의 `allow`에 미리 추가하기 (추천).** 팀 전체에 똑같이 적용되므로 공유 묶음에 잘 맞는다.
2. **실행할 때 한 번만 허용하기:**
   ```powershell
   claude -p (Get-Content prompts\e2e.txt -Raw -Encoding UTF8) --permission-mode acceptEdits --allowedTools "Bash(python tools/*)"
   ```
3. **`--permission-mode bypassPermissions`는 피하기.** 모든 동작을 묻지 않고 허용하므로 위험하다. 다만 `deny`와 훅은 계속 적용된다.

**설계 원칙:** 업무에 필요한 동작은 `allow`에, 절대 하면 안 되는 동작은 `deny`와 훅에 넣는다.
**실패했을 때:** `logs/tool_log.jsonl`을 보면 어느 단계에서 막혔는지 확인할 수 있다.

---

## 한 줄 요약
- **공유 묶음** = 팀 전체가 쓰는 규칙·매뉴얼·담당자 세트
- **E2E** = 그 세트로 한 줄 지시가 끝까지 처리되는지 확인하는 시험
- **MCP** = 그 세트를 바깥 시스템에 연결하는 플러그
