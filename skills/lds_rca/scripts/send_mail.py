"""분석 리포트 메일 발송. 기본은 dry-run (out/*.eml 로 저장만). 실제 발송은 --send.
사용: python send_mail.py --result out/R.json --body-file out/R.md [--send]
"""
import argparse
import json
import smtplib
from email.message import EmailMessage

from common import load_config, resolve, secret, setup_stdout


def build(cfg, result, body):
    m = EmailMessage()
    m["Subject"] = f"[LDS RCA] {result['product']} / {result['rootid']} / {result['step']} ({result['eqpid']})"
    m["From"] = cfg["mail"]["from"]
    m["To"] = ", ".join(cfg["mail"]["to"])
    m.set_content(body)
    return m


def send(cfg, msg):
    mc = cfg["mail"]
    with smtplib.SMTP(mc["smtp_host"], mc["smtp_port"], timeout=30) as s:
        if mc.get("user"):
            s.starttls()
            s.login(mc["user"], secret(mc["password_env"]))
        s.send_message(msg)


if __name__ == "__main__":
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--send", action="store_true", help="실제 발송 (없으면 dry-run)")
    ap.add_argument("--config")
    a = ap.parse_args()
    cfg = load_config(a.config)
    res = json.load(open(a.result, encoding="utf-8"))
    msg = build(cfg, res, open(a.body_file, encoding="utf-8").read())
    if a.send:
        send(cfg, msg)
        print("sent to", msg["To"])
    else:
        p = resolve(f"out/{res['rootid']}.eml")
        p.write_bytes(bytes(msg))
        print("dry-run saved:", p)
