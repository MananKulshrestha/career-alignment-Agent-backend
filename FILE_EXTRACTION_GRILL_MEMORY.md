# File Extraction Grill Memory

Purpose: durable memory for a three-round grill on the planned file-upload and profile-evidence extraction feature.

Session context captured on 2026-07-04:
- Feature goal: let users add files such as resumes, certifications, transcripts, and project decks, then extract skills, experiences, projects, certifications, education, achievements, and related evidence.
- Current recommended product boundary: uploaded files create draft evidence; approved drafts create profile items; only saved profile items feed matching, selection, and resume tailoring.
- Current recommended technical boundary: reuse existing `UserProfileItem`, `ProfileItemPayload`, and `evidence_gaps`; add source-document ingestion, extraction-run metadata, document parsers, structured agent extraction, review-first approval, deterministic fallback, and focused tests.

## Round 1 Questions

1. What is the core domain object boundary between an uploaded source document, an extraction run, a draft profile item, and a saved `UserProfileItem`? Explain why these should or should not be separate persisted concepts.
2. Why is review-first approval safer than auto-saving extracted profile items, and what production problems could auto-save create in this resume-tailoring system?
3. You proposed helper functions like `extract_skills`, `extract_experiences`, and `extract_certifications`. Should these be separate LLM calls, deterministic post-processing functions, or some hybrid? Defend the choice in terms of correctness, cost, testability, and failure isolation.

## Round 1 Final Answers

### 1. Source document, extraction run, draft item, and saved profile item boundaries

These should be separate concepts because they represent different stages of truth, review, and ownership.

An uploaded source document is raw user-provided evidence. It answers: "What file did the user provide, what type was it, where is it stored, what hash identifies it, and what readable text could be extracted?" It should persist independently because the system may need to dedupe uploads, retry extraction, audit where a claim came from, or re-run extraction after prompt/schema improvements. It is not itself profile evidence; it is the evidence source.

An extraction run is a processing attempt against a source document. It answers: "Which parser/model/prompt/fallback processed this document, did it succeed, what warnings appeared, and what draft evidence did it produce?" This should be separate because extraction is repeatable, fallible, model-versioned, and auditable. A single document may have multiple runs over time.

A draft profile item is a candidate claim produced by extraction. It answers: "What might be saved as a skill, project, experience, certification, education item, or achievement?" It is not yet trusted enough to feed matching or resume tailoring. Drafts should include provenance snippets, confidence, warnings, and evidence gaps. They may be stored inside the extraction run JSON at first rather than as first-class rows, unless the UI needs long-lived granular draft state.

A saved `UserProfileItem` is reviewed profile evidence. It answers: "What has the user accepted as usable career evidence?" This is the only object that should feed job matching, selection planning, and resume generation. It should keep enough provenance in its payload or metadata to trace back to the document, but its meaning is different from the draft: it is approved user-owned evidence, not model output waiting for review.

The strongest boundary is therefore:
- source document = raw evidence container
- extraction run = processing/audit record
- draft item = proposed structured evidence
- saved profile item = approved evidence used by downstream workflows

Keeping these separate prevents accidental trust escalation. It also enables dedupe, retry, review, observability, and future migration without corrupting the core profile.

### 2. Why review-first is safer than auto-save

Review-first approval is safer because this product optimizes for truthful resume tailoring. Uploaded resumes and decks can be stale, aspirational, ambiguous, or written by someone else. An LLM/parser can also misread layout, mix sections, mistake job requirements for user skills, or turn a project mention into a stronger ownership claim than the file supports.

Auto-save can create production problems:
- False evidence pollution: unsupported skills, tools, dates, metrics, employers, certifications, or titles enter the profile.
- Downstream resume hallucination amplification: once bad evidence is a `UserProfileItem`, the selection and resume-writing agents may treat it as legitimate support.
- User trust damage: the app may later generate a resume claim the user never approved.
- Bad matching: job-match scores can rise because extracted skills were over-inferred.
- Dedupe/version confusion: stale uploaded resumes may overwrite newer manually curated profile items.
- Compliance/audit weakness: it becomes harder to explain which claims were user-approved versus merely model-extracted.
- UX debt: users may have to clean up invisible or surprising profile mutations.

