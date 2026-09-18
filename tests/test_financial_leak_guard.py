from __future__ import annotations

from pathlib import Path

import pytest

from ai4binance.ops.financial_leak_guard import (
    FinancialLeakFinding,
    FinancialLeakScanResult,
    assert_public_financial_values_do_not_leak,
    main,
    scan_public_financial_value_leaks,
)


def test_financial_leak_guard_blocks_binance_values_in_public_ykb_surface(
    tmp_path: Path,
) -> None:
    public_report = tmp_path / "runtime" / "reports" / "ykb" / "ykb_report.md"
    public_report.parent.mkdir(parents=True)
    public_report.write_text(
        "market_value_usdt: 125\nfree_market_value_usdt: 100\n",
        encoding="utf-8",
    )

    result = scan_public_financial_value_leaks(tmp_path)

    assert result.status == "BLOCKED"
    assert result.findings[0].relative_path == "runtime/reports/ykb/ykb_report.md"
    assert result.findings[0].token == "market_value_usdt"  # noqa: S105
    assert "BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK" in result.blockers
    assert result.execution_allowed is False
    assert result.live_eligibility_status == "LIVE_ORDER_BLOCKED"
    with pytest.raises(ValueError, match="BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK"):
        assert_public_financial_values_do_not_leak(tmp_path)


def test_financial_leak_guard_allows_local_private_ykb_financial_annex(
    tmp_path: Path,
) -> None:
    private_report = tmp_path / "state" / "private" / "ykb" / "financial.md"
    private_report.parent.mkdir(parents=True)
    private_report.write_text(
        "market_value_usdt: 125\nfree_market_value_usdt: 100\n",
        encoding="utf-8",
    )
    public_report = tmp_path / "runtime" / "reports" / "ykb" / "ykb_report.md"
    public_report.parent.mkdir(parents=True)
    public_report.write_text(
        "value_disclosure_policy: LOCAL_PRIVATE_ANNEX_ONLY\n",
        encoding="utf-8",
    )

    result = scan_public_financial_value_leaks(tmp_path)

    assert result.status == "CLEAR"
    assert result.findings == ()
    assert result.blockers == ()


def test_financial_leak_guard_contract_and_cli_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clear = FinancialLeakScanResult(
        status="CLEAR",
        scanned_roots=("runtime/reports/ykb",),
        findings=(),
        blockers=(),
    )
    assert clear.to_payload()["status"] == "CLEAR"
    with pytest.raises(ValueError, match="status is invalid"):
        FinancialLeakScanResult(
            status="UNKNOWN",
            scanned_roots=(),
            findings=(),
            blockers=(),
        )
    with pytest.raises(ValueError, match="clear financial leak scan"):
        FinancialLeakScanResult(
            status="CLEAR",
            scanned_roots=(),
            findings=(FinancialLeakFinding("a", "market_value_usdt"),),
            blockers=(),
        )
    with pytest.raises(ValueError, match="requires findings"):
        FinancialLeakScanResult(
            status="BLOCKED",
            scanned_roots=(),
            findings=(),
            blockers=("BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK",),
        )
    with pytest.raises(ValueError, match="cannot authorize execution"):
        FinancialLeakScanResult(
            status="CLEAR",
            scanned_roots=(),
            findings=(),
            blockers=(),
            execution_allowed=True,
        )

    assert main(["--repository-root", str(tmp_path)]) == 0
    assert "GUARD_CLEAR" in capsys.readouterr().out

    public_report = tmp_path / "runtime" / "reports" / "ykb" / "ykb_report.md"
    public_report.parent.mkdir(parents=True)
    public_report.write_text("availableBalance: 10\n", encoding="utf-8")

    assert main(["--repository-root", str(tmp_path)]) == 1
    assert "BINANCE_FINANCIAL_VALUE_PUBLIC_LEAK" in capsys.readouterr().out


def test_financial_leak_guard_skips_binary_and_oversized_public_files(
    tmp_path: Path,
) -> None:
    public_dir = tmp_path / "runtime" / "reports" / "ykb"
    public_dir.mkdir(parents=True)
    (public_dir / "binary.bin").write_bytes(b"\xff\xfe\x00\x00market_value_usdt")
    (public_dir / "large.md").write_text(
        "x" * 2_000_001 + "market_value_usdt",
        encoding="utf-8",
    )

    result = scan_public_financial_value_leaks(tmp_path)

    assert result.status == "CLEAR"
