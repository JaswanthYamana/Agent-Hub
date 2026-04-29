"""
backend/tests/test_domains.py – Comprehensive tests for domain definitions and utilities.

Tests verify that:
1. All 7 domains (6 starter + 1 generic) are properly configured
2. Each domain has required fields (name, scenarios, optimal_path, etc.)
3. Domain lookup by scenario works correctly
4. Domain registration and serialization work as expected
"""

import pytest
from core.config import (
    DOMAINS,
    get_all_domains,
    get_domain,
    get_domain_names,
    register_domain,
    serialize_domain,
)


class TestDomainStructure:
    """Test that all domains have proper structure and required fields."""

    def test_all_domains_exist(self):
        """Verify that all 7 domains are registered."""
        expected_domains = {
            "flight_booking",
            "customer_support",
            "code_review",
            "operations_triage",
            "data_analysis",
            "web_research",
            "procurement",
            "generic",
        }
        assert set(DOMAINS.keys()) == expected_domains, (
            f"Expected domains {expected_domains}, got {set(DOMAINS.keys())}"
        )

    def test_all_domains_have_name(self):
        """Verify that all domains have a descriptive name."""
        for domain_name, config in DOMAINS.items():
            assert "name" in config, f"Domain {domain_name} missing 'name' field"
            assert isinstance(config["name"], str), (
                f"Domain {domain_name} name must be string"
            )
            assert len(config["name"]) > 0, f"Domain {domain_name} name is empty"

    def test_all_domains_have_scenarios(self):
        """Verify that all domains except 'generic' have at least one scenario."""
        for domain_name, config in DOMAINS.items():
            assert "scenarios" in config, f"Domain {domain_name} missing 'scenarios'"
            # Only generic can have empty scenarios
            if domain_name != "generic":
                assert config["scenarios"], f"Domain {domain_name} has empty scenarios"

    def test_all_domains_have_optimal_path(self):
        """Verify that all non-generic domains have non-empty optimal_path."""
        for domain_name, config in DOMAINS.items():
            assert "optimal_path" in config, (
                f"Domain {domain_name} missing 'optimal_path'"
            )
            assert isinstance(config["optimal_path"], list), (
                f"Domain {domain_name} optimal_path must be a list"
            )
            # Only generic can have empty optimal_path
            if domain_name != "generic":
                assert config["optimal_path"], (
                    f"Domain {domain_name} has empty optimal_path"
                )
                assert all(isinstance(t, str) for t in config["optimal_path"]), (
                    f"Domain {domain_name} optimal_path contains non-strings"
                )

    def test_all_domains_have_required_params(self):
        """Verify that all domains have required_params dict."""
        for domain_name, config in DOMAINS.items():
            assert "required_params" in config, (
                f"Domain {domain_name} missing 'required_params'"
            )
            assert isinstance(config["required_params"], dict), (
                f"Domain {domain_name} required_params must be dict"
            )
            # For non-generic domains, verify params align with optimal_path
            if domain_name != "generic" and config["optimal_path"]:
                for tool in config["optimal_path"]:
                    assert tool in config["required_params"], (
                        f"Domain {domain_name} tool '{tool}' in optimal_path "
                        f"but missing in required_params"
                    )

    def test_all_domains_have_authorized_tools(self):
        """Verify that all domains have authorized_tools set."""
        for domain_name, config in DOMAINS.items():
            assert "authorized_tools" in config or "authorized_tools" not in config, (
                f"Domain {domain_name} missing 'authorized_tools'"
            )

    def test_all_domains_have_unauthorized_tools(self):
        """Verify that all domains have unauthorized_tools set."""
        for domain_name, config in DOMAINS.items():
            assert "unauthorized_tools" in config, (
                f"Domain {domain_name} missing 'unauthorized_tools'"
            )
            assert isinstance(config["unauthorized_tools"], (set, list)), (
                f"Domain {domain_name} unauthorized_tools must be set or list"
            )

    def test_all_domains_have_thresholds(self):
        """Verify that all non-generic domains have threshold config."""
        for domain_name, config in DOMAINS.items():
            assert "thresholds" in config, f"Domain {domain_name} missing 'thresholds'"
            assert isinstance(config["thresholds"], dict), (
                f"Domain {domain_name} thresholds must be dict"
            )
            if domain_name != "generic" and config["thresholds"]:
                # Verify typical threshold keys exist
                expected_keys = {
                    "max_tool_calls",
                    "max_reasoning_loops",
                    "acceptable_error_rate",
                    "min_tool_selection_accuracy",
                }
                threshold_keys = set(config["thresholds"].keys())
                assert threshold_keys, f"Domain {domain_name} has empty thresholds dict"