Review-first does not mean slow or clunky. The system can still present high-confidence drafts with batch approval, inline editing, and clear source snippets. But the default should be `auto_save=false`: drafts are proposed; the user decides what becomes profile evidence.

The only reasonable exception is a deliberate future "trusted import" mode, gated by explicit user action and still with provenance, conflict detection, and a reversible import log.

### 3. Should category helpers be separate LLM calls or deterministic functions?

The best default is a hybrid with one structured LLM extraction call followed by deterministic category-specific post-processing functions.

One LLM call should read the document text and produce a structured extraction object containing draft skills, experiences, projects, certifications, education, achievements, warnings, and document-level uncertainty. This is better than six independent LLM calls because a resume or deck is context-heavy: dates, organizations, tools, and outcomes often connect across sections. One pass reduces contradictory interpretations, prompt drift, cost, latency, and duplicated token use.

The helper functions `extract_skills`, `extract_experiences`, `extract_projects`, and similar should initially be deterministic validators/normalizers, not separate model calls. They should:
- coerce the LLM output into `ProfileItemCreate` shapes
- enforce kind-specific required fields and evidence gaps
- dedupe repeated claims
- attach provenance and confidence
- reject unsupported or empty items
- normalize dates, URLs, skills, issuer names, and source IDs
- downgrade weak claims to warnings or gaps

This is more testable because deterministic functions can be unit-tested without API keys. It is also safer because validation rules remain in code rather than only in prompt language.

Separate per-category LLM calls should be a later escalation path, not the default. They make sense if a category is hard enough to warrant specialized reasoning, such as dense project decks or certification transcripts, or if the first pass marks a category as low confidence. In that future design, the orchestrator can call targeted refiners only for low-confidence sections. That preserves failure isolation without paying the six-call cost on every upload.

Final rule:
- default path: one structured extraction LLM call
- category helpers: deterministic normalization, validation, provenance, gaps, and dedupe
- fallback path: deterministic heuristic extraction when LLM is off
- escalation path: targeted per-category LLM refinement only for low-confidence or high-value sections

## Round 1 Analysis

The critical design insight is that the system must not confuse extraction with truth. A file can be evidence, but model extraction from that file is only a proposal. The durable profile should remain the trusted boundary.

The main architectural risk is over-normalizing too early. If drafts are immediately forced into the same shape as saved profile items, the system may lose uncertainty, provenance, and conflict details that the review UI needs. The draft layer should therefore preserve metadata that a final `UserProfileItem` may only reference compactly.

The main product risk is making the upload flow feel magical while hiding uncertainty. The better UX is "here is what I found, with source snippets and missing details," not "I updated your profile behind the scenes."

The main engineering tradeoff is persistence granularity. Storing draft items as JSON on `ProfileExtractionRun` is enough for a first implementation and keeps the schema small. First-class draft rows become worthwhile only if the product needs partial approval state, per-draft editing history, collaborative review, or asynchronous extraction queues.

Round 1 decision:
- Persist source documents and extraction runs.
- Store draft extracted items as run JSON for v1.
- Save `UserProfileItem` rows only after user approval.
- Use one structured LLM extraction call plus deterministic category post-processing.
- Keep a deterministic fallback so tests and local development remain keyless.

## Round 2 Questions

