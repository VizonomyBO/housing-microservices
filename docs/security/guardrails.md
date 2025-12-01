# Guardrail Policy Framework

Task 06 introduced a reusable guardrail layer for the LangGraph agent. All policies are defined in `services/agent-api/src/guardrails/policy.py` and enforced through the `GuardrailEngine`. The framework groups checks into three buckets:

1. **Prompt rules** – keyword/regex patterns for classic prompt-injection attempts and restricted content.
2. **Attachment constraints** – limits on attachment counts, visibility, and country-alignment with the active conversation.
3. **Compliance filters** – coarse topic filters plus lightweight PII heuristics to prevent accidental data leaks before downstream nodes execute.

## Violation Codes

| Code | Purpose |
| --- | --- |
| `prompt_injection` | Detects instructions such as "ignore previous instructions" or "act as system" before they reach tools. |
| `prompt_policy` | Flags disallowed content (credential theft, ransomware, etc.). |
| `pii` | Indicates high-risk patterns (SSN, 16-digit card numbers). |
| `attachment_scope` | Attachments span multiple countries within a single request. |
| `attachment_limit` | More than 30 documents are attached in one run. |
| `country_mismatch` | Attachment country metadata conflicts with the conversation country. |
| `workflow_policy` | Too many workflow graphs were requested (>8) which could overload Retrieval. |
| `compliance_policy` | Prompt references topics explicitly blocked by compliance review (e.g., "top secret"). |

Blocking violations automatically set `route = escalate` and `next_subgraph = human_gate` so Task 08 can pause execution while surfacing the violation list to HumanGate reviewers.

## Extending Policies

1. Edit `services/agent-api/src/guardrails/policy.py` to add or adjust `PromptPolicyRule`, `AttachmentPolicy`, or `CompliancePolicy` values.
2. Unit-test changes under `services/agent-api/tests/guardrails/` to cover new rules.
3. Regenerate docs as needed to describe the new codes.

Future tasks (Vision, HumanGate, CacheWriter) should reference this document to understand the canonical violation codes and the guardrail entrypoint.
