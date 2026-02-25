"""Report generator: creates an HTML forensic investigation report from evaluation results."""

import json
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, BaseLoader

_REPORT_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Forensic Investigation Report — Case {{ case_id }}</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', Arial, sans-serif; background: #f4f6f9; color: #222; }
    header { background: #1a2540; color: #fff; padding: 24px 40px; }
    header h1 { font-size: 1.6rem; letter-spacing: 0.04em; }
    header p { margin-top: 6px; font-size: 0.9rem; opacity: 0.8; }
    .container { max-width: 1200px; margin: 30px auto; padding: 0 24px; }
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-bottom: 30px; }
    .card { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.1); text-align: center; }
    .card .num { font-size: 2rem; font-weight: 700; }
    .card .label { font-size: 0.82rem; color: #666; margin-top: 4px; text-transform: uppercase; letter-spacing: .05em; }
    .card.relevant .num { color: #d32f2f; }
    .card.potential .num { color: #f57c00; }
    .card.not-relevant .num { color: #388e3c; }
    .card.total .num { color: #1565c0; }
    section h2 { font-size: 1.15rem; margin-bottom: 14px; border-left: 4px solid #1a2540; padding-left: 12px; }
    .allegations-box { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 30px;
                       box-shadow: 0 1px 4px rgba(0,0,0,.1); white-space: pre-wrap; font-size: 0.9rem; line-height: 1.6; }
    table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
            box-shadow: 0 1px 4px rgba(0,0,0,.1); overflow: hidden; }
    th { background: #1a2540; color: #fff; padding: 12px 14px; text-align: left; font-size: 0.82rem; text-transform: uppercase; letter-spacing: .05em; }
    td { padding: 12px 14px; font-size: 0.88rem; border-bottom: 1px solid #eee; vertical-align: top; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: #f9fafb; }
    .badge { display: inline-block; padding: 3px 10px; border-radius: 12px; font-size: 0.78rem; font-weight: 600; white-space: nowrap; }
    .badge-relevant { background: #ffebee; color: #c62828; }
    .badge-potential { background: #fff3e0; color: #e65100; }
    .badge-not { background: #e8f5e9; color: #2e7d32; }
    .score-bar-wrap { width: 90px; background: #eee; border-radius: 4px; height: 8px; display: inline-block; vertical-align: middle; margin-left: 6px; }
    .score-bar { height: 8px; border-radius: 4px; background: #1565c0; }
    .kw-tag { display: inline-block; background: #e3f2fd; color: #1565c0; border-radius: 10px;
               padding: 2px 8px; font-size: 0.75rem; margin: 2px; }
    footer { text-align: center; padding: 30px; color: #999; font-size: 0.8rem; }
  </style>
</head>
<body>
  <header>
    <h1>🔍 Forensic AI Investigation Report</h1>
    <p>Case ID: {{ case_id }} &nbsp;|&nbsp; Generated: {{ generated_at }}</p>
  </header>

  <div class="container">

    <div class="summary-grid">
      <div class="card total"><div class="num">{{ total }}</div><div class="label">Total Results</div></div>
      <div class="card relevant"><div class="num">{{ count_relevant }}</div><div class="label">Relevant</div></div>
      <div class="card potential"><div class="num">{{ count_potential }}</div><div class="label">Potentially Relevant</div></div>
      <div class="card not-relevant"><div class="num">{{ count_not }}</div><div class="label">Not Relevant</div></div>
    </div>

    <section>
      <h2>Allegations</h2>
      <div class="allegations-box">{{ allegations }}</div>
    </section>

    <br/>
    <section>
      <h2>Evaluation Results</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Filename</th>
            <th>Verdict</th>
            <th>Relevance</th>
            <th>Confidence</th>
            <th>Matched Keywords</th>
            <th>Reasoning</th>
          </tr>
        </thead>
        <tbody>
          {% for r in results %}
          <tr>
            <td>{{ loop.index }}</td>
            <td><strong>{{ r.filename }}</strong><br/><small style="color:#888">{{ r.filepath }}</small></td>
            <td>
              {% if r.verdict == 'Relevant' %}
                <span class="badge badge-relevant">Relevant</span>
              {% elif r.verdict == 'Potentially Relevant' %}
                <span class="badge badge-potential">Potentially Relevant</span>
              {% else %}
                <span class="badge badge-not">Not Relevant</span>
              {% endif %}
            </td>
            <td>
              {{ "%.2f"|format(r.relevance_score) }}
              <div class="score-bar-wrap"><div class="score-bar" style="width:{{ (r.relevance_score * 100)|int }}%"></div></div>
            </td>
            <td>
              {{ "%.2f"|format(r.confidence_score) }}
              <div class="score-bar-wrap"><div class="score-bar" style="width:{{ (r.confidence_score * 100)|int }}%"></div></div>
            </td>
            <td>
              {% for kw in r.matched_keywords %}
                <span class="kw-tag">{{ kw }}</span>
              {% endfor %}
            </td>
            <td>{{ r.reasoning }}<br/><small style="color:#555">{{ r.matched_allegations }}</small></td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </section>

  </div>

  <footer>
    Generated by Forensic AI Investigation System &mdash; Powered by Ollama (offline LLM)
  </footer>
</body>
</html>
"""


def generate_report(
    case_id: str,
    allegations: str,
    evaluation_results: list[dict],
    reports_dir: Path,
) -> Path:
    """Render an HTML forensic report.

    Args:
        case_id: The unique case identifier.
        allegations: The original allegations text.
        evaluation_results: List of evaluated result dicts from the evaluator.
        reports_dir: The ``reports/`` sub-directory of the case folder.

    Returns:
        Path to the generated HTML report.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)

    count_relevant = sum(1 for r in evaluation_results if r.get("verdict") == "Relevant")
    count_potential = sum(
        1 for r in evaluation_results if r.get("verdict") == "Potentially Relevant"
    )
    count_not = sum(1 for r in evaluation_results if r.get("verdict") == "Not Relevant")

    env = Environment(loader=BaseLoader(), autoescape=True)
    template = env.from_string(_REPORT_TEMPLATE)
    html = template.render(
        case_id=case_id,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        allegations=allegations,
        results=evaluation_results,
        total=len(evaluation_results),
        count_relevant=count_relevant,
        count_potential=count_potential,
        count_not=count_not,
    )

    report_path = reports_dir / "investigation_report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path