1. Design the exact JSON contract for a `ProfileDocumentExtraction` returned by the agent. What top-level fields, per-item fields, provenance fields, confidence fields, and warning/error fields are required so the service can safely render drafts and later save approved items?
2. Suppose a user uploads an old resume saying "AWS, Docker, Kubernetes" in a skills list, and a project deck saying they personally built Docker deployment but only watched a teammate manage Kubernetes. How should extraction, dedupe, confidence, and review UI behavior prevent Kubernetes from becoming a strong saved skill?
3. What are the precise failure modes for PDF/DOCX/PPTX text extraction in this app, and what should the backend return for each: block, warn with partial drafts, request a different file, or allow user review?

## Round 2 Final Answers

### 1. `ProfileDocumentExtraction` JSON contract

The agent output must be structured enough for review UI rendering and backend validation, but it should not pretend that extraction is final profile truth. The service should add database identifiers such as `document_id` and `extraction_run_id`; the agent should return extraction content and uncertainty.

Recommended agent schema:

```json
{
  "schema_version": "1.0",
  "detected_document_kind": "resume",
  "document_summary": "Candidate resume with backend projects, education, and skills.",
  "overall_confidence": 0.82,
  "extraction_risk": "medium",
  "draft_items": [
    {
      "draft_id": "draft_project_job_tracker",
      "kind": "project",
      "source_item_id": "doc_project_job_tracker",
      "payload": {
        "title": "Backend Job Tracker",
        "description": "Built a FastAPI job tracker with PostgreSQL persistence.",
        "skills": ["Python", "FastAPI", "PostgreSQL"],
        "tech_stack": ["FastAPI", "PostgreSQL"],
        "metrics": []
      },
      "confidence": 0.86,
      "support_level": "direct",
      "review_recommendation": "approve_after_review",
      "provenance": [
        {
          "locator": "page 1",
          "section_label": "Projects",
          "source_snippet": "Backend Job Tracker - FastAPI, PostgreSQL...",
          "character_start": 1200,
          "character_end": 1310,
          "confidence": 0.9
        }
      ],
      "warnings": [
        {
          "code": "missing_metric",
          "message": "No measurable outcome was found for this project.",
          "field_name": "measurable_impact",
          "severity": "medium"
        }
      ]
    }
  ],
  "excluded_claims": [
    {
      "claim": "Kubernetes ownership",
      "reason": "Source says the candidate observed a teammate managing Kubernetes, not that they personally used it.",
      "provenance": [
        {
          "locator": "slide 7",
          "source_snippet": "Teammate managed Kubernetes deployment while I handled Docker packaging.",
          "confidence": 0.92
        }
      ],
      "severity": "high"
    }
  ],
  "document_warnings": [
    {
      "code": "stale_resume_possible",
      "message": "The resume appears older than another uploaded source.",
      "severity": "medium"
    }
  ],
  "unresolved_questions": [
    {
      "field_name": "project_job_tracker.measurable_impact",
      "question": "What usage, latency, reliability, or user impact can you support for Backend Job Tracker?",
      "priority": "high"
    }
  ]
}
```

Required top-level fields:
- `schema_version`: allows future schema migration.
- `detected_document_kind`: lets the service compare user-declared file kind with detected content.
- `document_summary`: short UI summary and logging aid.
- `overall_confidence`: document-level quality signal.
- `extraction_risk`: low, medium, high. This should reflect source quality, ambiguity, and conflict, not how impressive the candidate is.
- `draft_items`: proposed profile evidence, not saved evidence.
- `excluded_claims`: claims noticed but judged unsafe to save.
- `document_warnings`: parser/model/source warnings.
- `unresolved_questions`: high-value questions for the user.

Required per-item fields:
- `draft_id`: stable within the run so the UI can approve/edit/reject a draft.
- `kind`: must match `ProfileItemKind`.
- `source_item_id`: proposed stable id for saved `UserProfileItem`, sanitized and dedupe-safe.
- `payload`: must be compatible with `ProfileItemPayload`.
- `confidence`: confidence in this draft item as a candidate profile item.
- `support_level`: `direct`, `listed_only`, `inferred`, `adjacent`, `conflicting`, or `insufficient`.
- `review_recommendation`: `approve_after_review`, `needs_edit`, `ask_user`, or `do_not_save`.
- `provenance`: at least one source snippet for every non-trivial claim.
- `warnings`: item-level warnings tied to fields.

