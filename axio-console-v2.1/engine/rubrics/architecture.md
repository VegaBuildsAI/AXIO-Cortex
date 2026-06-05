# Architecture Benchmark Rubric — ARCH-001

## Task
The model is asked to design a software architecture for a local AI orchestration system, covering components, data flow, and trade-offs.

## Scoring Criteria (0–100)

| Range | Label | Description |
|-------|-------|-------------|
| 90–100 | Excellent | Comprehensive design with clear components, data flow, trade-offs discussed, scalable and realistic |
| 70–89  | Good | Solid design covering major components, minor gaps in trade-off analysis or scalability |
| 50–69  | Partial | Covers the basics but misses key components or provides shallow analysis |
| 25–49  | Weak | Vague or generic answer, lacks specificity to the stated problem |
| 0–24   | Fail | No meaningful architecture proposed, off-topic, or refused |

## Key Evaluation Points
- Are all major system components identified and described?
- Is the data flow between components clear?
- Are trade-offs and design decisions explained?
- Is the design practical for local deployment (not cloud-only assumptions)?
- Does it address the AXIO-specific context (Ollama, Python, YAML config, audit logs)?

## Scoring Instructions
Return a JSON object:
```json
{ "score": <0-100>, "label": "<Excellent|Good|Partial|Weak|Fail>", "reasoning": "<2-3 sentences explaining the score>" }
```
