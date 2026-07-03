# User Abstract Context Grill Memory

Purpose: durable memory for a three-round grill on the technical plan for adding persistent user abstract/context to the career alignment backend.

Session focus:
- Add an option for users to provide a personal abstract/context describing specialization, goals, preferred resume strictness, and useful positioning guidance.
- Keep context useful for matching, selection, and writing without letting freeform text become unsupported resume evidence.
- Preserve the existing source-backed resume contract, deterministic fallbacks, and backward-compatible profile APIs.

Current recommended technical direction:
- Add a separate `UserProfileContext` table keyed by `user_id`, rather than storing the abstract as a normal evidence item.
- Add strict schemas for abstract, specializations, career goals, target roles, strictness, tone preferences, and avoid-claims.
- Include context in `UserProfileRead` and thread it into match, selection, and resume-writing agent calls.
- Update prompts so context guides emphasis, ordering, tone, and claim strength, but never proves skills, employers, metrics, credentials, dates, or projects.
- Keep source-ID validation unchanged so resume content still cites approved evidence items.
- Do not automatically generate a resume summary from the abstract in the first implementation.

## Round 1 Questions

1. Defend the decision to store the user abstract in a separate `UserProfileContext` table instead of as a normal `UserProfileItem`. What specific bugs or product failures does this avoid?
2. In this system, what is the exact difference between "user context" and "resume evidence"? Give two examples where the abstract should influence behavior and two examples where it must not.
3. If a user writes in the abstract, "I specialize in Kubernetes and distributed systems," but their profile evidence only contains a FastAPI/PostgreSQL project, how should matching, selection, and resume writing each treat Kubernetes?

## Round 1 Answers

1. The abstract should live in a separate `UserProfileContext` table because it has different semantics from a normal `UserProfileItem`.

   A profile item is source-backed evidence: a project, job, education record, skill group, achievement, certification, or research note that can be selected into a resume plan and cited by `source_item_id`. The existing system treats selected profile items as resume claim sources. If the abstract becomes a normal profile item, several bugs become likely:

   - The selection agent may select the abstract as if it were proof of a skill, project, or experience.
   - The template builder may try to turn the abstract into resume placeholders, especially through the existing `summary` section support.
   - Resume validation may allow model output to cite the abstract's `source_item_id`, creating a loophole where broad self-description becomes support for concrete claims.
   - Matching may over-score a job because a keyword appears in the abstract, even when no evidence item proves it.
   - User experience gets messy: an abstract is one per user and cross-job, while evidence items are many per user and often resume-selectable.
   - Updates become ambiguous: replacing a user's career goal should not behave like adding/deactivating a project item.

   A separate context table makes the contract explicit: context is user-level steering data, not resume evidence. It also gives us simpler one-row-per-user upsert behavior, clean API naming, independent validation limits, and a safer prompt payload.

2. User context is guidance about how to interpret and present the user's evidence. Resume evidence is the factual support for claims that can appear in a resume.

   The abstract should influence behavior in these ways:

   - It can influence ranking and emphasis. If the user says their goal is backend platform engineering, the system can prefer backend/API/database projects over a generic frontend project when both are truthful and relevant.
   - It can influence style and strictness. If `resume_strictness` is `conservative`, the writer should use narrower wording, preserve uncertainty, and avoid stretching adjacent evidence.

   The abstract must not influence behavior in these ways:

   - It must not prove a job requirement by itself. If the job asks for Kubernetes and only the abstract mentions Kubernetes, matching cannot mark Kubernetes as supported.
   - It must not create resume content that cites no approved evidence. The writer cannot invent "deployed Kubernetes clusters" or "specialized in distributed systems" unless selected profile items actually support that wording.

   The practical rule is: context can choose among supported truths and control how strongly they are phrased; evidence determines what truths are available.

3. If the abstract says "I specialize in Kubernetes and distributed systems" but profile evidence only contains a FastAPI/PostgreSQL project, each stage should treat Kubernetes differently:

   - Matching: Kubernetes should not be counted as supported evidence. It may be treated as a self-reported interest or unverified context signal. If a job requires Kubernetes, the match output should list it as missing or `needs_user_input`, with a suggestion asking the user to add a project, work example, certification, or concrete Kubernetes detail.
   - Selection: the selection plan should not select the abstract as Kubernetes evidence. It may select the FastAPI/PostgreSQL project if backend systems evidence is adjacent or useful, but it must preserve a missing requirement such as "Kubernetes not supported by current profile evidence." It should not hide the gap just because the abstract contains the word.
   - Resume writing: the writer must not claim Kubernetes. It can write supported backend wording like "Built FastAPI services with PostgreSQL persistence" and, if appropriate, use adjacent distributed-systems-adjacent language only if the project evidence supports it. It should not write "Kubernetes," "distributed systems specialist," or "cloud-native orchestration" unless those facts are in approved evidence items.

   The final behavior should be helpful but strict: the system can say, "Your context says Kubernetes matters, but your current evidence does not prove it yet."

