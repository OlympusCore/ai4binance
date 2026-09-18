from __future__ import annotations

from ai4binance.cli.bootstrap import (
    SnapshotAcquirer,
    build_parser,
    normalize_cli_symbol,
    normalize_slash_command,
    parse_arguments,
    parse_as_of,
    safe_validation_symbol,
)
from ai4binance.cli.bootstrap.parser import build_parser as canonical_build_parser
from ai4binance.cli.parser import (
    SnapshotAcquirer as LegacySnapshotAcquirer,
)
from ai4binance.cli.parser import (
    build_parser as legacy_build_parser,
)
from ai4binance.cli.parser import (
    normalize_cli_symbol as legacy_normalize_cli_symbol,
)
from ai4binance.cli.parser import (
    normalize_slash_command as legacy_normalize_slash_command,
)
from ai4binance.cli.parser import (
    parse_arguments as legacy_parse_arguments,
)
from ai4binance.cli.parser import (
    parse_as_of as legacy_parse_as_of,
)
from ai4binance.cli.parser import (
    safe_validation_symbol as legacy_safe_validation_symbol,
)


def test_cli_parser_legacy_import_preserves_canonical_symbol_identity() -> None:
    assert SnapshotAcquirer is LegacySnapshotAcquirer
    assert build_parser is canonical_build_parser
    assert legacy_build_parser is canonical_build_parser
    assert normalize_cli_symbol is legacy_normalize_cli_symbol
    assert normalize_slash_command is legacy_normalize_slash_command
    assert parse_arguments is legacy_parse_arguments
    assert parse_as_of is legacy_parse_as_of
    assert safe_validation_symbol is legacy_safe_validation_symbol
    assert canonical_build_parser.__module__ == "ai4binance.cli.bootstrap.parser"
