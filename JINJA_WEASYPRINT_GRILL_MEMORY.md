# Jinja2 + WeasyPrint Migration Grill Memory

Purpose: durable memory for the three-round grill on migrating resume rendering from LaTeX/raw-PDF fallback to a Jinja2 HTML template plus WeasyPrint PDF pipeline.

Project context:
- Current renderer lives in `app/services/latex.py`.
- Current compile path writes `resume.tex`, tries `settings.latex_engine`, and falls back to a custom raw PDF writer.
- Target architecture keeps `resume.tex` only for archival/debugging, writes `resume.html`, and renders `resume.pdf` through WeasyPrint.
- Jake's Resume visual target: centered large name, compact contact row, small-caps section headings with horizontal rules, dense serif typography, right-aligned dates/location/links, tight bullets, ATS-readable selectable text.
- Main migration files expected: `pyproject.toml`, `app/services/html_renderer.py`, `app/templates/jakes_resume.html.j2`, `app/templates/jakes_resume.css`, `app/services/latex.py`, `app/services/tailoring.py`, `app/schemas/resume.py`, `app/services/prompts.py`, and rendering tests.

## Jinja Migration Round 1 Questions

1. In the new architecture, which module should own each responsibility: placeholder-to-section grouping, HTML template rendering, PDF generation, and archival `.tex` generation?
2. What should the structured context passed into `jakes_resume.html.j2` look like, and why is that safer than letting the template consume raw placeholders directly?
3. If the PDF is now produced only by WeasyPrint, what exactly should happen to `settings.latex_engine`, `latex_compile_timeout_seconds`, `CompileRun.compiler`, and the old fallback/raw-PDF code?

## Jinja Migration Round 1 Answers

1. `app/services/html_renderer.py` should own the new compile pipeline. It should group placeholders into sections and entries, render Jinja HTML, call WeasyPrint, write `resume.html`, and return `CompileResult`. `app/services/latex.py` should keep only archival `.tex` generation through `assemble_latex()` and `escape_latex()`. The Jinja template should only render an already-structured context; it should not understand placeholder IDs or profile model internals.
2. The template context should be a plain structured dictionary: top-level candidate/contact data, `section_order`, and a `sections` mapping. Each section should expose exactly what the template needs, such as `entries`, `skills`, `summary_items`, `title`, `organization`, `location`, `dates`, `tech_stack`, `links`, and `bullets`. This is safer because the transformation layer can validate grouping, skip empty content, normalize URLs, preserve section order, and keep template logic dumb. Raw placeholders would force the template to infer content types and source relationships, making bugs and malformed resumes much more likely.
3. `settings.latex_engine` and `latex_compile_timeout_seconds` should become unused legacy config for now, not part of the rendering path. `CompileRun.compiler` should record something like `weasyprint` instead of `pdflatex`. The old `compile_resume()`, `render_fallback_pdf()`, `_JakeFallbackPdfBuilder`, raw PDF byte writer, and PDF drawing helpers should be removed from `latex.py`. If WeasyPrint fails, compilation should fail clearly with diagnostic output; it should not fall back to LaTeX or raw PDF.

## Jinja Migration Round 1 Feedback

1. Correct ownership split. The important boundary is that `html_renderer.py` owns runtime rendering, while `latex.py` becomes archival-only. Keep the archival call optional only in code organization, not in product behavior unless the team later decides to drop `.tex`.
2. Correct context shape. The strongest part is keeping source-model and placeholder mechanics outside the template. The missing implementation detail to remember is autoescaping: Jinja should escape text by default, while URL values should still be normalized/validated before becoming `href` attributes.
3. Correct migration stance. The production detail is metadata: database and API consumers may still see `tex_path`, so keep it populated; but the compiler label and README must stop implying LaTeX is required.

Key implementation decisions from Round 1:
- `html_renderer.compile_resume()` is the new public entry point used by tailoring.
- `latex.py` remains only for `resume.tex` archival/debug output.
- Jinja receives a structured resume context, not raw placeholders.
- WeasyPrint failure is a render failure, not a trigger for LaTeX or raw-PDF fallback.

## Jinja Migration Round 2 Questions

1. Design the exact `build_template_context()` behavior for these sections: `education`, `experience`, `projects`, `technical_skills`, `achievements`, `certifications`, and `summary`. What fields does each section expose to the template?
2. How should links be handled end to end so Repo/Demo/Credential links are clickable in the PDF, safe in HTML, and never invented by the model?
3. What tests would prove this migration really removed the LaTeX dependency instead of just hiding it behind a new import path?