## Round 1 Feedback

The central insight is that the abstract is a control plane, not a data source for claims. That distinction should drive storage, APIs, prompts, validation, tests, and fallback logic.

Technical consequences:

- `UserProfileContext` should not have `source_item_id` and should not participate in `selected_item_ids`.
- `validate_selection_source_ids` and `validate_resume_content` should remain evidence-only.
- Agent payloads can include `user_context`, but prompt rules must clearly say it cannot satisfy requirements or support resume claims.
- Deterministic fallback scoring should build `profile_text` only from evidence items, not from `context.abstract`.
- `avoid_claims` should behave like hard negative guidance. If the user says to avoid leadership claims, the writer should not produce leadership framing even if adjacent wording would sound stronger.
- `resume_strictness` should map to claim style, not truthfulness level. Even `assertive` cannot invent facts.

Implementation risk to watch:

- The existing code already supports a `summary` section and `ContentType.SUMMARY`. That is useful later, but dangerous in the first version if the abstract is allowed to become a summary source. First implementation should avoid automatic abstract-to-summary generation unless a separate validation rule is designed.

Recommended invariant:

- Context can influence selection among evidence-backed options. It cannot become the evidence-backed option.

## Round 2 Questions

1. Design the exact Pydantic schemas for `UserProfileContext`. Which fields should be required, optional, length-limited, enum-limited, and list-size-limited? Explain the validation rules and why each limit exists.
2. Walk through the service flow after implementation: a user saves context, ingests a job, gets a match, creates a tailoring session, approves selection, and generates resume content. At each step, name which function should read or pass `profile.context`, and name one thing that function must not do with it.
3. Suppose a bug causes `deterministic_match` to include `context.abstract` in the same text blob as evidence item descriptions. What incorrect outcomes could this produce, which tests would catch it, and what code-level boundary would prevent it from recurring?

## Round 2 Answers

1. The context schema should be strict, bounded, and optional by default. The user should be able to provide only an abstract, only strictness, only target roles, or any combination.

   Recommended schema shape:

   ```python
   class ResumeStrictness(StrEnum):
       CONSERVATIVE = "conservative"
       BALANCED = "balanced"
       ASSERTIVE = "assertive"


   class UserProfileContextBase(BaseModel):
       model_config = ConfigDict(extra="forbid")

       abstract: str | None = Field(default=None, max_length=6000)
       specializations: list[str] = Field(default_factory=list, max_length=20)
       career_goals: list[str] = Field(default_factory=list, max_length=10)
       target_roles: list[str] = Field(default_factory=list, max_length=20)
       resume_strictness: ResumeStrictness = ResumeStrictness.BALANCED
       tone_preferences: list[str] = Field(default_factory=list, max_length=10)
       avoid_claims: list[str] = Field(default_factory=list, max_length=30)


   class UserProfileContextUpsert(UserProfileContextBase):
       pass


   class UserProfileContextRead(UserProfileContextBase):
       id: str
       user_id: str
   ```

   Validation rules:

   - `abstract` is optional because a user may only want to configure strictness or target roles. If provided, trim it, normalize whitespace, reject blank strings, and cap it around 4,000-6,000 characters.
   - `specializations` should be a short list of concrete focus areas, capped around 20 items and about 80-120 characters per item.
   - `career_goals` should be capped lower, around 10 items, because goals are steering signals, not a biography.
   - `target_roles` should be capped around 20 items so matching can use them without prompt bloat.
   - `resume_strictness` must be enum-limited. Freeform strictness text invites inconsistent behavior and prompt ambiguity.
   - `tone_preferences` should be capped around 10 items. It can guide style, but should not dominate evidence.
   - `avoid_claims` should be capped around 30 items and treated as hard negative guidance. It exists to prevent unwanted framing such as "leadership," "AI expert," or "full-stack" when the user does not want those claims.
   - All list entries should be stripped, blank entries rejected, duplicates removed case-insensitively, and per-item length-limited.
   - `extra="forbid"` matters because silently accepting fields such as `has_kubernetes=true` or `verified_skills=["AWS"]` would blur the context/evidence boundary.

   The key schema principle is: broad enough for user expression, narrow enough that downstream code knows what each field means.

