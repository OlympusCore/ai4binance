"""Privacy boundary tests for Computer.md-only local profile handling."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest

from ai4binance.privacy_boundary import (
    PrivacyBoundaryBlocker,
    PrivacyBoundaryFinding,
    PrivacyBoundaryReport,
    PrivacyBoundaryStatus,
    scan_privacy_boundary,
)


def test_privacy_boundary_passes_when_profile_is_only_source(tmp_path: Path) -> None:
    (tmp_path / "Computer.md").write_text(
        "\n".join(
            (
                "# Local Computer Profile",
                "Device: LOCAL-DEVICE-ALPHA",
                "GPU: PRIVATEGPU123",
            )
        ),
        encoding="utf-8",
    )
    (tmp_path / "Docs").mkdir()
    (tmp_path / "Docs" / "overview.md").write_text(
        "System documentation links to Computer.md for local profile data.",
        encoding="utf-8",
    )

    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.PASSED
    assert report.computer_profile_ref == "Computer.md"
    assert report.findings == ()
    assert report.blockers == ()
    assert report.execution_allowed is False
    assert report.promotion_status == "RESEARCH_ONLY"
    assert report.live_eligibility_status == "LIVE_ORDER_BLOCKED"


def test_privacy_boundary_reports_hash_without_raw_token(tmp_path: Path) -> None:
    profile_marker = "LOCAL-DEVICE-ALPHA"
    (tmp_path / "Computer.md").write_text(
        f"Device: {profile_marker}\n",
        encoding="utf-8",
    )
    (tmp_path / "Docs").mkdir()
    (tmp_path / "Docs" / "leak.md").write_text(
        f"Do not copy {profile_marker} into documentation.\n",
        encoding="utf-8",
    )

    report = scan_privacy_boundary(tmp_path)

    assert report.status is PrivacyBoundaryStatus.BLOCKED
    assert report.blockers == (
        PrivacyBoundaryBlocker.PERSONAL_INFO_OUTSIDE_COMPUTER_MD,
    )
    assert report.finding_count == 1
    assert report.findings[0].file_path == "Docs/leak.md"
    assert report.findings[0].line_number == 1
    assert (
        report.findings[0].token_sha256
        == sha256(profile_marker.encode("utf-8")).hexdigest()
    )
    assert profile_marker not in repr(report)


def test_privacy_boundary_ignores_local_profile_neighbors(tmp_path: Path) -> None:
    profile_marker = "PRIVATEGPU123"
    (tmp_path / "Computer.md").write_text(
        f"GPU: {profile_marker}\n",
        encoding="utf-8",
    )
    (tmp_path / "Computer.local.md").write_text(
        f"Local copy: {profile_marker}\n",
        encoding="utf-8",
    )
    hardware_dir = tmp_path / ".hardware"
    hardware_dir.mkdir()
    (hardware_dir / "probe.txt").write_text(
        f"Probe detail: {profile_marker}\n",
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
            computer_profile_ref="Computer.md",
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