Required provenance fields:
- `locator`: page, slide, paragraph, or chunk label.
- `section_label`: optional but useful for resume sections like Skills or Experience.
- `source_snippet`: short quote or paraphrase span from extracted text.
- `character_start` and `character_end`: optional when available; useful for traceability.
- `confidence`: confidence that this snippet supports the claim.

The backend should still validate everything. Agent output is not trusted just because it matches the schema. The service must reject empty descriptions, unknown kinds, unsupported source IDs, missing provenance, malformed dates/URLs, and claims marked `conflicting` or `insufficient` unless the user edits them into a supportable form.

### 2. Preventing Kubernetes from becoming a strong saved skill

The key is to treat skill mentions as claims with support levels, not as flat keywords.

In the old resume, "AWS, Docker, Kubernetes" in a skills list is only listed evidence. It says the term appears in the user's self-presentation, but it does not prove ownership, recency, depth, or project context. That can produce a low or medium confidence skill draft only if no contradictory source exists.

In the project deck, "I built Docker deployment; teammate managed Kubernetes" is more specific and more recent/contextual if the deck is tied to an actual project. It directly supports Docker, but it limits Kubernetes. The system should extract:
- Docker as direct project evidence.
- Kubernetes as an excluded or low-support claim, depending on wording.
- A user-facing question: "Did you personally configure, deploy, or operate Kubernetes in this project? If yes, what did you own?"

Dedupe should group claims by normalized skill name across sources. Each grouped claim should track:
- strongest supporting source
- strongest limiting or conflicting source
- support level
- provenance snippets
- source freshness if dates exist
- source kind weight

For Kubernetes, the merged result should not be `direct` because the strongest contextual source says the user did not own it. A flat resume skill list cannot override a specific ownership limitation from a project deck. The merged result should become one of:
- `do_not_save` if the deck clearly says the user only observed a teammate's Kubernetes work.
- `ask_user` if the resume suggests Kubernetes but project evidence is ambiguous.
- `listed_only` if no conflicting detail exists, with a weak evidence warning.

The review UI should make this visible:
- show Kubernetes under "Needs confirmation" or "Not saved automatically," not in the primary approved skills list.
- display both snippets side by side.
- explain the limitation plainly: "Mentioned in resume skills list, but project deck says teammate handled Kubernetes."
- offer actions: reject, edit into adjacent wording, or confirm with a required ownership note.

If the user approves Kubernetes anyway without adding concrete ownership evidence, the saved item should either remain weak with `evidence_source="listed on uploaded resume; ownership not confirmed"` or be blocked from strong resume usage. The resume-writing workflow should never turn that into "deployed Kubernetes services" unless a saved profile item contains direct support.

Final rule:
- Keyword presence is not proof.
- Specific ownership evidence outranks generic skill lists.
- Conflicts should lower confidence and force review.
- Unsupported or teammate-owned claims should not become strong saved skills.

### 3. PDF/DOCX/PPTX extraction failure modes and backend behavior

The backend should distinguish parser failure, source quality problems, and partial extraction. Not all failures should block the upload, but no failure should silently produce trusted profile items.

Failure modes and behavior:

