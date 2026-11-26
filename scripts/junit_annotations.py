"""Print GitHub Actions error annotations for failed tests in a JUnit XML report."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET


def main(path: str) -> int:
    root = ET.parse(path).getroot()
    failures = 0
    for case in root.iter("testcase"):
        for problem in list(case.findall("failure")) + list(case.findall("error")):
            failures += 1
            message = (problem.get("message") or problem.text or "").replace("\n", " ")[:400]
            print(f"::error title={case.get('classname')}.{case.get('name')}::{message}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
