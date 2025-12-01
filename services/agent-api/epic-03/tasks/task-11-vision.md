# Task 11 — Vision Subgraph & Multimodal Responses

## System Snapshot
- Informational/Analyst (Task 09) and Numerical (Task 10) subgraphs exist.
- Vision-specific routing is enabled via Router but implementation is pending.
- Retrieval layer already surfaces `image_caption` chunks when attachments include images.

## What You Inherit
- CacheWriter/HumanGate infrastructure.
- Attachment metadata from Task 03; guardrail policy definitions from Task 06.

## Goal
Implement the Vision subgraph to handle image-only or multimodal requests, leverage `image_caption` chunks, and enforce guardrails/HITL for sensitive media.

## Must Read Before Coding
1. `docs/epics/03.md` Task 3.4 (Vision bullet).
2. `docs/agents/implementation.md` §4.4 (vision flow + retries).
3. `docs/security/guardrails.md` (vision-specific content policies).
4. `docs/interfaces/api_contracts.md` §3.5 (streaming multimodal payloads and attachment schema).

## Implementation Scope & Files
- `services/agent-api/src/subgraphs/vision/VisionRouterNode.ts`
- `services/agent-api/src/subgraphs/vision/ImageReasonerNode.ts`
- `services/agent-api/src/subgraphs/vision/MultimodalResponderNode.ts`
- Tests `services/agent-api/tests/subgraphs/vision/`
- Update acceptance doc with Vision section.

## Step-by-Step Instructions
1. **VisionRouterNode**:
   - Inspect attachments and determine if request is image-only vs. multimodal; choose reasoning path accordingly.
   - Validate attachments via guardrails (content policy, allowed mime types).
2. **ImageReasonerNode**:
   - Consume `image_caption` chunks + metadata to build prompts for the vision-capable model/tool.
   - Provide fallback to textual description if captions missing (record warning).
3. **MultimodalResponderNode**:
   - Combine visual insights with textual context; produce structured answer referencing images/citations.
   - Integrate CacheWriter for positive answers + guardrail fallback to HumanGate on policy trigger.
4. **Testing**:
   - Image-only request -> ensures pipeline uses captions.
   - Multimodal request with both text + image -> ensures response references both.
   - Guardrail violation (unsafe image) -> ensures HumanGate invoked.
5. **Docs**:
   - Document flowchart for Vision subgraph, guardrail policies, and SSE payload expectations (images referenced by IDs).

## Definition of Done
- Vision subgraph nodes implemented with tests.
- Acceptance doc updated with Vision QA steps.
- Guardrail + HumanGate integrations verified.

## Handoff Notes
- Provide sample multimodal response payload for SSE team (Task 12).
- Note any dependencies on external vision models/services.