- Unsupported extension or content type: block with a clear 400. Ask for PDF, DOCX, PPTX, or TXT.
- File too large: block with a clear 400. Include the configured max size.
- Empty file or zero extracted text: block. Ask for a readable file or pasted text.
- Corrupt or encrypted file: block if parser cannot read it. Ask the user to upload an unlocked/exported copy.
- Password-protected PDF/DOCX/PPTX: block. Do not ask for passwords in this workflow.
- Scanned image-only PDF: block for v1 unless OCR is explicitly implemented. Ask for a text-based PDF/DOCX or pasted text.
- Very low text volume after extraction: block if it cannot support meaningful evidence, or allow manual review only if there are a few usable snippets.
- Partial PDF extraction due to unreadable pages: warn and allow partial drafts if enough useful text remains. Include page-level warnings.
- DOCX with tables/text boxes/headers that parse incompletely: warn and allow review if core sections are extracted; block only if the result is unusable.
- PPTX with speaker notes, grouped shapes, or odd layout: warn that slide order/layout may be imperfect. Allow review if snippets are meaningful.
- Duplicated text from headers/footers: normalize where possible; warn only if it materially affects extraction quality.
- Garbled encoding or broken Unicode: block if meaning is lost; warn if isolated characters are affected.
- Parser timeout: fail the extraction run and mark document status failed. User can retry or upload a simpler file.
- Text exceeds model/context limit: truncate or chunk deterministically, warn that only the first configured amount was analyzed, and prefer asking for a more focused file if important sections may be omitted.
- Conflicting document kind: warn if user marks a file as `certification` but content looks like a resume. Allow review, but set extraction risk medium/high.

Policy:
- Block when there is no reliable text to review.
- Warn and allow review when enough meaningful text exists but quality is imperfect.
- Never auto-save from a degraded extraction.
- Store parser warnings in the extraction run so the UI and logs explain why confidence is low.

## Round 2 Analysis

The contract should carry uncertainty as first-class data. A draft item without provenance is dangerous because reviewers cannot tell whether the system found evidence or invented a clean profile object. A draft item without support level is also dangerous because "Kubernetes" from a generic skills list and "configured Kubernetes deployments in production" are not equivalent.

The hardest design problem is not extraction. It is claim calibration. The system needs to know whether a claim is directly supported, merely listed, adjacent, contradicted, or insufficient. That support level should affect dedupe, review UI placement, save behavior, matching, and resume usage.

The second hard problem is preserving negative evidence. If a deck says "teammate handled Kubernetes," that is not just absence of Kubernetes evidence. It is a limiting fact. The extraction contract needs `excluded_claims` or a similar mechanism so the system does not lose that information during normalization.

Parser behavior should be user-friendly but strict at the trust boundary. Partial extraction can be useful as long as it is visibly partial and review-first. It becomes unsafe only if the app treats partial drafts as approved evidence.

Round 2 decision:
- Define agent output around draft items, support levels, provenance, warnings, excluded claims, and unresolved questions.
- Treat generic skill lists as weak/listed evidence unless supported elsewhere.
- Treat specific ownership limitations as confidence-lowering or claim-blocking evidence.
- Block unreadable files; warn on partial-but-useful extraction.
- Keep degraded extractions review-only.

## Round 3 Questions

1. Define the backend approval algorithm from selected draft items to saved `UserProfileItem` rows. What validation must happen before saving, how should edited drafts be handled, and what should happen to drafts marked `conflicting`, `listed_only`, or `insufficient`?
2. Design the database and idempotency strategy for repeated uploads, extraction retries, and approval retries. How should file hashes, extraction run ids, draft ids, and `source_item_id` uniqueness interact without overwriting curated user profile data?
3. What focused test suite would prove this feature is production-ready without over-testing implementation details? Include parser tests, extraction contract tests, approval tests, downstream resume-tailoring regression tests, and keyless fallback tests.

## Round 3 Final Answers

### 1. Backend approval algorithm

Approval should be a dedicated service operation, not a thin wrapper over `add_profile_item`. The service must treat agent drafts as untrusted input, even when they came from a stored extraction run.

Recommended approval request shape:

```json
{
  "extraction_run_id": "uuid",
  "items": [
    {
      "draft_id": "draft_project_job_tracker",
      "action": "approve",
      "edited_kind": "project",
      "edited_payload": {},
      "edited_source_item_id": null
    }
  ]
}
```

Approval algorithm:

1. Load `ProfileExtractionRun` by `extraction_run_id` and `user_id`.
2. Verify the run succeeded and belongs to a source document owned by the same user.
3. Load the stored draft JSON from the extraction run, not from client-provided draft content.
4. For each requested `draft_id`, find the matching stored draft.
5. Apply user edits only to approved editable fields. Do not allow edits to forge parser/model metadata, document ownership, or extraction run identity.
6. Validate `kind` against `ProfileItemKind`.
7. Validate `payload` against `ProfileItemPayload`.
8. Require a non-empty description and at least one meaningful field beyond metadata.
9. Require provenance for non-manual claims, unless the user explicitly converts the item into a manual entry.
10. Attach metadata into the payload using the existing `extra="allow"` behavior:
    - `source_document_id`
    - `extraction_run_id`
    - `draft_id`
    - `provenance`
    - `support_level`
    - `extraction_confidence`
    - `approved_from_document=true`
    - `approval_notes` if the user edited or confirmed weak evidence
11. Handle support level:
    - `direct`: can be approved after normal validation.
    - `adjacent`: can be approved, but keep adjacent wording and warnings.
    - `listed_only`: can be saved only as weak/listed evidence with `evidence_source` or an evidence gap. It must not be upgraded to strong experience without user-added support.
    - `inferred`: can be saved only if the payload wording stays conservative and provenance supports the inference.
    - `insufficient`: block saving unless user edits the item with enough concrete information to change support level or turns it into a manual item.
    - `conflicting`: block by default. Allow saving only if the user explicitly resolves the conflict with an edit and the saved payload preserves the limitation or includes a clear manual confirmation note.
12. Run `add_kind_specific_evidence_gaps(kind, payload)` before persistence.
13. Check `source_item_id` collision rules before calling `add_profile_item`.
14. Save all approved items in one transaction when possible. If one item fails, return field-level errors and do not partially save unless the API explicitly supports partial success.
15. Mark the extraction run/document approval status and store which draft IDs were approved, rejected, or edited.

Edited drafts are allowed, but edits must not hide uncertainty. If the user edits "Kubernetes" from `listed_only` into "Configured Kubernetes deployments," the approval service should require a support note or manual provenance. Otherwise the item should remain weak or be rejected. User edits are valuable, but they are not automatically stronger evidence unless they add concrete ownership, dates, metrics, issuer details, links, or supporting context.

The service should distinguish three cases:
- Approved extracted evidence: source-backed claim from a document.
- Approved edited evidence: source-backed claim modified by the user.
- Manual override evidence: user asserts a claim beyond the source. This should be visibly marked so downstream resume generation can be conservative if needed.

### 2. Database and idempotency strategy

The database should support retry and dedupe without overwriting curated profile data.

Recommended tables:

- `UserSourceDocument`
  - `id`
  - `user_id`
  - `kind`
  - `filename`
  - `content_type`
  - `file_hash`
  - `storage_path`
  - `extracted_text_hash`
  - `character_count`
  - `status`
  - `parser_warnings`
  - `error_message`
  - timestamps

- `ProfileExtractionRun`
  - `id`
  - `source_document_id`
  - `user_id`
  - `status`
  - `model_name`
  - `prompt_version`
  - `schema_version`
  - `draft_items`
  - `excluded_claims`
  - `warnings`
  - `approved_draft_ids`
  - `rejected_draft_ids`
  - `success`
  - `error_message`
  - timestamps

For v1, draft items can live as JSON on `ProfileExtractionRun`. Move to a `ProfileDraftItem` table only when the UI needs independent draft editing state, collaboration, audit history per draft, or async review queues.

Idempotency rules:

- File upload dedupe:
  - Compute `file_hash` from raw bytes.
  - If the same user uploads the same file hash again, return the existing document or create a new document version only if the caller explicitly asks.
  - Do not dedupe across users.

