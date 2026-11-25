"""errorcode.h 의 `#define <NAME> <INT>` 를 파싱해서 {정수: [이름...]} 매핑을 만든다."""
import re

DEFINE_RE = re.compile(r"^\s*#\s*define\s+([A-Za-z_]\w*)\s+\(?\s*(-?(?:0[xX][0-9a-fA-F]+|\d+))\s*\)?")

# PGM 정의 밖의 오류 유형 힌트 (로그 텍스트 기준)
OTHER_PATTERNS = {
    "memory": re.compile(r"segmentation fault|out of memory|malloc|bad_alloc|core dumped|stack overflow", re.I),
    "compile": re.compile(r"compile|syntax error|undefined reference|unresolved|parse error", re.I),
}


def parse_errorcode_header(path):
    mapping = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = DEFINE_RE.match(line)
            if m:
                mapping.setdefault(int(m.group(2), 0), []).append(m.group(1))
    return mapping


def classify(code_str, mapping, block_text=""):
    """returns {'code', 'category', 'names'}"""
    code = int(code_str, 0)
    if code in mapping:
        return {"code": code, "category": "pgm_defined", "names": mapping[code]}
    for cat, pat in OTHER_PATTERNS.items():
        if pat.search(block_text):
            return {"code": code, "category": cat, "names": []}
    return {"code": code, "category": "unknown", "names": []}


if __name__ == "__main__":
    import argparse
    import json
    from common import setup_stdout

    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--header", required=True)
    ap.add_argument("--code")
    a = ap.parse_args()
    mp = parse_errorcode_header(a.header)
    print(json.dumps(classify(a.code, mp) if a.code else {str(k): v for k, v in mp.items()},
                     ensure_ascii=False, indent=2))
