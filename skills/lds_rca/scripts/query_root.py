"""제품 + rootid + step → starttime / endtime / eqpid 조회.

db.order 순서대로 (예: appdb → oracle) 시도해서 먼저 결과가 나온 쪽을 사용.
사용: python query_root.py --product P --rootid R --step S [--mock]
"""
import argparse
import json
from datetime import datetime

from common import load_config, resolve, secret, setup_stdout

TIME_FMTS = ["%Y-%m-%d %H:%M:%S", "%Y%m%d%H%M%S", "%Y-%m-%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"]


def to_dt(v):
    if isinstance(v, datetime):
        return v
    for f in TIME_FMTS:
        try:
            return datetime.strptime(str(v).strip(), f)
        except ValueError:
            pass
    raise ValueError(f"시간 형식을 알 수 없음: {v!r} (TIME_FMTS 에 추가하세요)")


def _query_mock(cfg, product, rootid, step):
    data = json.loads(resolve("sample/roots.json").read_text(encoding="utf-8"))
    for r in data:
        if r["rootid"] == rootid and r["step"] == step and r["product"] == product:
            return r["starttime"], r["endtime"], r["eqpid"]
    return None


def _query_oracle(cfg, product, rootid, step):
    import oracledb  # pip install oracledb (thin mode: Oracle client 설치 불필요)

    c = cfg["db"]["oracle"]
    with oracledb.connect(user=c["user"], password=secret(c["password_env"]), dsn=c["dsn"]) as conn:
        cur = conn.cursor()
        cur.execute(c["sql"], product=product, rootid=rootid, step=step)
        row = cur.fetchone()
    return tuple(row) if row else None


def _query_appdb(cfg, product, rootid, step):
    # TODO(사내): appdb 가 무엇인지(ODBC? 자체 API?)에 맞게 수정.
    import pyodbc  # pip install pyodbc

    c = cfg["db"]["appdb"]
    conn = pyodbc.connect(f"DSN={c['odbc_dsn']};UID={c['user']};PWD={secret(c['password_env'])}")
    try:
        cur = conn.cursor()
        cur.execute(c["sql"], product, rootid, step)
        row = cur.fetchone()
    finally:
        conn.close()
    return tuple(row) if row else None


BACKENDS = {"mock": _query_mock, "oracle": _query_oracle, "appdb": _query_appdb}


def query_root(cfg, product, rootid, step, mock=False):
    order = ["mock"] if (mock or cfg.get("mode") == "mock") else cfg["db"]["order"]
    errors = []
    for name in order:
        try:
            row = BACKENDS[name](cfg, product, rootid, step)
        except Exception as e:  # 한쪽 DB 장애 시 다음 DB 로 폴백
            errors.append(f"{name}: {e}")
            continue
        if row:
            st, et, eqp = row
            return {"source": name, "starttime": to_dt(st).isoformat(sep=" "),
                    "endtime": to_dt(et).isoformat(sep=" "), "eqpid": str(eqp).strip()}
    raise LookupError(f"rootid={rootid} 조회 실패. 시도 결과: {errors or '모든 DB 에서 행 없음'}")


if __name__ == "__main__":
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--rootid", required=True)
    ap.add_argument("--step", required=True)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--config")
    a = ap.parse_args()
    print(json.dumps(query_root(load_config(a.config), a.product, a.rootid, a.step, a.mock),
                     ensure_ascii=False, indent=2))