## Jinja Migration Round 2 Answers

1. `build_template_context()` should first create a plain `content_by_placeholder` map, a `profile_by_id` map, and a grouped entry map keyed by `entry_id` or `source_item_id`. It should then iterate `template_plan.section_order` and build only non-empty sections. `education` exposes `entries` with `title`, `organization`, `location`, `dates`, and `bullets`, rendered Jake-style as school/location on line one and degree/dates on line two. `experience` exposes the same entry shape, rendered as title/dates on line one and organization/location on line two. `projects` exposes `title`, `tech_stack`, `dates`, `links`, and `bullets`. `achievements` and `certifications` expose `title`, `organization`, `dates`, `links`, and `bullets`, where organization can represent issuer/event/source. `technical_skills` exposes `skills`, a list of `{label, items}` from `field_label` plus placeholder text. `summary` exposes `summary_items` or `paragraphs`, each plain text. The top level should include `template_family`, `name`, `contact`, `section_order`, and `sections`. Candidate identity/contact can stay defaulted for this migration unless a real user profile/contact schema is added.
2. Links should be owned by profile evidence, not by model-written resume text. The renderer should extract fixed-label links from profile payload fields: `repo_url` as `Repo`, `demo_url` as `Demo`, `credential_url` as `Credential`, and fallback `url` as `Link` only when the specific fields are absent. It should trim blanks, reject unsafe schemes such as `javascript:`, allow only expected web/mail schemes, and let Jinja autoescape attribute values. The HTML template should render links with normal `<a href="{{ link.url }}">{{ link.label }}</a>` elements so WeasyPrint preserves clickable PDF annotations. The prompts should continue telling the model not to output URLs or link markup; tests should prove links appear from payload data even when resume content contains none.
3. Tests should make LaTeX impossible and still pass. Set `settings.latex_engine` to a bogus value, monkeypatch `subprocess.run` to fail if called, and assert `html_renderer.compile_resume()` still writes `resume.html`, `resume.pdf`, and archival `resume.tex`. Add a failure test where WeasyPrint raises and assert the result is a clear failed compile, not a LaTeX/raw-PDF fallback. Add a tailoring service test proving `CompileRun.compiler == "weasyprint"` and `CompileResult.html_path` is included. Keep `assemble_latex()` tests separate so archival `.tex` generation remains covered without implying it renders the PDF. Optionally assert removed fallback functions are no longer imported or referenced by production code.

## Jinja Migration Round 2 Feedback

1. Correct section mapping. The key implementation detail is to keep one normalized entry shape where possible, but let the template choose section-specific two-line layouts. This avoids seven separate mini-renderers while still matching Jake's visual grammar.
2. Correct trust boundary. Links are evidence metadata, not model prose. The extra production guard is URL validation before rendering because autoescape prevents HTML injection but does not by itself decide whether a URL scheme is safe.
3. Correct test strategy. The best proof is behavioral: bogus LaTeX settings and a poisoned `subprocess.run` must not affect successful WeasyPrint rendering. Also test the failure path so a broken WeasyPrint install does not silently create a misleading PDF through old code.

Key implementation decisions from Round 2:
- `build_template_context()` is the only place that understands placeholders, content types, profile evidence, and section grouping.
- The template renders a clean context and should not branch on placeholder IDs.
- Links come only from profile payload URL fields and use fixed labels.
- Tests must prove no subprocess-based LaTeX compile path remains in production rendering.

## Jinja Migration Round 3 Questions

1. How should `jakes_resume.css` reproduce the attached Jake screenshot in WeasyPrint, including page size, margins, typography, spacing, section rules, right-aligned metadata, and bullet density?
2. What packaging/runtime changes are needed so template files and CSS are available in editable installs, tests, and built wheels, and so developers understand the WeasyPrint/Pango dependency?
3. What should the final validation and rollout plan be before merging this migration, including automated tests, manual PDF QA, failure-mode checks, and any backward-compatibility notes?

## Jinja Migration Round 3 Answers

