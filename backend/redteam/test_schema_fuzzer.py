"""
Test suite for SchemaFuzzer module.

This test file verifies that all fuzzing strategies work correctly
and that the SchemaFuzzer class behaves as expected.
"""

import pytest
from schema_fuzzer import FuzzStrategy, SchemaFuzzer


class TestFuzzStrategy:
    """Test the FuzzStrategy enum."""

    def test_all_strategies_exist(self):
        """Verify all 6 strategies are defined."""
        strategies = list(FuzzStrategy)
        assert len(strategies) == 6

    def test_strategy_values(self):
        """Verify strategy values are correct."""
        assert FuzzStrategy.REMOVE_REQUIRED_FIELD.value == "remove_required_field"
        assert FuzzStrategy.CHANGE_TYPE_CONSTRAINT.value == "change_type_constraint"
        assert (
            FuzzStrategy.ADD_CONTRADICTORY_CONSTRAINT.value
            == "add_contradictory_constraint"
        )
        assert FuzzStrategy.DUPLICATE_PROPERTY.value == "duplicate_property"
        assert FuzzStrategy.ADD_HIDDEN_FIELD.value == "add_hidden_field"
        assert FuzzStrategy.MAKE_CONFLICTING_ENUM.value == "make_conflicting_enum"


class TestSchemaFuzzerInit:
    """Test SchemaFuzzer initialization."""

    def test_init_with_seed(self):
        """Test initialization with a seed."""
        fuzzer = SchemaFuzzer(seed=42)
        assert fuzzer.seed == 42
        assert fuzzer.random_gen is not None

    def test_init_without_seed(self):
        """Test initialization without a seed."""
        fuzzer = SchemaFuzzer()
        assert fuzzer.seed is None
        assert fuzzer.random_gen is not None

    def test_reproducibility_with_seed(self):
        """Test that same seed produces same mutations."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        }

        fuzzer1 = SchemaFuzzer(seed=42)
        result1 = fuzzer1.fuzz_tool_schema(schema, FuzzStrategy.REMOVE_REQUIRED_FIELD)

        fuzzer2 = SchemaFuzzer(seed=42)
        result2 = fuzzer2.fuzz_tool_schema(schema, FuzzStrategy.REMOVE_REQUIRED_FIELD)

        assert result1 == result2


class TestFuzzToolSchema:
    """Test fuzz_tool_schema method."""

    def test_original_schema_unchanged(self):
        """Verify original schema is not modified."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        original = schema.copy()

        fuzzer = SchemaFuzzer()
        fuzzer.fuzz_tool_schema(schema, FuzzStrategy.REMOVE_REQUIRED_FIELD)

        assert schema == original

    def test_invalid_schema_raises_error(self):
        """Test that invalid schema raises ValueError."""
        fuzzer = SchemaFuzzer()
        with pytest.raises(ValueError):
            fuzzer.fuzz_tool_schema("not a dict", FuzzStrategy.REMOVE_REQUIRED_FIELD)

    def test_all_strategies_executable(self):
        """Test that all strategies can be executed."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        fuzzer = SchemaFuzzer()
        for strategy in FuzzStrategy:
            result = fuzzer.fuzz_tool_schema(schema, strategy)
            assert isinstance(result, dict)
            assert result is not schema

    def test_mutation_count(self):
        """Test that multiple mutations can be applied."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        fuzzer = SchemaFuzzer(seed=42)
        result = fuzzer.fuzz_tool_schema(
            schema, FuzzStrategy.REMOVE_REQUIRED_FIELD, mutation_count=3
        )

        assert isinstance(result, dict)


class TestGenerateFuzzedSchemas:
    """Test generate_fuzzed_schemas method."""

    def test_generates_correct_count(self):
        """Test that correct number of schemas are generated."""
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

        fuzzer = SchemaFuzzer()
        results = fuzzer.generate_fuzzed_schemas(schema, count=5)

        assert len(results) == 5

    def test_all_schemas_are_different_types(self):
        """Test that generated schemas are all dictionaries."""
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

        fuzzer = SchemaFuzzer()
        results = fuzzer.generate_fuzzed_schemas(schema, count=5)

        assert all(isinstance(s, dict) for s in results)

    def test_original_schema_unchanged(self):
        """Test that original schema is not modified."""
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}
        original = schema.copy()

        fuzzer = SchemaFuzzer()
        fuzzer.generate_fuzzed_schemas(schema, count=3)

        assert schema == original

    def test_negative_count_raises_error(self):
        """Test that negative count raises ValueError."""
        schema = {"type": "object", "properties": {}}

        fuzzer = SchemaFuzzer()
        with pytest.raises(ValueError):
            fuzzer.generate_fuzzed_schemas(schema, count=-1)

    def test_empty_strategies_raises_error(self):
        """Test that empty strategy list raises ValueError."""
        schema = {"type": "object", "properties": {}}

        fuzzer = SchemaFuzzer()
        with pytest.raises(ValueError):
            fuzzer.generate_fuzzed_schemas(schema, count=1, strategies=[])

    def test_specific_strategies(self):
        """Test generation with specific strategies."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        fuzzer = SchemaFuzzer()
        strategies = [FuzzStrategy.REMOVE_REQUIRED_FIELD, FuzzStrategy.ADD_HIDDEN_FIELD]
        results = fuzzer.generate_fuzzed_schemas(
            schema, count=10, strategies=strategies
        )

        assert len(results) == 10


class TestGenerateVariantsByStrategy:
    """Test generate_variants_by_strategy method."""

    def test_one_variant_per_strategy(self):
        """Test that exactly one variant is created per strategy."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }

        fuzzer = SchemaFuzzer()
        variants = fuzzer.generate_variants_by_strategy(schema)

        assert len(variants) == 6  # One per strategy

    def test_variant_keys_are_strategy_names(self):
        """Test that keys match strategy values."""
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

        fuzzer = SchemaFuzzer()
        variants = fuzzer.generate_variants_by_strategy(schema)

        expected_keys = {s.value for s in FuzzStrategy}
        assert set(variants.keys()) == expected_keys

    def test_all_variants_are_dicts(self):
        """Test that all variants are dictionaries."""
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

        fuzzer = SchemaFuzzer()
        variants = fuzzer.generate_variants_by_strategy(schema)

        assert all(isinstance(v, dict) for v in variants.values())

    def test_specific_strategies(self):
        """Test generation with specific strategies."""
        schema = {"type": "object", "properties": {"id": {"type": "integer"}}}

        fuzzer = SchemaFuzzer()
        strategies = [FuzzStrategy.ADD_HIDDEN_FIELD, FuzzStrategy.DUPLICATE_PROPERTY]
        variants = fuzzer.generate_variants_by_strategy(schema, strategies=strategies)

        assert len(variants) == 2


