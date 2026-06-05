# Revenue Analysis Benchmark Rubric — REVREC-001 (v2)
#
# FIX: Original rubric scored "contract extraction & allocation schedules"
# but REVREC-001 prompt asks: "Create an ASC 606 decision tree for
# identifying performance obligations in a SaaS contract."
# This version scores the actual task.

## Task
The model is asked to produce an ASC 606 decision tree for identifying
performance obligations in a SaaS contract.

## Scoring Criteria (0–100)

| Range | Label | Description |
|-------|-------|-------------|
| 90–100 | Excellent | Covers all 5 ASC 606 steps, correct distinctness criteria (capable + separately identifiable), SaaS-specific examples (license, implementation, support, training), clear tree structure, actionable output |
| 70–89  | Good | Covers core distinctness test and most SaaS obligations, structure is clear, minor gaps (e.g. missing one criterion or one SaaS type) |
| 50–69  | Partial | Decision tree present but omits key criteria (e.g. no "separately identifiable" test) or misclassifies a common SaaS obligation |
| 25–49  | Weak | Mentions ASC 606 but logic is vague, tree is incomplete or not decision-tree format, significant omissions |
| 0–24   | Fail | Does not produce a decision tree, incorrect framework, refuses, or output is irrelevant |

## Key Evaluation Points
- Does the tree cover the two-part distinctness test (capable of being distinct AND separately identifiable)?
- Are common SaaS obligations correctly identified (subscription/license, implementation, training, ongoing support, updates)?
- Is the output structured as a decision tree (Yes/No branches, not just a bullet list)?
- Are the ASC 606 five steps referenced or at least implied?
- Are edge cases handled (e.g. bundled obligations, highly interdependent services)?

## Scoring Instructions
Return a JSON object:
```json
{ "score": <0-100>, "label": "<Excellent|Good|Partial|Weak|Fail>", "reasoning": "<2-3 sentences explaining the score>" }
```
