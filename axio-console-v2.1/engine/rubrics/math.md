# Math Benchmark Rubric — MATH-001

## Task
The model is asked to solve a multi-step arithmetic or algebraic problem and show its reasoning.

## Scoring Criteria (0–100)

| Range | Label | Description |
|-------|-------|-------------|
| 90–100 | Excellent | Correct final answer, clear step-by-step reasoning, no errors |
| 70–89  | Good | Correct final answer, reasoning present but minor gaps or unclear steps |
| 50–69  | Partial | Incorrect final answer but correct approach or partial steps shown |
| 25–49  | Weak | Significant reasoning errors, wrong approach, final answer wrong |
| 0–24   | Fail | No meaningful attempt, refused to answer, or completely wrong |

## Key Evaluation Points
- Is the final numerical answer correct?
- Are intermediate steps shown and logically connected?
- Are units and notation handled correctly?
- Does the model catch and correct its own errors?

## Scoring Instructions
Return a JSON object:
```json
{ "score": <0-100>, "label": "<Excellent|Good|Partial|Weak|Fail>", "reasoning": "<2-3 sentences explaining the score>" }
```
