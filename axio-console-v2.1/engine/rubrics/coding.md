# Coding Benchmark Rubric — CODING-001

## Task
The model is asked to write working Python code for a specific programming task, including documentation.

## Scoring Criteria (0–100)

| Range | Label | Description |
|-------|-------|-------------|
| 90–100 | Excellent | Code is correct, runs without errors, well-structured, includes docstrings/comments |
| 70–89  | Good | Code is mostly correct, minor bugs or style issues, adequate documentation |
| 50–69  | Partial | Code has logical errors but demonstrates correct approach and structure |
| 25–49  | Weak | Significant bugs, wrong approach, or missing key requirements |
| 0–24   | Fail | Non-functional code, refused task, or pseudocode only with no real implementation |

## Key Evaluation Points
- Does the code solve the stated problem correctly?
- Is the code syntactically valid Python?
- Are edge cases handled?
- Is there adequate documentation (docstrings, inline comments)?
- Is the code structured and readable?

## Scoring Instructions
Return a JSON object:
```json
{ "score": <0-100>, "label": "<Excellent|Good|Partial|Weak|Fail>", "reasoning": "<2-3 sentences explaining the score>" }
```
