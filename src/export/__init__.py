"""Unified export module for cross-project financial fact exchange.

Produces a normalised JSON envelope that downstream quantitative platforms
(e.g. ``stock``) can consume as fundamental-factor input.
"""

from src.export.builder import build_export
from src.export.schema import ExportedFact, ExportedFinancialFacts

__all__ = ["ExportedFact", "ExportedFinancialFacts", "build_export"]