- Text extraction retry:
  - Reuse the same `UserSourceDocument`.
  - Update extracted text metadata only if the parser version or extraction settings changed, or create a new extraction run referencing the same document.

- Agent extraction retry:
  - Always create a new `ProfileExtractionRun`.
  - Keep old runs for audit.
  - The latest successful run can be the default for UI display, but previous runs remain inspectable.

- Draft ID stability:
  - `draft_id` must be stable within one extraction run.
  - It does not need to be globally unique.
  - Approval requests must include `extraction_run_id + draft_id`.

- `source_item_id` generation:
  - Proposed IDs should be deterministic from document/run context plus item kind/title, for example `doc_<document_short_hash>_project_backend_job_tracker`.
  - The approval service may adjust the final ID if there is a collision.

- Approval retry:
  - If the same `extraction_run_id + draft_id` has already created a `UserProfileItem`, return the existing saved item rather than creating a duplicate.
  - Store approval metadata either in the extraction run JSON or in an approval map to make this lookup reliable.

- Collision with existing profile items:
  - If an existing item has the same `source_item_id` and came from the same extraction approval, treat the operation as idempotent.
  - If an existing item has the same `source_item_id` but is manually curated or from a different source, do not overwrite it.
  - Instead return a conflict requiring explicit merge, update, or save-as-new behavior.
  - If save-as-new is chosen, create a suffixed source item id.

The current `add_profile_item` upserts by `user_id + source_item_id`. That is convenient for manual updates but risky for imports. The document-approval service should perform collision checks before calling it so extracted drafts cannot accidentally overwrite curated evidence.

Final idempotency principle:
- retries should be harmless
- repeated approvals should not duplicate items
- extracted imports should never overwrite curated profile data without an explicit user action

### 3. Focused production-ready test suite

The test suite should prove behavior at the trust boundaries, not every implementation detail.

Parser and document ingestion tests:
- TXT upload extracts normalized readable text.
- Unsupported file type returns a clear 400.
- Oversized file returns a clear 400.
- Empty file or zero extracted text blocks extraction.
- Corrupt/password-protected file maps to a failed document/extraction status.
- Partial extraction with useful text returns warnings and allows review.
- Scanned/image-only PDF blocks for v1 unless OCR is implemented.
- File hash dedupe returns or reuses the existing user document.

Extraction contract tests:
- LLM-off fallback returns a valid `ProfileDocumentExtraction`.
- Agent output with unknown kind is rejected.
- Draft with missing description is rejected.
- Draft without provenance is rejected unless converted to manual.
- `excluded_claims` survive storage.
- `listed_only`, `conflicting`, and `insufficient` support levels are preserved.
- Warnings and unresolved questions are returned to the API response.

Category normalization tests:
- Skill drafts become `ProfileItemKind.SKILL` with skill category, skills, evidence source, and gaps.
- Experience drafts populate employer/title/dates/responsibilities/tools when supported.
- Project drafts populate title/problem/role/tech stack/features/impact when supported.
- Certification drafts require title/issuer/date/url or produce gaps.
- Education and achievement drafts preserve nullable/missing fields as evidence gaps.
- Duplicate skills across documents merge into the safer support level, not the most flattering one.

Approval tests:
- Direct supported draft approval creates a `UserProfileItem`.
- Edited draft approval persists user edits and metadata.
- `listed_only` skill approval saves weak evidence with an evidence gap or conservative evidence source.
- `conflicting` draft is blocked unless explicitly resolved.
- `insufficient` draft is blocked until required fields are added.
- Re-approving the same draft is idempotent.
- Approval does not overwrite an existing manually curated item with the same `source_item_id`.
- Approval transaction rolls back if one selected item fails validation, unless partial success is explicitly supported.

API tests:
- `POST /profiles/{user_id}/source-documents/extract` returns document metadata, extraction run id, draft items, warnings, and unresolved questions.
- `POST /profiles/{user_id}/source-documents/{document_id}/approve` saves selected drafts and returns saved profile items.
- Cross-user document/extraction access is rejected.
- Failed extraction run cannot be approved.