2. The service flow should read context through `get_profile(...)` and pass it separately from profile evidence.

   Save context:

   - Route: `PUT /api/v1/profiles/{user_id}/context`.
   - Function: `upsert_profile_context(session, user_id, request)`.
   - It should create or update one `UserProfileContext` row for the user.
   - It must not create a `UserProfileItem`, assign a `source_item_id`, or add evidence gaps.

   Ingest job and match:

   - `ingest_job(...)` already calls `match_job_for_user(...)` after job extraction/storage.
   - `match_job_for_user(...)` should call `get_profile(session, user_id=request.user_id, preferences=request.preferences)`.
   - `get_profile(...)` should return `UserProfileRead(items=[...], context=...)`.
   - `agent_gateway.analyze_match(...)` should receive `profile_items=profile.items`, `preferences=request.preferences`, and `user_context=profile.context`.
   - It must not merge context text into the evidence text used to decide supported requirements.

   Create tailoring session:

   - `create_tailoring_session(...)` should call `get_profile(...)`.
   - It should pass `profile.items` and `profile.context` into `agent_gateway.create_selection_plan(...)`.
   - It must not allow `selection_plan.selected_item_ids` to contain any context identifier, because context has no valid evidence source ID.

   Approve selection:

   - `approve_selection(...)` should keep using `get_profile(...)` and `validate_selection_source_ids(...)` against `{item.source_item_id for item in profile.items}` only.
   - `build_template_plan(...)` should receive evidence items only.
   - It must not let context remove missing requirements from the approved plan.

   Generate resume content:

   - `generate_resume_content(...)` should fetch `profile = get_profile(...)`.
   - It should compute `approved_items` from selected evidence IDs only.
   - It should pass `approved_profile_items=approved_items` and `user_context=profile.context` to `agent_gateway.write_resume_content(...)`.
   - It must not allow context to create extra placeholders, unapproved source IDs, or content outside `template_plan`.

   Compile:

   - `compile_tailored_resume(...)` should continue passing only approved evidence items to `compile_resume(...)`.
   - It should not pass context to the renderer in the first implementation, because rendering should be a deterministic output of the approved template and approved content.

   The key flow principle is: context travels beside evidence, never inside evidence.

3. If `deterministic_match` accidentally includes `context.abstract` in the same text blob as evidence descriptions, it can produce several wrong outcomes.

   Incorrect outcomes:

   - A job requiring Kubernetes may receive a higher match score because "Kubernetes" appears in the abstract.
   - `missing_requirements` may omit Kubernetes even though no profile item proves it.
   - The match verdict may move from rejected/weak to good/strong for the wrong reason.
   - `short_explanation` may say "Matched 1 of 1 required skill signals," which is false under the evidence model.
   - Downstream selection may start from a misleading fit assessment, even if later validation prevents direct resume fabrication.

   Tests that should catch it:

   - A unit test for `deterministic_match(...)`: job requires Kubernetes, evidence item only mentions FastAPI/PostgreSQL, context abstract mentions Kubernetes. Expected result: Kubernetes remains missing, score does not treat it as covered.
   - An end-to-end keyless workflow test with context present: context-only skills should not disappear from missing requirements after job ingest/match.
   - A regression test around `avoid_claims`: context should be able to add negative guidance, but not positive evidence.

   Code-level boundary:

   - Use separate helpers such as `_profile_evidence_text(profile_items)` and `_context_guidance_text(user_context)`.
   - Compute covered skills only from `_profile_evidence_text(...)`.
   - Keep `deterministic_match(job_spec, profile_items, preferences, user_context=None)` parameters separate and avoid passing a whole `UserProfileRead` object into fallback scoring.
   - Name variables explicitly: `evidence_text`, `context_guidance`, `context_negative_guidance`.
   - If context is used for scoring at all, restrict it to preference-like adjustments or explanations, never requirement coverage.

   The best prevention is not a clever regex. It is a data boundary that makes the wrong concatenation feel obviously wrong in code.

## Round 2 Feedback

Round 2 settles the production contract:

- Context is optional and bounded. The feature should not require a long abstract, because many users may only want "be conservative" or "target backend roles."
- `resume_strictness` must be an enum. Otherwise the writer has to interpret vague user language such as "make it strong but not too much," which is exactly where unsupported claims creep in.
- `avoid_claims` is not a preference in the soft sense. It should act as hard negative guidance unless the product later adds a deliberate override.
- The service flow should use `get_profile(...)` as the one profile aggregation point, but all downstream calls must keep `profile.items` and `profile.context` separate.
- `build_template_plan(...)`, `validate_selection_source_ids(...)`, `validate_resume_content(...)`, and `compile_resume(...)` should remain evidence-only in the first version.

