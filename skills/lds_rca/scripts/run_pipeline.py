"""조회 → 로그 수집 → PGM 구간 스크랩 → ERRORCODE 해석까지 수행하고 JSON 으로 출력.
(원인 분석 요약 / 메일 / history 는 SKILL.md 의 후속 단계에서 처리)

사용: python run_pipeline.py --product P --rootid R --step S [--mock]
"""
import argparse
import json
from datetime import datetime

from common import load_config, resolve, setup_stdout
from extract_pgm import extract_blocks, find_error_codes
from fetch_logs import fetch_logs
from parse_errorcode import classify, parse_errorcode_header
from query_root import query_root


def run(product, rootid, step, mock=False, config_path=None):
    cfg = load_config(config_path)
    info = query_root(cfg, product, rootid, step, mock)
    st = datetime.fromisoformat(info["starttime"])
    et = datetime.fromisoformat(info["endtime"])

    logs = fetch_logs(cfg, info["eqpid"], st, et, mock)
    mapping = parse_errorcode_header(resolve(cfg["errorcode_header"]))
    sc = cfg["scrape"]

    # 같은 종류(LDS/TSC)의 날짜별 로그는 날짜순으로 이어 붙여서 처리
    # (PGM 구간이 자정을 넘어 파일 경계에 걸칠 수 있음. line 번호는 이어붙인 기준)
    findings = []
    for kind in ("LDS", "TSC"):
        group = sorted((l for l in logs if l["kind"] == kind), key=lambda l: l["date"])
        if not group:
            continue
        text = "\n".join(l["text"].rstrip("\n") for l in group)
        fname = "+".join(l["name"] for l in group)
        for b in extract_blocks(text, rootid, sc["window_lines"], sc["max_block_lines"]):
            codes = [classify(c, mapping, b["text"]) for c in find_error_codes(b["text"])]
            findings.append({"file": fname, "kind": kind, **b, "errors": codes})

    return {
        "product": product, "rootid": rootid, "step": step, **info,
        "files_fetched": [l["name"] for l in logs],
        "match_count": len(findings),
        "findings": findings,
    }


if __name__ == "__main__":
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--rootid", required=True)
    ap.add_argument("--step", required=True)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--config")
    ap.add_argument("--out", help="결과 JSON 저장 경로 (기본 out/<rootid>.json)")
    a = ap.parse_args()
    res = run(a.product, a.rootid, a.step, a.mock, a.config)
    out = a.out or str(resolve(f"out/{a.rootid}.json"))
    with open(out, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))