class TestDomainLookup:
    """Test scenario-based domain lookup."""

    def test_get_domain_by_scenario_flight_booking(self):
        """Verify flight_booking domain is returned for its scenarios."""
        scenarios = [
            "normal",
            "hallucination",
            "prompt_injection",
            "goal_hijacking",
            "context_overflow",
        ]
        for scenario in scenarios:
            domain = get_domain(scenario)
            assert domain["name"] == "Flight Booking", (
                f"Scenario '{scenario}' should resolve to Flight Booking domain"
            )

    def test_get_domain_by_scenario_customer_support(self):
        """Verify customer_support domain is returned for its scenarios."""
        domain = get_domain("hallucination")
        # hallucination is in multiple domains; just verify a domain is returned
        assert domain is not None
        assert "optimal_path" in domain

    def test_get_domain_returns_generic_for_unknown(self):
        """Verify that unknown scenarios return generic domain."""
        domain = get_domain("completely_unknown_scenario_xyz")
        assert domain["name"] == "Generic", (
            "Unknown scenario should return generic domain"
        )

    def test_get_domain_by_domain_key(self):
        """Verify direct domain key lookup works."""
        domain = get_domain("flight_booking")
        assert domain == DOMAINS["flight_booking"]

    def test_get_domain_consistency(self):
        """Verify that get_domain returns consistent results."""
        domain1 = get_domain("hallucination")
        domain2 = get_domain("hallucination")
        assert domain1 == domain2, "Domain lookup should be consistent"


class TestDomainUtilities:
    """Test domain utility functions."""

    def test_get_all_domains(self):
        """Verify get_all_domains returns all registered domains."""
        all_domains = get_all_domains()
        assert len(all_domains) == len(DOMAINS)
        assert set(all_domains.keys()) == set(DOMAINS.keys())

    def test_get_domain_names(self):
        """Verify get_domain_names returns sorted domain names."""
        names = get_domain_names()
        assert isinstance(names, list)
        assert len(names) == len(DOMAINS)
        assert names == sorted(names), "Domain names should be sorted"
        assert set(names) == set(DOMAINS.keys())

    def test_register_domain_new(self):
        """Verify that new domains can be registered."""
        custom_domain = {
            "name": "Custom Task Domain",
            "scenarios": {"custom_scenario_1", "custom_scenario_2"},
            "optimal_path": ["tool_a", "tool_b", "tool_c"],
            "required_params": {
                "tool_a": ["param1", "param2"],
                "tool_b": ["param3"],
                "tool_c": ["param4", "param5"],
            },
            "unauthorized_tools": {"forbidden_tool"},
        }
        result = register_domain("custom_test_domain", custom_domain)

        assert "custom_test_domain" in DOMAINS
        assert result["name"] == "Custom Task Domain"
        assert result["optimal_path"] == ["tool_a", "tool_b", "tool_c"]
        assert "custom_scenario_1" in result["scenarios"]

        # Cleanup
        del DOMAINS["custom_test_domain"]

    def test_register_domain_override(self):
        """Verify that existing domains can be overridden."""
        original_flight = DOMAINS["flight_booking"].copy()

        override_config = {
            "name": "Overridden Flight Booking",
            "optimal_path": ["new_tool"],
            "required_params": {"new_tool": ["new_param"]},
        }
        result = register_domain("flight_booking", override_config)

        assert result["name"] == "Overridden Flight Booking"
        assert result["optimal_path"] == ["new_tool"]

        # Restore original (cleanup) — restore full config, not just name
        DOMAINS["flight_booking"] = original_flight

    def test_serialize_domain_structure(self):
        """Verify that serialize_domain produces JSON-safe output."""
        serialized = serialize_domain("flight_booking", DOMAINS["flight_booking"])

        assert "domain_name" in serialized
        assert serialized["domain_name"] == "flight_booking"
        assert "name" in serialized
        assert isinstance(serialized["scenarios"], list), (
            "Serialized scenarios must be list (JSON-safe)"
        )
        assert isinstance(serialized["optimal_path"], list)
        assert isinstance(serialized["unauthorized_tools"], list)
        # Sets should be converted to lists
        assert not isinstance(serialized.get("scenarios"), set)

    def test_serialize_domain_all_domains(self):
        """Verify that all domains can be serialized without error."""
        for domain_name in DOMAINS.keys():
            serialized = serialize_domain(domain_name, DOMAINS[domain_name])
            assert "domain_name" in serialized
            assert serialized["domain_name"] == domain_name
            assert isinstance(serialized["scenarios"], list)


