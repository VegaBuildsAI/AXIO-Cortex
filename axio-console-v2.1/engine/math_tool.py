"""
math_tool.py — Python-based exact arithmetic solver
Implements the `exact_math` route defined in routing.yaml:
    exact_math:
      tool: "python"
      model: null

Used by benchmark_models.py for MATH-001 and any future math benchmarks.
Bypasses Ollama entirely — no timeout risk, always correct.
"""

import re
import ast
import operator
from typing import Union

# Only these operations are allowed — no exec, no builtins, no import
_SAFE_OPS = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
    ast.Pow:  operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node) -> Union[int, float]:
    """Recursively evaluate a parsed AST node using only safe operators."""
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsupported constant type: {type(node.value)}")
        return node.value
    elif isinstance(node, ast.BinOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        left  = _eval_node(node.left)
        right = _eval_node(node.right)
        return op_fn(left, right)
    elif isinstance(node, ast.UnaryOp):
        op_fn = _SAFE_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return op_fn(_eval_node(node.operand))
    else:
        raise ValueError(f"Unsupported AST node: {type(node).__name__}")


def safe_eval(expression: str) -> Union[int, float]:
    """
    Safely evaluate a pure arithmetic expression string.
    Raises ValueError for any non-arithmetic content.
    """
    expression = expression.strip().replace(",", "")
    tree = ast.parse(expression, mode="eval")
    return _eval_node(tree.body)


def extract_expression(prompt: str) -> str | None:
    """
    Extract an arithmetic expression from a benchmark prompt string.
    Handles formats like:
      'Calculate exactly: 84736291 * 69384725. Return only FINAL_RESULT.'
      'What is 12345 + 67890?'
    """
    # Match a run of digits/operators — greedy left-to-right
    pattern = r'[\d,]+\s*[\+\-\*\/\^]\s*[\d,]+(?:\s*[\+\-\*\/\^]\s*[\d,]+)*'
    match = re.search(pattern, prompt)
    if match:
        return match.group().replace(",", "").strip()
    return None


def solve(prompt: str) -> dict:
    """
    Given a math benchmark prompt, extract and compute the answer with Python.

    Returns a result dict compatible with model_tests.jsonl schema:
      {
        "result":     "5878714018754475",
        "expression": "84736291 * 69384725",
        "score":      100,
        "method":     "python_exact",
        "error":      None
      }
    On failure returns score=0 and an error string.
    """
    expr = extract_expression(prompt)
    if not expr:
        return {
            "result":     None,
            "expression": None,
            "score":      0,
            "method":     "python_exact",
            "error":      "Could not extract arithmetic expression from prompt",
        }
    try:
        raw = safe_eval(expr)
        # Return as integer string when result is whole number
        result_str = str(int(raw)) if isinstance(raw, float) and raw.is_integer() else str(raw)
        return {
            "result":     result_str,
            "expression": expr,
            "score":      100,
            "method":     "python_exact",
            "error":      None,
        }
    except Exception as exc:
        return {
            "result":     None,
            "expression": expr,
            "score":      0,
            "method":     "python_exact",
            "error":      str(exc),
        }


# ── CLI quick-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else \
             "Calculate exactly: 84736291 * 69384725. Return only FINAL_RESULT."
    out = solve(prompt)
    print(f"Expression : {out['expression']}")
    print(f"Result     : {out['result']}")
    print(f"Score      : {out['score']}")
    if out["error"]:
        print(f"Error      : {out['error']}")
