"""분석 결과를 SQLite history 에 저장.
사용: python save_history.py --result out/R.json --summary "원인 요약" [--mailed]
"""
import argparse
import json
import sqlite3
from datetime import datetime

from common import load_config, resolve, setup_stdout

DDL = """CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT,
  product TEXT, rootid TEXT, step TEXT, eqpid TEXT, starttime TEXT, endtime TEXT,
  errorcodes TEXT, error_names TEXT, categories TEXT,
  summary TEXT, mailed INTEGER, raw_json TEXT)"""


def save(cfg, result, summary, mailed):
    errs = [e for f in result["findings"] for e in f["errors"]]
    db = resolve(cfg["history_db"])
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as c:
        c.execute(DDL)
        c.execute(
            "INSERT INTO history(created_at,product,rootid,step,eqpid,starttime,endtime,errorcodes,"
            "error_names,categories,summary,mailed,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), result["product"], result["rootid"],
             result["step"], result["eqpid"], result["starttime"], result["endtime"],
             ",".join(str(e["code"]) for e in errs),
             ",".join(n for e in errs for n in e["names"]),
             ",".join(sorted({e["category"] for e in errs})),
             summary, int(mailed), json.dumps(result, ensure_ascii=False)))
    return str(db)


if __name__ == "__main__":
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--result", required=True)
    ap.add_argument("--summary", default="")
    ap.add_argument("--mailed", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    res = json.load(open(a.result, encoding="utf-8"))
    print("saved:", save(load_config(a.config), res, a.summary, a.mailed))