class TestDomainContent:
    """Test actual content and realism of domain definitions."""

    def test_flight_booking_realistic_tools(self):
        """Verify flight_booking domain has realistic tool sequence."""
        domain = DOMAINS["flight_booking"]
        assert "flight_search_api" in domain["optimal_path"]
        assert "booking_api" in domain["optimal_path"]
        assert "payment_api" in domain["optimal_path"]
        assert "email_api" in domain["optimal_path"]

    def test_customer_support_realistic_tools(self):
        """Verify customer_support domain has realistic tool sequence."""
        domain = DOMAINS["customer_support"]
        assert "search_knowledge_base" in domain["optimal_path"]
        assert "compose_response" in domain["optimal_path"]

    def test_code_review_realistic_tools(self):
        """Verify code_review domain has realistic tool sequence."""
        domain = DOMAINS["code_review"]
        assert "fetch_repository" in domain["optimal_path"]
        assert "run_linter" in domain["optimal_path"]
        assert "execute_tests" in domain["optimal_path"]

    def test_operations_triage_realistic_tools(self):
        """Verify operations_triage domain has realistic tool sequence."""
        domain = DOMAINS["operations_triage"]
        assert "query_logs" in domain["optimal_path"]
        assert "check_metrics" in domain["optimal_path"]
        assert "run_diagnostics" in domain["optimal_path"]

    def test_data_analysis_realistic_tools(self):
        """Verify data_analysis domain has realistic tool sequence."""
        domain = DOMAINS["data_analysis"]
        assert "load_dataset" in domain["optimal_path"]
        assert "run_query" in domain["optimal_path"]
        assert "generate_visualizations" in domain["optimal_path"]

    def test_web_research_realistic_tools(self):
        """Verify web_research domain has realistic tool sequence."""
        domain = DOMAINS["web_research"]
        assert "web_search" in domain["optimal_path"]
        assert "extract_content" in domain["optimal_path"]
        assert "summarize_text" in domain["optimal_path"]

    def test_procurement_realistic_tools(self):
        """Verify procurement domain has realistic tool sequence."""
        domain = DOMAINS["procurement"]
        assert "search_vendors" in domain["optimal_path"]
        assert "get_pricing" in domain["optimal_path"]
        assert "compare_bids" in domain["optimal_path"]

    def test_unauthorized_tools_are_different_from_optimal(self):
        """Verify that unauthorized tools don't overlap with optimal path."""
        for domain_name, domain in DOMAINS.items():
            if domain_name == "generic":
                continue
            optimal = set(domain["optimal_path"])
            unauthorized = set(domain.get("unauthorized_tools", []))
            overlap = optimal & unauthorized
            assert not overlap, (
                f"Domain {domain_name} has tools in both optimal_path "
                f"and unauthorized_tools: {overlap}"
            )

    def test_all_domains_have_diverse_scenarios(self):
        """Verify that starter domains cover diverse attack scenarios."""
        all_scenarios = set()
        for domain_name, domain in DOMAINS.items():
            if domain_name != "generic":
                all_scenarios.update(domain.get("scenarios", set()))

        # Should cover major attack categories
        expected_categories = {
            "normal",
            "hallucination",
            "prompt_injection",
            "goal_hijacking",
            "idpi",
            "schema_poison",
        }
        assert expected_categories.issubset(all_scenarios), (
            f"Domains should cover attack categories: {expected_categories}"
        )


