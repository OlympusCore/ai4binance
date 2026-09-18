"""Compatibility facade for canonical Agent Skill discovery CLI services."""

from ai4binance.cli.bootstrap.skill_discovery import (
    run_skill_discovery_command as run_skill_discovery_command,
)

__all__ = ("run_skill_discovery_command",)
