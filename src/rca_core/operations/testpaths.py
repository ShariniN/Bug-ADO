from __future__ import annotations

import re

_SEG = re.compile(r"(^|/)(tests?|__tests__|specs?)(/|$)", re.IGNORECASE)
_NAME_CI = re.compile(r"(\.(test|spec)\.|_tests?\.|^test_|(^|[_\-.])tests?\.(cs|py|ts|js|java|go)$)", re.IGNORECASE)
_NAME_CS = re.compile(r"Tests?\.(cs|java)$")  # PascalCase C#/Java: PayrollTests.cs


def is_test_path(path: str) -> bool:
    p = path.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    return bool(_SEG.search(p) or _NAME_CI.search(name) or _NAME_CS.search(name))
