"""护栏拦截异常。"""

from __future__ import annotations


class GuardrailBlockedError(Exception):
    """命中 block 规则，当次 Run 应失败。"""

    def __init__(self, codes: list[str]) -> None:
        self.codes = codes
        joined = ",".join(codes) if codes else "unknown"
        super().__init__(f"内容护栏拦截: {joined}")