1. `jakes_resume.css` should target print output first. Use `@page { size: Letter; margin: 0.5in; }`, a compact serif stack such as `"Latin Modern Roman", "Times New Roman", Times, serif`, and an `11pt` body baseline close to Jake's LaTeX output. The header should center the candidate name with a large bold serif size, tight bottom spacing, and a smaller inline contact row. Section headings should use small caps, modest font size, tight vertical margins, and a `1px` bottom border to match the horizontal rule in the screenshot. Entries should use a two-column layout with left text and right-aligned dates/location/links, implemented with table/table-cell or stable flex rules that WeasyPrint handles reliably. Entry titles should be bold, secondary lines italic, tech stacks italic after a separator, and bullets should have small font size, compact line height, tight margins, and a modest left indent. The CSS should avoid decorative backgrounds, images, cards, and anything that harms ATS parsing. The goal is dense, readable, selectable text that visually tracks the Jake screenshot, not pixel-perfect browser UI.
2. Template assets must be real package assets, not loose files that only exist in the source tree by accident. Add `app/templates/jakes_resume.html.j2` and `app/templates/jakes_resume.css`, load them through a stable package-relative path or Jinja `PackageLoader`, and verify both editable installs and built wheels can find them. If Hatch does not include template files by default, add explicit build configuration for `app/templates/*`. Runtime docs should move from LaTeX setup to WeasyPrint setup: mention Python version compatibility, `jinja2`, `weasyprint`, and native Pango/Cairo dependencies. README should include `python -m weasyprint --info` as the environment sanity check, explain that `LATEX_ENGINE` is legacy/unused, and describe generated artifacts: `resume.html`, `resume.pdf`, and archival `resume.tex`.
3. Final validation should combine contract tests, renderer tests, service integration tests, and manual PDF QA. Automated tests should cover context building for every supported section, URL extraction/sanitization, Jinja HTML rendering with escaped special characters, successful WeasyPrint PDF creation while LaTeX is deliberately unavailable, WeasyPrint failure behavior, `CompileResult.html_path`, `CompileRun.compiler == "weasyprint"`, and preservation of archival `tex_path`. Keep LaTeX assembly tests only for the archival `.tex` path. Manual QA should generate a representative resume and compare it against the Jake screenshot: centered header, section rules, dense spacing, right-aligned metadata, clickable links, selectable text, and one-page fit for ordinary early-career content. Rollout notes should call out that `pdflatex`/`xelatex` are no longer needed, WeasyPrint/Pango is the new system dependency, `latex_engine` remains only for backward-compatible config shape, and existing consumers can still read `pdf_path`, `tex_path`, and now `html_path`.

## Jinja Migration Round 3 Feedback

1. Correct visual target. The subtle risk is WeasyPrint CSS support: prefer boring print-friendly layout primitives over clever browser-only CSS. Use the screenshot as a density/spacing target, but keep ATS-readability higher priority than pixel-perfect ornament.
2. Correct packaging emphasis. The most common production failure would be `TemplateNotFound` or missing CSS in a wheel, so package-data verification belongs in the test/QA plan, not as an afterthought.
3. Correct rollout shape. The migration is production-ready only if tests prove LaTeX is not invoked and the service metadata tells the truth. A pretty PDF is necessary, but not sufficient.

Key implementation decisions from Round 3:
- CSS should be print-first, dense, semantic, and conservative for WeasyPrint.
- Template and CSS files must be included in built distributions and loaded package-relatively.
- README/setup docs must replace LaTeX guidance with WeasyPrint/Pango guidance.
- Final verification must prove rendering, metadata, packaging, failure behavior, and manual PDF quality.

## Grill Closeout

Current design level: strong implementation-ready understanding. The architecture is now clear enough to hand to a coding pass: `html_renderer.py` owns the new rendering pipeline, `latex.py` becomes archival-only, Jinja consumes structured context, links come from profile evidence, WeasyPrint is the only PDF renderer, and tests must actively prove LaTeX is not used.

Strongest areas:
- Clear module boundaries between data transformation, templating, PDF rendering, and archival `.tex`.
- Correct trust boundary: model content stays plain, links and layout come from deterministic code.
- Good migration safety: preserve `tex_path`, add `html_path`, and update compiler metadata.
- Strong validation instinct around poisoning `subprocess.run` and bogus `latex_engine`.

Weakest gaps to watch during implementation:
- Package-data handling for templates/CSS can be easy to miss.
- WeasyPrint/Pango install behavior should be documented carefully, especially outside the current Windows dev machine.
- CSS should be tested against actual PDF output, not only HTML snapshots.
- Candidate contact fields are still placeholder/defaulted unless a real profile/contact source is introduced.

Next drills:
- Write the exact `build_template_context()` unit-test cases before implementation.
- Decide whether `html_path` should remain only in `CompileResult.compile_metadata` or become a first-class DB artifact column later.
- Add a small visual-regression/manual-QA checklist for generated PDFs.

Uncomfortable question to revisit:
- If the WeasyPrint PDF is visually close but not identical to Jake's LaTeX output, what tolerance is acceptable before you would delay the migration?
