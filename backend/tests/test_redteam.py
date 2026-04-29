"""
tests/test_redteam.py – Unit tests for redteam/catalogue.py and
                        redteam/prompt_generator.py
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from redteam.catalogue import ATTACK_CATALOGUE, get_payload


# ── Catalogue structure ────────────────────────────────────────────────────

class TestAttackCatalogue:
    def test_catalogue_not_empty(self):
        assert len(ATTACK_CATALOGUE) > 0

    def test_all_entries_have_required_keys(self):
        required = {"id", "name", "description", "severity", "payloads"}
        for attack_id, entry in ATTACK_CATALOGUE.items():
            missing = required - entry.keys()
            assert not missing, f"Attack '{attack_id}' is missing keys: {missing}"

    def test_all_entries_have_non_empty_payloads(self):
        for attack_id, entry in ATTACK_CATALOGUE.items():
            assert len(entry["payloads"]) > 0, f"'{attack_id}' has no payloads"

    def test_severity_values_valid(self):
        valid = {"low", "medium", "high", "critical"}
        for attack_id, entry in ATTACK_CATALOGUE.items():
            assert entry["severity"] in valid, (
                f"'{attack_id}' has invalid severity: {entry['severity']}"
            )

    def test_idpi_present(self):
        assert "idpi" in ATTACK_CATALOGUE

    def test_schema_poison_present(self):
        assert "schema_poison" in ATTACK_CATALOGUE

    def test_tool_fuzzing_or_similar_present(self):
        """At least one fuzzing / parameter-mutation attack type exists."""
        has_fuzz = any(
            "fuzz" in k or "param" in k or "memory" in k
            for k in ATTACK_CATALOGUE
        )
        assert has_fuzz


# ── Payload retrieval ──────────────────────────────────────────────────────

class TestGetPayload:
    def test_get_payload_returns_string(self):
        payload = get_payload("idpi")
        assert isinstance(payload, str)
        assert len(payload) > 0

    def test_get_payload_unknown_type_raises_or_returns_string(self):
        """Unknown attack types should either raise ValueError or return a default."""
        try:
            payload = get_payload("nonexistent_attack_xyz")
            assert isinstance(payload, str)
        except (KeyError, ValueError):
            pass  # both behaviours acceptable

    def test_schema_poison_payload_content(self):
        payload = get_payload("schema_poison")
        assert isinstance(payload, str)
        assert len(payload) > 10


# ── AdversarialPromptGenerator ─────────────────────────────────────────────

class TestAdversarialPromptGenerator:
    @pytest.fixture(autouse=True)
    def _setup(self):
        from redteam.prompt_generator import AdversarialPromptGenerator
        self.gen = AdversarialPromptGenerator(seed=42)

    def test_generate_returns_list(self):
        prompts = self.gen.generate_variants(attack_type="idpi", n=3)
        assert isinstance(prompts, list)
        assert len(prompts) == 3

    def test_generate_strings_not_empty(self):
        prompts = self.gen.generate_variants(attack_type="idpi", n=2)
        for p in prompts:
            assert isinstance(p, str)
            assert len(p) > 0

    def test_fuzz_parameters_returns_list(self):
        variants = self.gen.fuzz_parameters("booking_api", {"flight_id": "FL001"}, n=4)
        assert isinstance(variants, list)
        assert len(variants) == 4

    def test_seeded_generator_is_deterministic(self):
        gen1 = __import__("redteam.prompt_generator",
                           fromlist=["AdversarialPromptGenerator"]).AdversarialPromptGenerator(seed=99)
        gen2 = __import__("redteam.prompt_generator",
                           fromlist=["AdversarialPromptGenerator"]).AdversarialPromptGenerator(seed=99)
        p1 = gen1.generate_variants("idpi", n=2)
        p2 = gen2.generate_variants("idpi", n=2)
        assert p1 == p2
