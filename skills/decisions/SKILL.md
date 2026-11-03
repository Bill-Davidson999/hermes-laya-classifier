---
name: decisions
description: Explicit advisory classification with a configured Laya service using predefined categories and concise summaries.
---

# Laya classification

Laya is a probabilistic classifier, not a conversational LLM. Call the native
`laya_classify` tool when a bounded classification can help with task routing,
delegated-response relevance, scope drift, or research categorization. Keep the orchestrator
responsible for planning, worker selection, verification, and authorization.

Use an existing concise summary. Do not invoke an LLM merely to prepare Laya input.
Include only the objective, relevant acceptance criteria and response summary when
classifying delegated work. Do not send secrets, full logs, or large documents.
Use meaningful category descriptions and keep their order consistent between calls.

Example tool arguments:

```json
{
  "state": "A technology company released a new AI processor for data centers.",
  "question_name": "category",
  "question": "Choose the primary news category for this summary.",
  "categories": {
    "Technology": "Computing, AI, processors, and technology products",
    "Business": "Corporate finance and general business activity",
    "Politics": "Government, elections, and public policy",
    "Sports": "Athletic teams and competitions"
  }
}
```

The tool accepts one question and 2-16 categories per request. Local guardrails:
state <=2000 characters, question <=300, question_name a letter followed by up to
63 letters/digits/underscores, labels <=64, descriptions <=160, encoded request
<=8192 bytes. These are adapter limits, not assurances that all text fits Laya's
model window. Prefer substantially shorter text and taxonomies.

On success, `category` is the selected label and `probabilities` is the complete
distribution over exactly the supplied categories. `confidence` measures
distribution concentration; `answer_confidence`, when present, is the selected
answer's confidence on Laya's separate scale. Missing answer confidence returns
null, never a fabricated value. These fields are distinct. Do not invent or
renormalize probabilities, call them proof, or assume a threshold is calibrated.
An optional `x_jev_confidence` is preserved under its own name.

For relevance use categories such as Relevant, Partially relevant, Off-topic and
Uncertain, with clear definitions. A highly probable Relevant answer does not prove
technical correctness, factual support, or completion of acceptance criteria.
Continue normal readbacks, tests and permission checks. Laya's action-head score
is intentionally not exposed and grants no execution authority.

`ok:false` contains an error and no classification. Treat it as unavailable
evidence. Do not invent a category, silently fall back to a hosted service, retry
in a loop, or reinterpret service failure as Off-topic/Uncertain. Calls can take
longer on a cold service. The 30-second SDK timeout is per blocking I/O operation,
not an overall deadline, and cannot cancel inference already running server-side.

Credentials are read privately by code from the configured external JSON file. Never read,
paste, include in tool arguments, or display them. Endpoint and credentials are
not model-controlled inputs. This skill introduces no automatic invocation,
middleware, approval, delegation, or authorization behavior.
