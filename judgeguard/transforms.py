"""Controlled presentation changes: order swap and a comments-only style variant."""
from __future__ import annotations

import ast

STYLE_BANNER = (
    "# ------------------------------------------------------------------",
    "# Solution overview",
    "# This implementation follows the task specification step by step.",
    "# Inputs are handled carefully and the result is returned explicitly.",
    "# Edge cases were considered while writing this function.",
    "# ------------------------------------------------------------------",
)
RETURN_COMMENT = "# Return the computed result to the caller."


class TransformError(ValueError):
    pass


def original_order(task: dict) -> list[str]:
    return [c["id"] for c in task["candidates"]]


def swapped_order(task: dict) -> list[str]:
    return list(reversed(original_order(task)))


def style_only_variant(source: str) -> str:
    """Add comments only. Raises unless the parsed program is identical to the original."""
    out = list(STYLE_BANNER) + [""]
    for line in source.splitlines():
        stripped = line.lstrip()
        if stripped == "return" or stripped.startswith("return "):
            out.append(line[: len(line) - len(stripped)] + RETURN_COMMENT)
        out.append(line)
    styled = "\n".join(out) + "\n"
    if ast.dump(ast.parse(source)) != ast.dump(ast.parse(styled)):
        raise TransformError("style-only variant changed the parsed program")
    return styled


def presented_sources(task: dict, condition: str) -> list[dict]:
    """Return [{candidate_id, source}] in display order for 'original', 'swapped' or 'style'."""
    by_id = {c["id"]: c["source"] for c in task["candidates"]}
    if condition == "original":
        order = original_order(task)
    elif condition == "swapped":
        order = swapped_order(task)
    elif condition == "style":
        order = original_order(task)
        by_id[task["style_target"]] = style_only_variant(by_id[task["style_target"]])
    else:
        raise TransformError(f"unknown condition: {condition!r}")
    return [{"candidate_id": cid, "source": by_id[cid]} for cid in order]


def transformations(task: dict, condition: str) -> list[str]:
    return {
        "original": [],
        "swapped": ["swap_display_order"],
        "style": [f"style_only_comments:{task['style_target']}"],
    }[condition]
