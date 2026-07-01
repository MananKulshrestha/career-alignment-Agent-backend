# Resume Workflow Grill Memory

Purpose: durable memory for the four-round grill on the ideal implementation state for the resume workflow changes.

Project context captured on 2026-07-01:
- Python backend for job ingestion, matching, profile evidence, selection, resume writing, and LaTeX/PDF generation.
- Relevant files inspected:
  - `app/services/prompts.py`
  - `app/services/agents.py`
  - `app/services/scraper.py`
  - `app/services/template_builder.py`
  - `app/services/latex.py`
  - `app/schemas/profile.py`
  - `app/schemas/resume.py`
  - `app/schemas/selection.py`
  - `app/services/profile_service.py`
  - `tests/test_template_builder.py`
  - `tests/test_latex.py`
  - `tests/test_keyless_workflow.py`
  - `tests/test_contracts.py`
- Current implementation notes:
  - Resume prompts are short, mostly rule lists, and do not include positive/negative examples.
  - Web scraping uses a custom `HTMLParser` subclass; `beautifulsoup4` is not currently in `pyproject.toml`.
  - Template planning currently emits generic resume bullet placeholders, with two bullets for both `experience` and `projects`.
  - LaTeX generation uses a simple dynamic ATS template with hardcoded candidate/contact header and section rendering.
  - Profile evidence uses one generic `ProfileItemPayload` shape across projects, experience, education, skills, and other kinds.
- Attached Jake's Resume template was read from the Codex attachment. Important traits to preserve as defaults:
  - `letterpaper,11pt` article document.
  - `fullpage`, `titlesec`, `enumitem`, `hyperref`, `fancyhdr`, `tabularx`, and `glyphtounicode` style setup.
  - ATS-friendly `\pdfgentounicode=1`.
  - Jake-style custom commands: `\resumeItem`, `\resumeSubheading`, `\resumeProjectHeading`, `\resumeSubHeadingListStart`, `\resumeItemListStart`, and related list commands.
  - Centered contact heading and section blocks for Education, Experience, Projects, Technical Skills.

Requested implementation directions:
1. Follow Jake's Resume as the default resume template while keeping it dynamically changeable through the first model output.
2. Improve agentic workflow prompts with important context, examples of correct outputs, edge cases, and non-edge cases.
3. Consider Beautiful Soup for cleaner job-page web scraping.
4. Make evidence collection less rigid and ask different evidence questions for projects, experience, and other profile sections.

## Round 1 Questions

1. What exactly should the first model be allowed to decide about the resume template, and what must remain fixed as Jake's Resume defaults?
2. What should count as a "correct" prompt output for the selection and resume-writing agents when evidence is strong, adjacent, missing, or risky?
3. For profile evidence collection, what should be different between a project evidence item and an experience evidence item, both in fields asked from the user and in how the resume writer may use them?

## Round 1 Answers

1. Use the attached Jake's Resume template as the default. Keep the number of projects, experiences, education entries, achievements, skills, and certifications variable. The first model should decide those counts. A deterministic tool call should receive those counts and generate the template/placeholders. The second model should receive that generated template and fill in content.
2. Prompt examples should be designed to improve the user's odds of getting selected while staying within truthfulness constraints.
3. Evidence-question differences are simple enough for Codex to decide.

## Round 1 Feedback

1. Strong direction. The clean architecture is: model 1 outputs a structured template plan, a deterministic builder turns that into Jake-style LaTeX placeholders, and model 2 fills only those placeholders. The remaining gap is exactly what model 1 may control. Recommended: allow `page_target`, `section_order`, counts per section, selected source IDs, and bullet counts per entry; keep Jake-style macros, margins, escaping rules, and raw LaTeX generation fixed in code.
2. Direction is right but too broad if left as "make the user more likely selected." The prompt examples must define "better" as ATS/job alignment, sharper action/result phrasing, keyword coverage, and stronger evidence selection without inventing employers, tools, dates, metrics, certifications, or responsibilities.
3. Delegation accepted. Implementation should split evidence collection by kind:
   - Projects: problem, target users, role, tech stack actually used, architecture/features, measurable impact, repo/demo URL, dates, collaboration, constraints/tradeoffs.
   - Experience: employer, title, location, dates, employment type, team/scope, responsibilities, tools actually used on the job, measurable outcomes, promotions/ownership, cross-functional work.
   - Education: school, degree, dates, coursework, GPA if useful, honors.
   - Skills: categorized skill groups and proficiency/evidence source.
   - Achievements/certifications: issuer/event, date, criteria, ranking/score if supported, URL.