Subtle weakness still unresolved:

- Current `validate_resume_content(...)` proves placeholder/source-ID discipline, but it does not semantically prove that every word in a bullet is supported by the cited item. A model could cite `project_fastapi` and still write "Deployed Kubernetes workloads" if prompts fail. This feature makes that risk more visible because context may contain tempting unsupported terms.

Implementation invariant after Round 2:

- Requirement coverage must be computed from evidence only.
- Context may influence priority and phrasing only after evidence has established what can truthfully be said.

## Round 3 Questions

1. The current project uses SQLModel `create_all(...)` and has no explicit migration framework in the inspected files. How should the `UserProfileContext` table be introduced safely for local SQLite and production Supabase/Postgres without risking existing user data?
2. `validate_resume_content(...)` checks placeholder IDs, word limits, required fields, and source IDs, but it does not semantically verify that a bullet's claims are supported by the cited profile item. How should the implementation reduce or catch context-induced unsupported claims such as "Kubernetes" appearing in a bullet sourced to a FastAPI project?
3. Should `avoid_claims` be enforced only through prompts, through deterministic validation, or through both? Give a concrete rule for what happens if `avoid_claims=["leadership"]` and the model writes "Led a team..." in a generated bullet.

## Round 3 Answers

1. The `UserProfileContext` table should be introduced as a new additive table, not by changing the semantics of `user_profile_items`.

   Local SQLite:

   - Adding the SQLModel class is enough for fresh local databases because `create_db_and_tables()` calls `SQLModel.metadata.create_all(engine)`.
   - For an existing local SQLite database, `create_all(...)` should create the new table if it does not exist, without rewriting existing tables.
   - Local tests should include `SQLModel.metadata.create_all(engine)` and verify that a user with no context still reads correctly.

   Production Supabase/Postgres:

   - Do not rely on app startup `create_all(...)` as the production migration strategy. It is fine as a local/dev convenience, but production schema changes should be explicit and reviewed.
   - Create an idempotent SQL migration before deploying code that reads/writes the table:

     ```sql
     create table if not exists user_profile_contexts (
       id uuid primary key,
       user_id uuid not null unique,
       abstract text,
       specializations json not null default '[]',
       career_goals json not null default '[]',
       target_roles json not null default '[]',
       resume_strictness text not null default 'balanced',
       tone_preferences json not null default '[]',
       avoid_claims json not null default '[]',
       created_at timestamptz not null,
       updated_at timestamptz not null
     );

     create index if not exists ix_user_profile_contexts_user_id
       on user_profile_contexts (user_id);

     alter table user_profile_contexts
       add constraint chk_user_profile_contexts_resume_strictness
       check (resume_strictness in ('conservative', 'balanced', 'assertive'));
     ```

   - If the project later formalizes migrations with Alembic or Supabase CLI migrations, this table creation should be the first migration.
   - Deploy order should be migration first, application code second. Otherwise `GET /profiles/{user_id}` could fail when it attempts to read a table that production does not have yet.
   - Backward compatibility requirement: users with no row in `user_profile_contexts` should still receive `context=None`, and all existing profile item flows should continue.
   - Rollback is simple because the table is additive: disable/hide context endpoints in code before dropping the table. Do not drop it casually once users may have stored context.

   The safety principle is: additive schema, nullable/empty defaults, migration before code path dependency, no mutation of existing evidence tables.

2. The implementation cannot fully prove semantic truthfulness with the current `validate_resume_content(...)`, but it can substantially reduce and catch context-induced unsupported claims through layered controls.

   First layer: prompt and payload design.

   - The writing prompt must state that `user_context` guides style/emphasis only.
   - The writing prompt should say context-only terms may not appear as factual claims unless present in approved evidence.
   - The model should receive `approved_profile_items` separately from `user_context`, not a merged blob.

   Second layer: deterministic suspicious-claim guard.

   - Add a validation helper after model output, before committing `resume_content`, such as `validate_context_terms_not_used_as_evidence(...)`.
   - Extract salient terms from `user_context` that are not present in the approved evidence text. At minimum, use `specializations`, `target_roles`, and meaningful tokens/phrases from `avoid_claims`; later this can be expanded with a controlled keyword extractor.
   - If a context-only term appears in generated resume text and does not appear in the cited profile item's payload, flag it.
   - For the Kubernetes example: if context mentions Kubernetes, approved evidence text does not, and a placeholder sourced to `project_fastapi` contains "Kubernetes", block generation with a `BlockedWorkflowError` or trigger regeneration depending on the system's retry policy.

   Third layer: source-local checking.

   - For each `PlaceholderValue`, inspect the cited source item or items.
   - Terms that are high-risk claims, such as tools, cloud platforms, certifications, employers, metrics, leadership, management, degrees, and dates, should be allowed only if present in the cited evidence or in another approved cited source.
   - This should start conservative and focused on obvious context leakage, rather than pretending to solve all semantic validation at once.

   Fourth layer: tests.

   - Test that context-only "Kubernetes" cannot appear in generated resume content sourced to a FastAPI/PostgreSQL project.
   - Test that if the approved profile item itself contains Kubernetes, the same word is allowed.
   - Test that context can still influence phrasing when it does not introduce unsupported concrete claims.
   - Test deterministic fallback separately because it bypasses the LLM and is easier to accidentally over-trust.

   The realistic standard is not perfect natural-language proof. The standard is a strong guard against the most likely leakage path introduced by this feature: context-only concrete claims appearing in evidence-backed resume bullets.