Downstream regression tests:
- Approved extracted project item can be used by existing match/selection/resume workflow.
- Weak/listed-only Kubernetes evidence does not become a strong resume bullet.
- Missing metrics from extracted projects become user improvement suggestions or evidence gaps, not invented metrics.
- Existing `test_keyless_text_to_resume_content_workflow` still passes.

Keyless fallback tests:
- With `ENABLE_LLM=false`, document extraction still returns valid draft schemas.
- Fallback extraction produces conservative support levels.
- Fallback never invents certifications, employers, dates, or metrics.

Validation commands:
- `python -m pytest`
- `ruff check .`
- `ruff format --check .`

The suite should use small fixture files or mocked parser outputs where possible. The goal is to test app behavior, not the internals of `pypdf`, `python-docx`, or `python-pptx`.

## Round 3 Analysis

The last dangerous edge is not the LLM. It is the write path. If approval is implemented as "take client JSON and call `add_profile_item`," the system loses the safety work from the earlier design. Approval must reload stored drafts, validate support levels, enforce provenance, handle edits deliberately, and protect curated profile rows from import overwrite.

The existing `UserProfileItem` unique constraint on `user_id + source_item_id` is both useful and sharp. It prevents duplicates, but the current upsert behavior is too permissive for extracted imports. The import approval layer needs an explicit collision policy before calling the lower-level profile service.

The second major insight is that user edits are not all equal. If the user corrects a date or project title, that is normal review. If the user upgrades a weak extracted claim into a strong one, the system should mark it as manual confirmation or require stronger supporting detail. That distinction protects resume truthfulness later.

The third major insight is that idempotency must be designed across four levels: file upload, text extraction, agent extraction, and approval. Retrying any step should not duplicate profile evidence or erase manual work.

Round 3 decision:
- Add a dedicated approval service between extraction drafts and `add_profile_item`.
- Use stored extraction-run drafts as the source of truth for approval, not client-submitted draft objects.
- Block or downgrade unsafe support levels.
- Make repeated approvals idempotent.
- Never overwrite curated profile items from extracted imports without explicit user intent.
- Test trust boundaries, not parser-library internals.

## Grill Closeout

Final design level: strong enough to implement with low ambiguity. The feature is now framed as a review-first evidence ingestion system, not a generic "resume parser." That framing is the difference between a useful agentic workflow and a profile-pollution machine.

Strongest areas:
- Clear trust boundary: document -> extraction run -> draft -> approved profile item.
- Good preservation of uncertainty through support levels, provenance, warnings, excluded claims, and unresolved questions.
- Correct default architecture: one structured extraction call, deterministic validators, keyless fallback.
- Solid production posture around idempotency, retries, and non-overwrite behavior.

Weakest gaps to watch during implementation:
- Migration strategy is not yet defined. The repo currently uses SQLModel metadata creation, so adding real tables may need a migration decision.
- UI details are not implemented, especially side-by-side source snippets and conflict review.
- File storage cleanup and retention policy are not specified.
- OCR is intentionally out of v1, so scanned resumes will need a clear user-facing fallback.
- Manual override semantics need careful naming so downstream agents know what is source-backed versus user-confirmed.

Next drills:
- Write exact Pydantic schemas for `ProfileDocumentExtraction`, `ExtractedProfileDraft`, `ExtractionProvenance`, and approval requests.
- Design the source-document tables and decide whether migrations are needed now.
- Draft the extraction prompt and deterministic fallback behavior.
- Implement the approval service before route wiring, so the trust boundary is tested directly.

Uncomfortable question to revisit:
- If a user manually confirms a high-value claim that no uploaded document supports, should the resume generator treat it as trusted evidence, weak evidence, or a separate "user asserted" category that requires extra caution?