4. Key implementation decision from Round 1: model 2 should never see a vague instruction to "make a resume"; it should receive concrete placeholder IDs generated from model 1's approved structure.

## Round 2 Questions

1. What should the first model do when the job asks for five major requirements but the user's profile only has strong evidence for two, adjacent evidence for one, and no evidence for two?
2. What exact fields should the template-builder tool accept so it can generate Jake-style placeholders without allowing the model to emit unsafe or malformed LaTeX?
3. Beautiful Soup will make text extraction cleaner, but job pages often include nav bars, cookie banners, repeated footers, hidden JSON, and "apply now" clutter. What extraction behavior should be considered good enough for the downstream job-spec model?

## Round 2 Answers

1. Put whatever evidence is available into the resume and give comments to the user about how to improve the resume.
2. Codex should research and decide the best template-builder tool interface.
3. The LLM should be capable enough to extract useful information from cleaned page text; GPT-5 nano is considered good enough for this extraction stage.

## Round 2 Feedback

1. Good user-centered instinct, but "put whatever is available" needs a guardrail. The first model should select the strongest relevant evidence that fits the target page length, not dump every available item. Missing and weak areas should become explicit improvement comments/questions for the user, separate from resume content.
2. Accepted. Recommended best approach:
   - Model 1 outputs a structured `ResumeStructurePlan`, not LaTeX.
   - Fields should include `template_family`, `page_target`, `section_order`, `selected_item_ids`, `entry_counts_by_section`, `bullet_counts_by_source_item_id`, `target_keywords_covered`, `missing_requirements`, and `user_improvement_suggestions`.
   - A deterministic builder receives that plan and creates Jake-style placeholders.
   - The builder should not accept raw LaTeX, arbitrary commands, freeform margins, unbounded counts, or source IDs not present in the profile.
3. Mostly reasonable. Beautiful Soup should focus on producing cleaner readable text, not perfect semantic extraction. The downstream model can tolerate some page clutter if the scraper removes scripts/styles/nav/footer noise, keeps headings/list structure, preserves enough job text, and fails clearly when readable text is too short.

Implementation decisions from Round 2:
- User-facing resume improvement comments should be first-class output from the selection/structure stage.
- Missing evidence should produce targeted evidence questions, not fake bullet content.
- Scraper acceptance bar: clean enough for LLM extraction, not perfect handcrafted parsing.
- GPT-5 nano can be used for job extraction if validation and verification remain in place.

## Round 3 Questions

1. If model 1 decides the resume should include 2 projects, 1 experience, 1 education entry, technical skills, and no certifications, what should happen if model 2 tries to add a third project or invent a certification?
2. What kinds of "resume improvement comments" should be shown to the user immediately, and which should be kept internal for the model workflow?
3. For evidence collection, should the backend store only the final user-entered payload, or should it also store unanswered/missing evidence questions per item, like "metric missing," "date missing," or "project URL missing"?

## Round 3 Answers

1. Strict guardrails should prevent model 2 from adding sections, entries, certifications, or content outside what model 1 specified.
2. Codex should decide the split between immediate user-facing comments and internal workflow notes.
3. The backend should store missing/unanswered values too, using `NULL` values where evidence is absent.

## Round 3 Feedback

1. Correct. This should be enforced in validation, not only prompt language. Model 2 should only return values for known placeholder IDs. Extra placeholders, source IDs outside the approved selection, added sections, or invented certifications should fail validation and trigger regeneration or a blocked workflow.
2. Accepted. Recommended split:
   - Show users: missing metrics, unclear dates, missing links, weak job-keyword coverage, unsupported requirements, unclear ownership, vague impact, and high-value questions that would improve the resume.
   - Keep internal: model confidence bookkeeping, token-budget choices, prompt-routing notes, raw scraper noise, and low-level validation heuristics unless they affect user action.
