import json
import subprocess
import sys
from pathlib import Path


def _run_report(quality_path: str, findings_path: str, output_path: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "code_check.cli", "report",
         "--quality", quality_path, "--findings", findings_path, "--output", output_path],
        capture_output=True, text=True,
        cwd=Path(__file__).parent.parent,
    )


class TestCliReport:
    def test_report_generates_file(self, tmp_path, sample_quality, sample_findings_passed):
        quality_file = tmp_path / "quality.json"
        findings_file = tmp_path / "findings.json"
        output_file = tmp_path / "report.md"

        quality_file.write_text(json.dumps(sample_quality))
        findings_file.write_text(json.dumps(sample_findings_passed))

        result = _run_report(str(quality_file), str(findings_file), str(output_file))
        assert result.returncode == 0

        assert output_file.exists()
        content = output_file.read_text()
        assert "PASSED" in content

    def test_report_missing_findings_exits_error(self, tmp_path):
        result = _run_report("/dev/null", "/nonexistent/f.json", str(tmp_path / "out.md"))
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_report_missing_quality_warns(self, tmp_path, sample_findings_passed):
        findings_file = tmp_path / "findings.json"
        output_file = tmp_path / "report.md"

        findings_file.write_text(json.dumps(sample_findings_passed))

        result = _run_report("/nonexistent/q.json", str(findings_file), str(output_file))
        assert output_file.exists()

    def test_report_help_shows_quality_findings_args(self):
        result = subprocess.run(
            [sys.executable, "-m", "code_check.cli", "report", "--help"],
            capture_output=True, text=True,
            cwd=Path(__file__).parent.parent,
        )
        assert "--quality" in result.stdout
        assert "--findings" in result.stdout
        assert "--output" in result.stdout
