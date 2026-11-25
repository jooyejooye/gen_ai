"""설비(eqpid)의 LDS_{YYYYMMDD}.log / TSC_{YYYYMMDD}.log 를 가져온다.
start~end 가 날짜를 넘기면 해당 날짜들의 파일을 모두 가져온다.

transport:
  mock    - sample/logs 폴더에서 읽기 (사외 테스트용)
  etelnet - `etelnet <eqpid>` 프로세스를 띄워 cat 으로 읽기 (사내에서 조정 필요)
읽기 전용 명령(cat)만 사용한다.
"""
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from queue import Queue, Empty

from common import resolve


def date_range(start: datetime, end: datetime):
    d = start.date()
    out = []
    while d <= end.date():
        out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out


def _fetch_mock(cfg, eqpid, kind, ymd):
    p = resolve(cfg["equipment"]["mock_log_dir"]) / f"{kind}_{ymd}.log"
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


class EtelnetSession:
    """etelnet 자식 프로세스 + 프롬프트 감지. TODO(사내): 로그인/프롬프트 방식에 맞게 조정."""

    def __init__(self, cfg, eqpid):
        eq = cfg["equipment"]
        cmd = [c.format(eqpid=eqpid) for c in eq["etelnet_cmd"]]
        self.prompt = re.compile(eq["prompt_regex"])
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=0)
        self.q = Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self._read_until_prompt(30)  # 접속 직후 프롬프트까지 소비

    def _pump(self):
        while True:
            ch = self.proc.stdout.read(1)
            if not ch:
                break
            self.q.put(ch)

    def _read_until_prompt(self, timeout):
        buf, t0 = "", time.time()
        while time.time() - t0 < timeout:
            try:
                buf += self.q.get(timeout=0.5)
            except Empty:
                if self.prompt.search(buf):
                    return buf
        return buf

    def run(self, command, timeout=120):
        marker = "__LDS_END__"
        self.proc.stdin.write(f"{command}; echo {marker}\n")
        buf, t0 = "", time.time()
        while marker not in buf.split(command, 1)[-1] and time.time() - t0 < timeout:
            try:
                buf += self.q.get(timeout=0.5)
            except Empty:
                pass
        body = buf.split(command, 1)[-1]
        return body.split(marker)[0].lstrip("\r\n")

    def close(self):
        try:
            self.proc.stdin.write("exit\n")
            self.proc.terminate()
        except Exception:
            pass


def fetch_logs(cfg, eqpid, start: datetime, end: datetime, mock=False):
    """returns [{'kind','date','name','text'}] (존재하는 파일만)"""
    transport = "mock" if (mock or cfg.get("mode") == "mock") else cfg["equipment"]["transport"]
    results = []
    sess = None
    if transport == "etelnet":
        sess = EtelnetSession(cfg, eqpid)
    try:
        for ymd in date_range(start, end):
            for kind in ("LDS", "TSC"):
                name = f"{kind}_{ymd}.log"
                if transport == "mock":
                    text = _fetch_mock(cfg, eqpid, kind, ymd)
                else:
                    path = f"{cfg['equipment']['log_dir']}/{name}"
                    text = sess.run(f"cat {path}")
                    if "No such file" in text:
                        text = None
                if text:
                    results.append({"kind": kind, "date": ymd, "name": name, "text": text})
    finally:
        if sess:
            sess.close()
    return results
