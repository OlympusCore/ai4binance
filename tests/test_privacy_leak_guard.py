from __future__ import annotations

from pathlib import Path

import pytest

from ai4binance.ops.privacy_leak_guard import (
    PrivacyLeakFinding,
    PrivacyLeakScanResult,
    assert_public_privacy_data_do_not_leak,
    assert_runtime_state_private_boundary,
    main,
    scan_public_privacy_leaks,
    scan_runtime_state_private_boundary,
)


def test_privacy_leak_guard_blocks_email_and_binance_wallet_in_public_reports(
    tmp_path: Path,
) -> None:
    public_report = tmp_path / "runtime" / "reports" / "ykb" / "ykb_report.md"
    public_report.parent.mkdir(parents=True)
    public_report.write_text(
        "mailadresim: owner@example.com\nBinanWallet: spot-main\n",
        encoding="utf-8",
    )

    result = scan_public_privacy_leaks(tmp_path)

    assert result.status == "BLOCKED"
    assert result.findings[0].relative_path == "runtime/reports/ykb/ykb_report.md"
    assert {finding.category for finding in result.findings} == {
        "EMAIL_ADDRESS_PUBLIC_LEAK",
        "BINANCE_WALLET_IDENTIFIER_PUBLIC_LEAK",
        "KVKK_PERSONAL_DATA_PUBLIC_LEAK",
    }
    assert "KVKK_PUBLIC_PRIVACY_LEAK" in result.blockers
    assert "NO_GITHUB_CLOUD_SHARE" in result.blockers
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="KVKK_PUBLIC_PRIVACY_LEAK"):
        assert_public_privacy_data_do_not_leak(tmp_path)


def test_privacy_leak_guard_allows_local_private_state(
    tmp_path: Path,
) -> None:
    private_report = tmp_path / "state" / "private" / "ykb" / "financial.md"
    private_report.parent.mkdir(parents=True)
    private_report.write_text(
        "mailadresim: owner@example.com\nBinanceWallet: spot-main\n",
        encoding="utf-8",
    )
    public_report = tmp_path / "runtime" / "reports" / "ykb" / "ykb_report.md"
    public_report.parent.mkdir(parents=True)
    public_report.write_text(
        "privacy_policy: LOCAL_PRIVATE_ONLY\n",
        encoding="utf-8",
    )

    result = scan_public_privacy_leaks(tmp_path)

    assert result.status == "CLEAR"
    assert result.findings == ()
    assert result.blockers == ()


def test_runtime_state_private_boundary_blocks_wallet_state_outside_private_root(
    tmp_path: Path,
) -> None:
    unsafe_state = tmp_path / "runtime" / "state" / "account.json"
    unsafe_state.parent.mkdir(parents=True)
    unsafe_state.write_text(
        "mailadresim: owner@example.com\nBinanceWallet: spot-main\n",
        encoding="utf-8",
    )

    result = scan_runtime_state_private_boundary(tmp_path)

    assert result.status == "BLOCKED"
    assert result.findings[0].relative_path == "runtime/state/account.json"
    assert {finding.category for finding in result.findings} == {
        "RUNTIME_STATE_EMAIL_ADDRESS_PUBLIC_LEAK",
        "RUNTIME_STATE_BINANCE_WALLET_IDENTIFIER_PUBLIC_LEAK",
        "RUNTIME_STATE_KVKK_PERSONAL_DATA_PUBLIC_LEAK",
    }
    assert "RUNTIME_STATE_PRIVATE_BOUNDARY_VIOLATION" in result.blockers
    assert "PRIVATE_STATE_RELOCATION_REQUIRED" in result.blockers
    assert result.execution_allowed is False
    assert result.promotion_status == "RESEARCH_ONLY"
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    assert "owner@example.com" not in repr(result)
    with pytest.raises(ValueError, match="RUNTIME_STATE_PRIVATE_BOUNDARY_VIOLATION"):
        assert_runtime_state_private_boundary(tmp_path)


def test_runtime_state_private_boundary_allows_private_runtime_state(
    tmp_path: Path,
) -> None:
    private_state = tmp_path / "runtime" / "state" / "private" / "account.json"
    private_state.parent.mkdir(parents=True)
    private_state.write_text(
        "mailadresim: owner@example.com\nBinanceWallet: spot-main\n",
        encoding="utf-8",
    )

    result = scan_runtime_state_private_boundary(tmp_path)

    assert result.status == "CLEAR"
    assert result.findings == ()
    assert result.blockers == ()


def test_privacy_leak_guard_contract_cli_and_binary_skip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear = PrivacyLeakScanResult(
        status="CLEAR",
        scanned_roots=("runtime/reports/ykb",),
        findings=(),
        blockers=(),
    )
    assert clear.to_payload()["status"] == "CLEAR"
    with pytest.raises(ValueError, match="status is invalid"):
        PrivacyLeakScanResult(
            status="UNKNOWN",
            scanned_roots=(),
            findings=(),
            blockers=(),
        )
    with pytest.raises(ValueError, match="clear privacy leak scan"):
        PrivacyLeakScanResult(
            status="CLEAR",
            scanned_roots=(),
            findings=(PrivacyLeakFinding("a", "EMAIL_ADDRESS_PUBLIC_LEAK"),),
            blockers=(),
        )
    with pytest.raises(ValueError, match="requires findings"):
        PrivacyLeakScanResult(
            status="BLOCKED",
            scanned_roots=(),
            findings=(),
            blockers=("KVKK_PUBLIC_PRIVACY_LEAK",),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        PrivacyLeakScanResult(
            status="CLEAR",
            scanned_roots=(),
            findings=(),
            blockers=(),
            execution_allowed=True,
        )

    assert main(["--repository-root", str(tmp_path)]) == 0
    assert "PRIVACY_LEAK_GUARD_CLEAR" in capsys.readouterr().out

    public_dir = tmp_path / "runtime" / "reports" / "ykb"
    public_dir.mkdir(parents=True)
    (public_dir / "binary.bin").write_bytes(b"\xff\xfe\x00\x00owner@example.com")
    (public_dir / "large.md").write_text(
        "x" * 2_000_001 + "owner@example.com",
        encoding="utf-8",
    )
    assert scan_public_privacy_leaks(tmp_path).status == "CLEAR"

    (public_dir / "leak.md").write_text("0x1234567890abcdef1234567890abcdef12345678")
    assert main(["--repository-root", str(tmp_path)]) == 1
    assert "KVKK_PUBLIC_PRIVACY_LEAK" in capsys.readouterr().out
