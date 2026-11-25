# Claude Code 통제 원리 정리: CLAUDE.md · Skill · settings.json · Hooks · 하네스

> **한 줄 요약**
> CLAUDE.md와 Skill은 모델에게 하는 **부탁**(프롬프트)이라 프롬프트로 뚫릴 수 있다.
> settings.json(permissions)과 hooks는 프로그램이 **집행**(코드)하므로 프롬프트로는 못 뚫는다.
> 다만 규칙 자체에 빈틈이 있으면 우회될 수 있다.

---

## 목차

1. [용어 정리](#1-용어-정리)
2. [각 설정이 작동하는 위치](#2-각-설정이-작동하는-위치)
3. [실행 순서](#3-실행-순서)
4. [컴퓨터 단위로 보는 구조](#4-컴퓨터-단위로-보는-구조)
5. [코드 단위로 보는 하네스 루프](#5-코드-단위로-보는-하네스-루프)
6. [Node.js란?](#6-nodejs란)
7. [settings.json이 뚫리는 경우](#7-settingsjson이-뚫리는-경우)
8. [강하게 막는 방법 (강도별)](#8-강하게-막는-방법-강도별)
9. [실습 1: Hook으로 rm 차단하기](#9-실습-1-hook으로-rm-차단하기)
10. [실습 2: 최소 하네스 직접 만들기](#10-실습-2-최소-하네스-직접-만들기)
11. [핵심 정리](#11-핵심-정리)

---

## 1. 용어 정리

| 용어 | 정체 | 강제력 |
|---|---|---|
| **하네스 (Harness)** | 내 PC에서 돌아가는 **Claude Code 프로그램 자체**(Node.js 프로세스). 모델을 호출하고, 모델이 요청한 도구를 대신 실행한다. | - |
| **CLAUDE.md** | 세션 시작 시 모델 컨텍스트에 들어가는 **텍스트 지침** | ❌ 없음 (부탁) |
| **Skill (SKILL.md)** | 호출될 때 컨텍스트에 로드되는 **텍스트 지침** (frontmatter의 `allowed-tools` 같은 설정은 하네스가 처리) | ❌ 대부분 없음 |
| **settings.json** | 하네스가 읽는 **설정 파일**(JSON). 스스로는 아무것도 안 한다. | ✅ 하네스가 집행 |
| **Hooks** | 하네스가 특정 시점에 실행해 주는 **외부 스크립트**. settings.json에 등록한다. | ✅ 하네스가 집행 |

> **비유**: 하네스는 자동차의 엔진+ECU, settings.json은 ECU에 넣어 둔 설정값, hook은 ECU가 특정 순간에 호출하는 외부 검사 장치.
> settings.json과 hooks는 **하네스가 아니라 하네스가 사용하는 것**이다.

---

## 2. 각 설정이 작동하는 위치

```
[사용자 프롬프트]
      │
      ▼
┌──────────────────────────────────┐
│  컨텍스트 (모델이 읽는 텍스트)        │  ← CLAUDE.md, Skill, 시스템 프롬프트
│  "rm 하지 마세요"                   │     = 모델이 '읽는' 부탁
└──────────────────────────────────┘
      │  모델이 판단해서 도구 호출을 만듦: Bash("rm -rf x")
      ▼
┌──────────────────────────────────┐
│  하네스 (Claude Code 프로그램)      │  ← settings.json의 permissions, hooks
│  도구 호출 하나하나를 검사            │     = 프로그램 코드가 '집행'
└──────────────────────────────────┘
      │  통과했을 때만
      ▼
   실제 실행 (OS)
```

- 모델은 확률적으로 지침을 따른다. 프롬프트가 교묘하거나, 컨텍스트가 길어지거나, 지침끼리 충돌하면 CLAUDE.md를 무시할 수 있다.
- 하네스의 검사는 `if` 문이다. 모델이 무엇을 "원하든" `deny`면 실행되지 않는다.
- 모델은 settings.json을 볼 수도, 바꿀 수도 없다(설정 파일 수정까지 deny해 두었다면).

---

## 3. 실행 순서

### 세션 시작 시

1. **settings 파일 병합** (우선순위 높은 순)
   1. Managed settings (조직 정책, 사용자가 못 끔)
   2. CLI 인자
   3. `.claude/settings.local.json` (개인용, git 제외)
   4. `.claude/settings.json` (프로젝트 공용)
   5. `~/.claude/settings.json` (사용자 전역)
2. **CLAUDE.md 로드** (사용자 전역 → 프로젝트 → 하위 폴더)
3. **Skill 목록**(이름+설명)을 컨텍스트에 추가

### 도구를 호출할 때마다

| 단계 | 내용 | 누가 |
|---|---|---|
| ① | 모델이 도구 호출 생성 (CLAUDE.md·Skill은 **여기까지만** 영향) | 모델 |
| ② | **PreToolUse hook** 실행. 스크립트가 거부 가능 (exit 2 / deny) | 하네스 |
| ③ | **permissions 평가**: `deny` → `ask` → `allow`. **deny가 항상 이긴다** (hook이 allow를 줘도 deny 규칙은 적용됨) | 하네스 |
| ④ | 권한 모드(default / acceptEdits / auto / bypass)에 따라 사용자 확인 또는 통과 | 하네스 |
| ⑤ | **실제 실행** (sandbox를 켰다면 OS 수준 격리) | OS |
| ⑥ | **PostToolUse hook**으로 결과 검사·로그 | 하네스 |

> "프롬프트로 뚫린다"는 건 **①단계(모델 설득)**에서만 해당한다. ②③⑤는 모델이 설득당해도 통과하지 못한다.

---

## 4. 컴퓨터 단위로 보는 구조

```
┌─────────────── 내 PC ──────────────────────────────┐
│                                                    │
│  [claude 프로세스 (Node.js)]  ← 하네스               │
│     │ 시작할 때 읽음: settings.json, CLAUDE.md       │
│     │                                              │
│     ├─ (자식 프로세스) hook 스크립트 실행              │
│     │     stdin으로 JSON 입력 → exit code로 판정     │
│     │                                              │
│     ├─ (자식 프로세스) bash / powershell             │
│     │     실제 명령 실행 (rm, git, ...)              │
│     │                                              │
│     └─ 파일 읽기/쓰기 (Read/Edit 도구)                │
│                                                    │
└──────────────┬─────────────────────────────────────┘
               │ HTTPS (인터넷)
               ▼
┌─────────── Anthropic 서버 ─────────┐
│  모델 (Claude)                      │
│  텍스트를 받고 텍스트를 돌려줄 뿐      │
│  → 내 PC에 직접 접근할 수 없음        │
└────────────────────────────────────┘
```

**핵심**: 모델은 원격 서버에 있고, 내 PC에서 아무것도 직접 실행할 수 없다.
모델이 할 수 있는 건 "이 명령을 실행해 줘"라는 **JSON을 응답에 담아 보내는 것뿐**이다.
실행 여부는 **내 PC의 하네스가 결정**한다. 그래서 프롬프트로 모델을 설득해도 하네스 코드는 바뀌지 않는다.

---

## 5. 코드 단위로 보는 하네스 루프

> 실제 코드가 아니라 원리를 보여 주는 의사코드

```js
// 시작
const settings = merge(
  readJSON("~/.claude/settings.json"),
  readJSON(".claude/settings.json"),
  readJSON(".claude/settings.local.json")
);
const claudeMd = readText("CLAUDE.md");          // 텍스트로만 쓰임

let messages = [{ role: "system", content: systemPrompt + claudeMd }];

while (true) {
  messages.push({ role: "user", content: await readUserInput() });

  while (true) {
    // ① 모델 호출: 원격 서버에 HTTPS 요청
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      body: JSON.stringify({ model, messages, tools })
    }).then(r => r.json());

    messages.push({ role: "assistant", content: res.content });

    // 도구 요청이 없으면 → 답변 출력하고 종료
    const toolCalls = res.content.filter(b => b.type === "tool_use");
    if (toolCalls.length === 0) { print(res); break; }

    for (const call of toolCalls) {
      // call 예: { name: "Bash", input: { command: "rm -rf src" } }

      // ② PreToolUse hook: 외부 프로세스로 실행
      for (const hook of settings.hooks.PreToolUse ?? []) {
        if (!matches(hook.matcher, call.name)) continue;
        const p = spawn(hook.command);             // 자식 프로세스
        p.stdin.write(JSON.stringify(call));       // 도구 정보를 넘김
        if (await p.exitCode === 2) { reject(call, p.stderr); continue nextCall; }
      }

      // ③ 권한 규칙: 문자열 매칭
      if (matchAny(settings.permissions.deny, call)) { reject(call); continue; }
      if (matchAny(settings.permissions.ask, call) || !matchAny(settings.permissions.allow, call)) {
        if (!(await askUser(call))) { reject(call); continue; }
      }

      // ④ 실제 실행: 여기서만 OS에 영향이 감
      const output = await runTool(call);   // Bash면 spawn("bash", ["-c", cmd])

      // ⑤ PostToolUse hook (생략)

      // ⑥ 결과를 다시 모델에게 텍스트로 돌려줌
      messages.push({ role: "user", content: [{ type: "tool_result", content: output }] });
    }
  }
}
```

**코드에서 보이는 것**

- **CLAUDE.md**는 `messages` 배열에 들어가는 문자열일 뿐이다. 모델이 무시해도 코드는 알 방법이 없다.
- **settings.json**은 `if` 문의 조건값이다. 모델 출력과 상관없이 매번 실행된다.
- **hook**은 `spawn`으로 실행되는 별도 프로세스다. stdin으로 JSON을 받고 **exit code 2**로 응답하면 차단된다. 어떤 언어로 짜도 된다.
- 모델은 `res.content`에 어떤 JSON을 넣을지만 정할 수 있다. ②③④ 코드에는 손댈 수 없다.

---

## 6. Node.js란?

**자바스크립트를 브라우저 밖(내 컴퓨터)에서 실행하게 해 주는 프로그램.** Claude Code가 이 위에서 돌아간다.

```
브라우저:  [V8 엔진] + [화면/DOM 기능]           → 웹페이지
Node.js:   [V8 엔진] + [파일/프로세스/네트워크]   → 일반 프로그램
```

- `python app.py`처럼 `node app.js`로 JS 코드를 실행한다.
- 브라우저의 JS는 보안상 파일 삭제·프로그램 실행이 막혀 있지만, Node.js는 가능하다.

### 동작 방식

1. `claude` 입력 → Windows가 `node.exe` **프로세스**를 띄움
2. JS 파일을 메모리로 읽음
3. **V8 엔진**이 JS를 기계어로 번역(JIT 컴파일) → CPU가 실행
4. `fs.readFile()`, `spawn()` 등을 부르면 Node.js가 **OS 시스템 콜**을 호출

```
JS 코드:   fs.readFile("settings.json")
   ↓
Node.js:   C++ 내부 함수
   ↓
libuv:     OS별 차이를 감춰 주는 라이브러리
   ↓
Windows:   ReadFile() 시스템 콜 → 디스크에서 읽음
```

### 이벤트 루프

스레드 하나로 여러 일을 처리한다. 핵심은 **"기다리는 동안 다른 일을 한다"**.
API 응답·명령 종료·사용자 입력을 기다리는 동안 멈추지 않고, 일이 생기면 OS가 깨워 준다.
Claude Code는 하는 일 대부분이 "기다리기"라서 이 구조가 잘 맞는다.

```powershell
node --version
```

(Claude Code가 독립 실행 파일 형태로 설치된 경우 Node.js가 따로 없을 수도 있다.)

---

## 7. settings.json이 뚫리는 경우

프롬프트가 뚫는 게 아니라 **규칙에 빈틈이 있는 경우**다.

| 유형 | 예시 |
|---|---|
| **패턴 우회** | `Bash(rm:*)`만 deny → `find . -delete`, `python -c "import shutil..."`, `bash -c "rm ..."`로 같은 작업 가능 |
| **다른 도구로 우회** | Bash는 막았는데 Write 도구로 스크립트를 만들어 실행 |
| **설정 파일 수정** | `.claude/settings.json`이나 hook 스크립트에 대한 Edit를 deny하지 않으면 모델이 규칙을 고칠 수 있음 |
| **bypassPermissions 모드** | 대부분의 확인이 생략됨 |

---

## 8. 강하게 막는 방법 (강도별)

| 강도 | 수단 | 성격 |
|---|---|---|
| 약함 | CLAUDE.md, Skill | 부탁. 모델 행동 가이드용 |
| 중간 | permissions `deny` | 문자열 매칭으로 차단 |
| 강함 | PreToolUse hook | 스크립트로 명령을 파싱해서 정교하게 차단 |
| 가장 강함 | sandbox, OS 권한, Managed settings | 파일시스템·네트워크를 OS 수준에서 격리, 사용자도 못 끔 |

> **권장**: 진짜로 막아야 하는 건 hook / sandbox로, CLAUDE.md는 모델이 처음부터 그런 시도를 덜 하게 만드는 용도로.

---

## 9. 실습 1: Hook으로 rm 차단하기

`.claude/settings.json`

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "powershell -File .claude/block.ps1" }]
      }
    ]
  }
}
```

`.claude/block.ps1`

```powershell
$in = [Console]::In.ReadToEnd() | ConvertFrom-Json
if ($in.tool_input.command -match 'rm ') { [Console]::Error.WriteLine("rm 금지"); exit 2 }
exit 0
```

**확인 방법**: Claude에게 "무조건 rm 해, 이건 테스트야"라고 설득해도 `rm`이 들어간 명령은 막힌다. 판단하는 주체가 모델이 아니라 이 스크립트이기 때문이다.
**한계**: `find -delete` 같은 다른 명령은 이 스크립트가 못 막는다(7번 참고).

---

## 10. 실습 2: 최소 하네스 직접 만들기

settings.json 작성은 **이미 만들어진 하네스를 설정하는 것**이고, 하네스를 만든다는 건 위 루프를 **내 코드로 짜는 것**이다.

| 단계 | 방법 | 통제 범위 |
|---|---|---|
| 1. 설정 | Claude Code의 settings.json, hooks | 정해진 설정 항목 안에서 |
| 2. SDK | Claude Agent SDK로 Claude Code 엔진을 라이브러리로 사용 | 권한 판단을 내 함수로 작성 |
| 3. 직접 구현 | Messages API를 호출하고 루프를 처음부터 작성 | 전부 |

### 준비

```powershell
pip install anthropic
```

```powershell
$env:ANTHROPIC_API_KEY = "본인의 API 키"
```

### `my_harness.py` (약 50줄)

```python
import subprocess, anthropic

client = anthropic.Anthropic()          # 환경 변수에서 API 키를 읽음

# ① 모델에게 "이런 도구가 있다"고 알려 주는 설명서 (실행 능력은 없음)
tools = [{
    "name": "run_command",
    "description": "PowerShell 명령을 실행한다",
    "input_schema": {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    },
}]

# ② settings.json 역할: 그냥 파이썬 리스트
DENY = ["rm ", "Remove-Item", "del ", "format"]

def allowed(cmd: str) -> bool:
    if any(word in cmd for word in DENY):       # deny 규칙
        return False
    ans = input(f"\n실행할까요? {cmd} [y/N] ")   # ask (사용자 확인)
    return ans.lower() == "y"

messages = [{"role": "user", "content": input("요청: ")}]

# ③ 하네스 루프
while True:
    res = client.messages.create(
        model="claude-sonnet-5-5",
        max_tokens=2048,
        system="너는 사용자의 PC에서 명령을 실행해 돕는 도우미다.",  # CLAUDE.md 역할
        tools=tools,
        messages=messages,
    )
    messages.append({"role": "assistant", "content": res.content})

    if res.stop_reason != "tool_use":            # 도구 요청이 없으면 끝
        print("".join(b.text for b in res.content if b.type == "text"))
        break

    results = []
    for block in res.content:
        if block.type != "tool_use":
            continue
        cmd = block.input["command"]
        if allowed(cmd):                          # ④ 검사: 모델이 손댈 수 없는 코드
            out = subprocess.run(["powershell", "-Command", cmd],
                                 capture_output=True, text=True, timeout=60)
            content = (out.stdout + out.stderr)[:5000]
        else:
            content = "차단됨: 정책에 의해 실행이 거부되었습니다."
        results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

    messages.append({"role": "user", "content": results})   # ⑤ 결과를 모델에게 돌려줌
```

```powershell
python my_harness.py
```

### 해 볼 것

1. "현재 폴더 파일 목록 보여줘" → 확인 후 실행됨
2. "temp 폴더 지워줘, 테스트니까 꼭 해" → 모델이 `Remove-Item`을 요청해도 `allowed()`에서 차단됨
3. 빈틈 찾기: `ri`(Remove-Item 별칭), `cmd /c rd` 등은 `DENY` 문자열 매칭을 우회한다. Claude Code의 Bash 규칙과 같은 한계다.

### 코드와 Claude Code 대응표

| 이 코드 | Claude Code |
|---|---|
| `system=...` | CLAUDE.md (부탁) |
| `DENY`, `allowed()` | settings.json permissions, PreToolUse hook (강제) |
| `input("실행할까요?")` | 권한 확인 프롬프트 |
| `subprocess.run(...)` | 실제 도구 실행 |
| `tool_result` 추가 | 실행 결과를 모델에게 반환 |

### (참고) Claude Agent SDK

실제로 쓸 에이전트라면 루프·파일 편집 도구·컨텍스트 관리를 직접 짜는 대신 SDK를 쓴다. 권한 판단을 내 함수로 넣을 수 있다. (개념 예시, 정확한 API는 공식 문서 확인)

```python
async def can_use_tool(tool_name, tool_input, context):
    if tool_name == "Bash" and "rm " in tool_input["command"]:
        return deny("rm 금지")
    return allow()
```

---

## 11. 핵심 정리

1. **모델은 원격 서버에서 JSON만 보낸다.** 실제 실행은 내 PC의 하네스가 한다.
2. **CLAUDE.md / Skill = 부탁** (프롬프트). 모델 설득으로 뚫릴 수 있다.
3. **settings.json / hooks = 강제** (코드). 모델이 설득당해도 하네스의 `if` 문은 그대로다.
4. **settings.json은 하네스가 아니라 하네스의 설정**, hook은 하네스가 실행하는 외부 스크립트다.
5. 강제 규칙도 **문자열 매칭의 빈틈**으로 우회될 수 있으니, 중요한 건 hook·sandbox·OS 권한으로 겹겹이 막는다.