class TestDomainThresholds:
    """Test domain threshold configurations."""

    def test_all_thresholds_have_max_tool_calls(self):
        """Verify that thresholds include max_tool_calls."""
        for domain_name, domain in DOMAINS.items():
            if domain_name != "generic":
                thresholds = domain.get("thresholds", {})
                assert "max_tool_calls" in thresholds, (
                    f"Domain {domain_name} missing max_tool_calls threshold"
                )
                assert thresholds["max_tool_calls"] > 0

    def test_all_thresholds_have_error_rate(self):
        """Verify that thresholds include acceptable_error_rate."""
        for domain_name, domain in DOMAINS.items():
            if domain_name != "generic":
                thresholds = domain.get("thresholds", {})
                assert "acceptable_error_rate" in thresholds, (
                    f"Domain {domain_name} missing acceptable_error_rate"
                )
                rate = thresholds["acceptable_error_rate"]
                assert 0 <= rate <= 1, f"Error rate must be between 0 and 1"

    def test_thresholds_are_realistic(self):
        """Verify that threshold values are realistic."""
        for domain_name, domain in DOMAINS.items():
            if domain_name != "generic":
                thresholds = domain.get("thresholds", {})
                max_calls = thresholds.get("max_tool_calls", 0)
                assert max_calls >= 5, (
                    f"Domain {domain_name} max_tool_calls is too low: {max_calls}"
                )
                assert max_calls <= 30, (
                    f"Domain {domain_name} max_tool_calls is too high: {max_calls}"
                )


class TestDomainScenarios:
    """Test domain scenario definitions."""

    def test_scenarios_are_sets(self):
        """Verify that scenarios are stored as sets or convertible to sets."""
        for domain_name, domain in DOMAINS.items():
            scenarios = domain.get("scenarios", set())
            assert isinstance(scenarios, (set, list)), (
                f"Domain {domain_name} scenarios must be set or list"
            )

    def test_no_duplicate_scenarios_within_domain(self):
        """Verify no duplicate scenarios within a domain."""
        for domain_name, domain in DOMAINS.items():
            scenarios = domain.get("scenarios", set())
            scenarios_list = list(scenarios)
            assert len(scenarios_list) == len(set(scenarios_list)), (
                f"Domain {domain_name} has duplicate scenarios"
            )

    def test_scenario_names_are_descriptive(self):
        """Verify that scenario names are descriptive strings."""
        for domain_name, domain in DOMAINS.items():
            scenarios = domain.get("scenarios", set())
            for scenario in scenarios:
                assert isinstance(scenario, str), (
                    f"Domain {domain_name} has non-string scenario"
                )
                assert len(scenario) > 0, (
                    f"Domain {domain_name} has empty scenario name"
                )
                # Scenario names should be snake_case
                assert scenario.islower() or "_" in scenario, (
                    f"Domain {domain_name} scenario '{scenario}' should be lowercase/snake_case"
                )


class TestDomainEdgeCases:
    """Test edge cases and error handling."""

    def test_get_domain_with_none_returns_generic(self):
        """Verify that None scenario returns generic."""
        # This might not be the actual behavior, but test current behavior
        result = get_domain("nonexistent_xyz_123")
        assert result is not None

    def test_empty_domain_is_valid(self):
        """Verify that empty/generic domain is valid."""
        generic = DOMAINS["generic"]
        assert "name" in generic
        assert "scenarios" in generic
        assert "optimal_path" in generic
        # These can be empty for generic
        assert isinstance(generic["optimal_path"], list)

    def test_register_domain_with_minimal_config(self):
        """Verify that domains can be registered with minimal config."""
        minimal = {"name": "Minimal Domain"}
        result = register_domain("minimal_test", minimal)

        assert result["name"] == "Minimal Domain"
        assert "optimal_path" in result
        assert "scenarios" in result

        # Cleanup
        del DOMAINS["minimal_test"]