class TestFuzzRequiredFields:
    """Test fuzz_required_fields method."""

    def test_removes_fields_correctly(self):
        """Test that fields are removed from required list."""
        schema = {
            "type": "object",
            "required": ["name", "email", "age"],
            "properties": {"name": {}, "email": {}, "age": {}},
        }

        fuzzer = SchemaFuzzer()
        result = fuzzer.fuzz_required_fields(schema, n_removals=1)

        assert len(result["required"]) == 2
        assert result["required"] != schema["required"]

    def test_removes_multiple_fields(self):
        """Test removal of multiple fields."""
        schema = {
            "type": "object",
            "required": ["a", "b", "c", "d", "e"],
            "properties": {"a": {}, "b": {}, "c": {}, "d": {}, "e": {}},
        }

        fuzzer = SchemaFuzzer()
        result = fuzzer.fuzz_required_fields(schema, n_removals=3)

        assert len(result["required"]) == 2

    def test_no_required_field_returns_unchanged(self):
        """Test that schema without required field is returned unchanged."""
        schema = {"type": "object", "properties": {"name": {}}}

        fuzzer = SchemaFuzzer()
        result = fuzzer.fuzz_required_fields(schema, n_removals=1)

        assert result == schema

    def test_invalid_removal_count_raises_error(self):
        """Test that invalid removal count raises ValueError."""
        schema = {"type": "object", "required": ["name", "email"]}

        fuzzer = SchemaFuzzer()
        with pytest.raises(ValueError):
            fuzzer.fuzz_required_fields(schema, n_removals=5)

    def test_negative_removal_raises_error(self):
        """Test that negative removal count raises ValueError."""
        schema = {"type": "object", "required": ["name"]}

        fuzzer = SchemaFuzzer()
        with pytest.raises(ValueError):
            fuzzer.fuzz_required_fields(schema, n_removals=-1)

    def test_zero_removals_returns_unchanged(self):
        """Test that zero removals returns unchanged schema."""
        schema = {"type": "object", "required": ["name", "email"]}

        fuzzer = SchemaFuzzer()
        result = fuzzer.fuzz_required_fields(schema, n_removals=0)

        assert result["required"] == schema["required"]


class TestFuzzTypeConstraint:
    """Test fuzz_type_constraint method."""

    def test_changes_type_correctly(self):
        """Test that type is changed."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }

        fuzzer = SchemaFuzzer()
        result = fuzzer.fuzz_type_constraint(schema, "name")

        assert result["properties"]["name"]["type"] != "string"
        assert result["properties"]["name"]["type"] in [
            "integer",
            "number",
            "boolean",
            "array",
            "object",
        ]

    def test_invalid_property_raises_error(self):
        """Test that invalid property raises ValueError."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        fuzzer = SchemaFuzzer()
        with pytest.raises(ValueError):
            fuzzer.fuzz_type_constraint(schema, "nonexistent")

    def test_schema_without_properties_raises_error(self):
        """Test that schema without properties raises ValueError."""
        schema = {"type": "object"}

        fuzzer = SchemaFuzzer()
        with pytest.raises(ValueError):
            fuzzer.fuzz_type_constraint(schema, "name")

    def test_original_schema_unchanged(self):
        """Test that original schema is not modified."""
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        original = schema.copy()

        fuzzer = SchemaFuzzer()
        fuzzer.fuzz_type_constraint(schema, "name")

        assert schema == original


class TestResetSeed:
    """Test reset_seed method."""

    def test_reset_seed_changes_generator(self):
        """Test that resetting seed recreates generator."""
        fuzzer = SchemaFuzzer(seed=42)
        old_gen = fuzzer.random_gen

        fuzzer.reset_seed(100)

        assert fuzzer.seed == 100
        assert fuzzer.random_gen is not old_gen

    def test_reset_seed_to_none(self):
        """Test that seed can be reset to None."""
        fuzzer = SchemaFuzzer(seed=42)
        fuzzer.reset_seed(None)

        assert fuzzer.seed is None


class TestExportSchema:
    """Test export_schema method."""

    def test_export_pretty_json(self):
        """Test exporting schema as pretty JSON."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        fuzzer = SchemaFuzzer()
        result = fuzzer.export_schema(schema, pretty=True)

        assert isinstance(result, str)
        assert "\n" in result
        assert '"name"' in result

    def test_export_compact_json(self):
        """Test exporting schema as compact JSON."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        fuzzer = SchemaFuzzer()
        result = fuzzer.export_schema(schema, pretty=False)

        assert isinstance(result, str)
        assert '"name"' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