3. `avoid_claims` should be enforced through both prompts and deterministic validation.

   Prompt-only enforcement is not enough because model output can drift. Deterministic validation alone is also not enough because it can only catch known terms/patterns and may be too blunt. The two layers should work together:

   - Prompt layer: tell the model that `avoid_claims` are hard negative guidance. It should choose alternative wording rather than using those claims.
   - Validation layer: scan generated placeholder text for blocked claim terms or close variants.

   Concrete rule for `avoid_claims=["leadership"]`:

   - If the model writes "Led a team...", "Leadership across...", "Owned team direction...", or similar leadership framing, generation should be rejected or regenerated.
   - The error should identify the blocked claim and placeholder, for example: `resume_content uses avoided claim 'leadership' in projects_project_1_bullet_2`.
   - If a user truly wants to allow leadership later, they should remove that avoid claim or explicitly change the context. The default should respect the user's negative guidance.

   Implementation detail:

   - Start with exact and simple morphological matching: `lead`, `led`, `leading`, `leadership`, maybe word-boundary regexes for each avoid term plus a small synonym map for common terms.
   - Avoid overblocking substrings. For example, "pleaded" should not match "lead".
   - Apply validation to generated resume text and potentially selection reasons/user-facing suggestions if those are shown to the user.
   - Keep warnings/errors actionable, because the user may need to know which preference caused the wording to be blocked.

   The product rule is: positive context is soft steering; `avoid_claims` is a hard brake.

## Round 3 Feedback

Round 3 closes the main production gaps:

- Migration risk is operational, not just code-level. Adding a SQLModel class is not a production migration plan by itself.
- The safest first version is additive: a new table, one row per user, no changes to evidence table semantics, and all existing flows working when context is absent.
- Semantic validation cannot be perfect, but the feature needs targeted leakage guards because context introduces high-value unsupported words directly into the model prompt.
- `avoid_claims` should be treated differently from tone preferences. Tone preferences guide style; avoid claims forbid certain framing.
- The model should not be trusted to enforce negative guidance by itself.

Final implementation invariants:

- Context table exists separately from evidence items.
- Requirement coverage is evidence-only.
- Resume placeholders cite approved evidence-only source IDs.
- Context-only concrete claims cannot appear in generated resume text unless independently supported by approved evidence.
- Avoided claims block or regenerate output when violated.

## Grill Closeout

Current design level: strong. The plan has moved from "add a user abstract" to a production-ready contract with clear data boundaries, migration strategy, and validation pressure points.

Strongest areas:

- Clear separation of context from evidence.
- Correct refusal to let freeform abstract text satisfy job requirements.
- Good service-flow boundary: `profile.items` and `profile.context` travel together but remain semantically separate.
- Strong instinct to keep `validate_selection_source_ids` and `validate_resume_content` evidence-only.

Weakest remaining gaps:

- Full semantic claim validation remains hard. The recommended first version catches obvious context leakage and avoided claims, but it will not prove every sentence is fully supported.
- Production migration tooling is still informal. The repo should eventually adopt a real migration workflow if Supabase/Postgres production data matters.
- Summary-section behavior is intentionally deferred. That is safe, but the product will likely want it soon, and it needs its own source/validation rule.

Next drills:

- Draft the exact `UserProfileContext` SQLModel and Pydantic schemas.
- Write the context leakage tests before implementation.
- Define the first version of the avoided-claim validator.
- Decide whether context should affect match score, explanation only, or both.

Uncomfortable question to revisit:

- If a user's abstract strongly says they want to be framed as something their evidence does not yet support, should the product quietly produce the best honest resume, or explicitly tell them the positioning is currently unsupported?