3. Good, with one correction: store missingness deliberately, not as random sparse payload chaos. Best approach is nullable typed fields plus a structured `evidence_questions` or `evidence_gaps` list with field name, prompt/question, status, and optional answer. This lets the UI ask better follow-ups later and lets the model distinguish "unknown" from "not applicable."

Implementation decisions from Round 3:
- Model 2 output must be schema-validated against the exact template/placeholders generated after model 1.
- User improvement comments are part of model 1/selection output, but resume content remains only approved placeholder text.
- Evidence storage should preserve explicit nulls and missing evidence questions so the system can revisit them.

## Round 4 Questions

1. What should the acceptance tests prove for the new Jake-style dynamic template workflow from model 1 structure plan to model 2 filled content?
2. When the user has weak evidence for a high-value job requirement, should the system prefer a weaker honest bullet, a user-facing evidence question, or both? Defend the rule.
3. What should happen when Beautiful Soup extraction returns long but noisy text versus short but clean text?

## Round 4 Answers

1. Codex should research and decide the acceptance-test strategy.
2. Codex should research and decide the weak-evidence rule.
3. LLM models should be capable enough that long/noisy versus short/clean scraped text is not a major issue.

## Round 4 Feedback

1. Accepted. Recommended acceptance tests:
   - A `ResumeStructurePlan` with variable counts generates exactly the expected Jake-style placeholders for education, experience, projects, achievements, technical skills, and certifications.
   - The generated `TemplatePlan` uses `template_family="jakes_resume"` and contains no model-authored raw LaTeX.
   - Model 2 content validates only when every placeholder is filled exactly once and every `source_item_id` is approved by model 1.
   - Extra model 2 placeholders, invented certifications, unapproved source IDs, and omitted placeholders are rejected.
   - The compiled/fallback LaTeX contains Jake-style commands/sections and escapes special characters.
   - User improvement comments survive the selection/approval flow and are separate from resume bullets.
   - Evidence gaps with `NULL` values remain stored and can drive follow-up questions.
2. Accepted. Recommended rule: use both when there is relevant but weak evidence. Put an honest weaker bullet only if it improves alignment without overstating the claim; also show a user-facing evidence question that would make the bullet stronger. If the evidence is missing, do not write a bullet pretending support exists; show the gap/question instead.
3. Partly accepted, with a guardrail. The LLM can tolerate noise, but the scraper should still remove obvious non-content and record extraction quality. Long/noisy text should be passed through with low/medium extraction confidence if enough job-like content remains. Short/clean text should pass only if it meets a minimum useful length and contains role/company/responsibility/qualification signals; otherwise block or request pasted text.

External references checked for Round 4:
- Beautiful Soup official docs: `get_text()` extracts human-readable text; `decompose()` removes tags and contents from the parse tree.
- Pydantic official docs: `extra="forbid"` rejects unknown fields; model validators support whole-model validation.

Implementation decisions from Round 4:
- Treat the scraper as best-effort cleanup, not the source of truth.
- Treat schema validation as the hard safety layer for model 1 and model 2.
- Acceptance tests should prove the full contract: structure plan -> Jake placeholders -> filled content -> validation -> LaTeX/PDF artifact.

## Grill Closeout

Current design level: strong product direction, medium implementation specificity. The best decisions were strict model 2 guardrails, dynamic model 1 structure, Jake's Resume as a deterministic renderer default, and storing missing evidence explicitly.

Strongest areas:
- Clear separation between structure selection and final writing.
- Good instinct that missing evidence should become user improvement guidance.
- Correct trust boundary: model 2 follows model 1, not its own improvisation.

Weakest gaps:
- Acceptance criteria were delegated to Codex; now filled in above.
- "LLM is capable enough" should not replace extraction-quality checks.
- User-facing guidance needs structured severity/actionability so it does not become vague advice.

Next drills:
- Define the exact `ResumeStructurePlan` schema.
- Define evidence-gap objects for projects, experience, education, skills, achievements, and certifications.
- Define regeneration/blocking behavior when validation fails.

Uncomfortable question to revisit:
- If the truthful resume is weak for a target job, should the system optimize for the best honest application anyway, or explicitly tell the user not to apply until they add stronger evidence?
