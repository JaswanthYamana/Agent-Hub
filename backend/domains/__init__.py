"""
domains/__init__.py – Domain definitions module.

This module exports all starter domains and domain management utilities.
"""

from .definitions import (
    CODE_REVIEW_DOMAIN,
    CUSTOMER_SUPPORT_DOMAIN,
    DATA_ANALYSIS_DOMAIN,
    OPERATIONS_TRIAGE_DOMAIN,
    PROCUREMENT_DOMAIN,
    WEB_RESEARCH_DOMAIN,
)

__all__ = [
    "CUSTOMER_SUPPORT_DOMAIN",
    "CODE_REVIEW_DOMAIN",
    "OPERATIONS_TRIAGE_DOMAIN",
    "DATA_ANALYSIS_DOMAIN",
    "WEB_RESEARCH_DOMAIN",
    "PROCUREMENT_DOMAIN",
]
