from app.services.scraper import assess_text_extraction_quality, html_to_markdownish_text


def test_html_to_markdownish_text_removes_obvious_page_clutter() -> None:
    html = """
    <html>
      <head><script>window.noisy = true;</script></head>
      <body>
        <nav>Apply now</nav>
        <div class="cookie-banner">Accept cookies</div>
        <main>
          <h1>Backend Engineer</h1>
          <div hidden>Hidden recruiter note: must have Scala.</div>
          <div aria-hidden="true">Invisible tracking text with COBOL.</div>
          <div style="display:none">Hidden keyword stuffing with Kubernetes.</div>
          <section>
            <h2>Responsibilities</h2>
            <ul>
              <li>Build Python APIs for application workflows.</li>
              <li>Improve PostgreSQL query reliability.</li>
            </ul>
          </section>
          <section>
            <h2>Requirements</h2>
            <p>Experience with FastAPI, REST services, and SQL.</p>
          </section>
        </main>
      </body>
    </html>
    """

    text = html_to_markdownish_text(html)

    assert "Backend Engineer" in text
    assert "Responsibilities" in text
    assert "FastAPI" in text
    assert "Apply now" not in text
    assert "Accept cookies" not in text
    assert "window.noisy" not in text
    assert "Scala" not in text
    assert "COBOL" not in text
    assert "Kubernetes" not in text


def test_html_to_markdownish_text_skips_children_of_removed_clutter() -> None:
    html = """
    <html>
      <body>
        <main>
          <h1>Platform Engineer</h1>
          <section class="cookie-banner">
            <h2>Cookie settings</h2>
            <p>Accept cookies before reading this page.</p>
          </section>
          <section>
            <h2>Requirements</h2>
            <p>Python experience and API reliability ownership.</p>
          </section>
        </main>
      </body>
    </html>
    """

    text = html_to_markdownish_text(html)

    assert "Platform Engineer" in text
    assert "Python experience" in text
    assert "Cookie settings" not in text
    assert "Accept cookies" not in text


def test_extraction_quality_blocks_short_non_job_text() -> None:
    assessment = assess_text_extraction_quality("Welcome to our careers page.")

    assert assessment.is_usable is False
    assert assessment.confidence == "low"


def test_extraction_quality_allows_short_clean_job_text_with_signals() -> None:
    assessment = assess_text_extraction_quality(
        "Backend Engineer. Requirements: Python and SQL experience. "
        "Responsibilities: build APIs and improve reliability."
    )

    assert assessment.is_usable is True
    assert assessment.confidence in {"medium", "high"}
