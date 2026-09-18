"""Privacy boundary tests for archive-only local profile handling."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.privacy_boundary import (
    PrivacyBoundaryBlocker,
    PrivacyBoundaryFinding,
    PrivacyBoundaryReport,
    PrivacyBoundaryStatus,
    _scan_file,
    scan_privacy_boundary,
)


def test_privacy_boundary_passes_when_profile_is_only_source(tmp_path: Path) -> None:
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs/archive/reference_local_computer_profile.md").write_text(
        "\n".join(
            (
                "# Local Computer Profile",
                "Device: LOCAL-DEVICE-ALPHA",
                "GPU: PRIVATEGPU123",
                "Python: 3.14.7",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "overview.md").write_text(
        (
            "System documentation links to "
            "docs/archive/reference_local_computer_profile.md for local profile data. "
            "The canonical runtime is Python 3.14.7."
        ),
        encoding="utf-8",
    )

    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.PASSED
    assert (
        report.computer_profile_ref
        == "docs/archive/reference_local_computer_profile.md"
    )
    assert report.findings == ()
    assert report.blockers == ()
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_privacy_boundary_treats_version_tokens_as_non_personal(tmp_path: Path) -> None:
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs/archive/reference_local_computer_profile.md").write_text(
        "Python: 9.87.6\n",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "overview.md").write_text(
        "Compatibility was checked with Python 9.87.6.\n",
        encoding="utf-8",
    )

    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.PASSED
    assert report.findings == ()


def test_privacy_boundary_reports_hash_without_raw_token(tmp_path: Path) -> None:
    profile_marker = "LOCAL-DEVICE-ALPHA"
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs/archive/reference_local_computer_profile.md").write_text(
        f"Device: {profile_marker}\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs" / "leak.md").write_text(
        f"Do not copy {profile_marker} into documentation.\n",
        encoding="utf-8",
    )

    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.BLOCKED
    assert report.blockers == (
        PrivacyBoundaryBlocker.PERSONAL_INFO_OUTSIDE_COMPUTER_MD,
    )
    assert report.finding_count == 1
    assert report.findings[0].file_path == "docs/leak.md"
    assert report.findings[0].line_number == 1
    assert (
        report.findings[0].token_sha256
        == sha256(profile_marker.encode("utf-8")).hexdigest()
    )
    assert profile_marker not in repr(report)


def test_privacy_boundary_ignores_local_profile_neighbors(tmp_path: Path) -> None:
    profile_marker = "PRIVATEGPU123"
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "docs/archive/reference_local_computer_profile.md").write_text(
        f"GPU: {profile_marker}\n",
        encoding="utf-8",
    )
    (tmp_path / "computer_local.md").write_text(
        f"Local copy: {profile_marker}\n",
        encoding="utf-8",
    )
    hardware_dir = tmp_path / ".hardware"
    hardware_dir.mkdir()
    (hardware_dir / "probe.txt").write_text(
        f"Probe detail: {profile_marker}\n",
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime" / "tmp"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "generated.jsonl").write_text(
        f'{{"runtime_detail": "{profile_marker}"}}\n',
        encoding="utf-8",
    )

    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.PASSED
    assert report.findings == ()


def test_privacy_boundary_missing_computer_md_is_not_configured(
    tmp_path: Path,
) -> None:
    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.NOT_CONFIGURED
    assert report.blockers == (PrivacyBoundaryBlocker.COMPUTER_MD_NOT_FOUND,)
    assert report.finding_count == 0
    assert report.execution_allowed is False


def test_privacy_boundary_contracts_reject_unsafe_shapes() -> None:
    with pytest.raises(ValueError, match="cannot allow execution"):
        PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.PASSED,
            computer_profile_ref="docs/archive/reference_local_computer_profile.md",
            scanned_file_count=0,
            finding_count=0,
            findings=(),
            blockers=(),
            execution_allowed=True,
        )
    with pytest.raises(ValueError, match="repository-relative"):
        PrivacyBoundaryFinding(
            file_path="C:/outside/leak.md",
            line_number=1,
            token_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="line_number"):
        PrivacyBoundaryFinding(
            file_path="docs/leak.md",
            line_number=0,
            token_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="SHA-256"):
        PrivacyBoundaryFinding(
            file_path="docs/leak.md",
            line_number=1,
            token_sha256="bad",  # noqa: S106 - deliberately invalid digest fixture
        )
    with pytest.raises(ValueError, match="live trading"):
        PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.PASSED,
            computer_profile_ref="docs/archive/reference_local_computer_profile.md",
            scanned_file_count=0,
            finding_count=0,
            findings=(),
            blockers=(),
            live_eligibility_status="READY",
        )
    with pytest.raises(ValueError, match="research-only"):
        PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.PASSED,
            computer_profile_ref="docs/archive/reference_local_computer_profile.md",
            scanned_file_count=0,
            finding_count=0,
            findings=(),
            blockers=(),
            promotion_status="PAPER_APPROVED",
        )
    with pytest.raises(ValueError, match="finding_count"):
        PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.PASSED,
            computer_profile_ref="docs/archive/reference_local_computer_profile.md",
            scanned_file_count=0,
            finding_count=1,
            findings=(),
            blockers=(),
        )
    with pytest.raises(ValueError, match="scanned_file_count"):
        PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.PASSED,
            computer_profile_ref="docs/archive/reference_local_computer_profile.md",
            scanned_file_count=-1,
            finding_count=0,
            findings=(),
            blockers=(),
        )
    with pytest.raises(ValueError, match="require blockers"):
        PrivacyBoundaryReport(
            status=PrivacyBoundaryStatus.BLOCKED,
            computer_profile_ref="docs/archive/reference_local_computer_profile.md",
            scanned_file_count=0,
            finding_count=0,
            findings=(),
            blockers=(),
        )


def test_privacy_boundary_handles_external_profile_ref_and_scannable_edges(
    tmp_path: Path,
) -> None:
    external_profile = tmp_path.parent / "external_computer_profile.md"
    marker = r"C:\Users\PrivateUser42\workspace"
    external_profile.write_text(f"Path: {marker}\n", encoding="utf-8")
    try:
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "leak.txt").write_text(
            f"Copied {marker} here.\n",
            encoding="utf-8",
        )
        (tmp_path / "docs" / "ignored.bin").write_text(
            f"Binary suffix {marker}\n",
            encoding="utf-8",
        )
        large = tmp_path / "docs" / "large.md"
        large.write_text(f"Large {marker}\n" * 10, encoding="utf-8")

        report = scan_privacy_boundary(
            tmp_path,
            computer_md=external_profile,
            max_file_bytes=100,
        )

        assert report.computer_profile_ref == "external_computer_profile.md"
        assert report.status is PrivacyBoundaryStatus.BLOCKED
        assert tuple(item.file_path for item in report.findings) == ("docs/leak.txt",)
    finally:
        external_profile.unlink(missing_ok=True)


def test_privacy_boundary_handles_unreadable_profile_and_duplicate_line_matches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "docs" / "archive" / "reference_local_computer_profile.md"
    profile.parent.mkdir(parents=True)
    profile.write_text("Device: LOCAL-DEVICE-ALPHA\n", encoding="utf-8")

    original_read_text = Path.read_text

    def guarded_read_text(
        self: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if self == profile:
            raise OSError("blocked")
        return original_read_text(self, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.BLOCKED
    assert report.blockers == (PrivacyBoundaryBlocker.COMPUTER_MD_UNREADABLE,)

    monkeypatch.setattr(Path, "read_text", original_read_text)
    leak = tmp_path / "docs" / "leak.md"
    leak.write_text(
        "LOCAL-DEVICE-ALPHA LOCAL-DEVICE-ALPHA\n",
        encoding="utf-8",
    )

    findings = _scan_file(leak, "docs/leak.md", frozenset({"LOCAL-DEVICE-ALPHA"}))

    assert len(findings) == 1
    assert _scan_file(leak, "docs/leak.md", frozenset()) == ()
