"""로그에서 `{rootid}` 와 `LDS PGM` 이 근처(window)에 같이 있는 구간을 찾아,
해당 `LDS PGM` 줄부터 다음 `LDS PGM` 줄까지 스크랩한다.
"""
import re

PGM_MARK = "LDS PGM"
ERRCODE_RE = re.compile(r"ERROR[_ ]?CODE\s*[:=]?\s*\[?\s*(-?\d+|0[xX][0-9a-fA-F]+)", re.IGNORECASE)


def extract_blocks(text: str, rootid: str, window=20, max_block=400):
    lines = text.splitlines()
    pgm_idx = [i for i, l in enumerate(lines) if PGM_MARK in l]
    if not pgm_idx:
        return []
    root_idx = [i for i, l in enumerate(lines) if rootid in l]

    starts = set()
    for r in root_idx:
        near = [p for p in pgm_idx if abs(p - r) <= window]
        if not near:
            continue
        # rootid 줄 이전(또는 같은 줄)에서 가장 가까운 PGM 줄을 시작점으로, 없으면 가장 가까운 줄
        before = [p for p in near if p <= r]
        starts.add(max(before) if before else min(near, key=lambda p: abs(p - r)))

    blocks = []
    for s in sorted(starts):
        nxt = next((p for p in pgm_idx if p > s), None)
        e = nxt if nxt is not None else min(len(lines) - 1, s + max_block)
        e = min(e, s + max_block)
        blocks.append({"start_line": s + 1, "end_line": e + 1, "text": "\n".join(lines[s:e + 1])})
    return blocks


def find_error_codes(block_text: str):
    return [m.group(1) for m in ERRCODE_RE.finditer(block_text)]


if __name__ == "__main__":
    import argparse
    import json
    from common import setup_stdout

    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", required=True)
    ap.add_argument("--rootid", required=True)
    a = ap.parse_args()
    txt = open(a.file, encoding="utf-8", errors="replace").read()
    print(json.dumps(extract_blocks(txt, a.rootid), ensure_ascii=False, indent=2))
