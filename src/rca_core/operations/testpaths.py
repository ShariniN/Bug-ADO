from __future__ import annotations

import re

_SEG = re.compile(r"(^|/)(tests?|__tests__|specs?)(/|$)", re.IGNORECASE)
_NAME = re.compile(r"(\.(test|spec)\.|_tests?\.|tests?\.(cs|py|ts|js|java|go)$|^test_)", re.IGNORECASE)


def is_test_path(path: str) -> bool:
    p = path.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    return bool(_SEG.search(p) or _NAME.search(name))
