"""
Schema Fuzzer Module for Agent Robustness Testing

This module provides comprehensive schema mutation and fuzzing capabilities to test
agent robustness against malformed, contradictory, and edge-case JSON schemas.
"""

import json
import random
from copy import deepcopy
from enum import Enum
from typing import Any, Dict, List, Optional


class FuzzStrategy(Enum):
    """
    Enumeration of fuzzing strategies for schema mutation.

    Each strategy represents a different type of schema perturbation to test
    how agents handle various schema violations and edge cases.
    """

    REMOVE_REQUIRED_FIELD = "remove_required_field"
    """Remove fields from the required list to test optional field handling"""

    CHANGE_TYPE_CONSTRAINT = "change_type_constraint"
    """Modify type constraints to create type mismatches"""

    ADD_CONTRADICTORY_CONSTRAINT = "add_contradictory_constraint"
    """Add conflicting constraints (e.g., minLength > maxLength)"""

    DUPLICATE_PROPERTY = "duplicate_property"
    """Duplicate properties with conflicting definitions"""

    ADD_HIDDEN_FIELD = "add_hidden_field"
    """Add undocumented fields to the schema"""

    MAKE_CONFLICTING_ENUM = "make_conflicting_enum"
    """Create enum constraints with conflicting values"""


class SchemaFuzzer:
    """
    Fuzzer for generating mutated JSON schemas to test agent robustness.

    This class provides various methods to systematically introduce schema mutations
    that test how well agents handle edge cases, contradictions, and malformed schemas.

    Attributes:
        seed (Optional[int]): Random seed for reproducible fuzzing
        random_gen (random.Random): Random number generator instance
    """

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize the SchemaFuzzer.

        Args:
            seed (Optional[int]): Random seed for reproducible mutations.
                                 If None, uses system randomness.
        """
        self.seed = seed
        self.random_gen = random.Random(seed)

    def fuzz_tool_schema(
        self,
        original_schema: Dict[str, Any],
        strategy: FuzzStrategy,
        mutation_count: int = 1,
    ) -> Dict[str, Any]:
        """
        Apply a single fuzzing strategy to a schema with specified mutation count.

        This method creates a deep copy of the original schema and applies the
        specified fuzzing strategy to it a given number of times.

        Args:
            original_schema (Dict[str, Any]): The original JSON schema to fuzz
            strategy (FuzzStrategy): The fuzzing strategy to apply
            mutation_count (int): Number of times to apply the mutation (default: 1)

        Returns:
            Dict[str, Any]: A fuzzed copy of the schema with mutations applied

        Raises:
            ValueError: If the schema structure is invalid or strategy cannot be applied

        Example:
            >>> fuzzer = SchemaFuzzer(seed=42)
            >>> schema = {"type": "object", "properties": {"name": {"type": "string"}}}
            >>> fuzzed = fuzzer.fuzz_tool_schema(schema, FuzzStrategy.REMOVE_REQUIRED_FIELD)
        """
        if not isinstance(original_schema, dict):
            raise ValueError("Schema must be a dictionary")

        fuzzed_schema = deepcopy(original_schema)

        for _ in range(mutation_count):
            if strategy == FuzzStrategy.REMOVE_REQUIRED_FIELD:
                fuzzed_schema = self.fuzz_required_fields(fuzzed_schema, n_removals=1)
            elif strategy == FuzzStrategy.CHANGE_TYPE_CONSTRAINT:
                fuzzed_schema = self._apply_type_constraint_change(fuzzed_schema)
            elif strategy == FuzzStrategy.ADD_CONTRADICTORY_CONSTRAINT:
                fuzzed_schema = self._apply_contradictory_constraint(fuzzed_schema)
            elif strategy == FuzzStrategy.DUPLICATE_PROPERTY:
                fuzzed_schema = self._apply_duplicate_property(fuzzed_schema)
            elif strategy == FuzzStrategy.ADD_HIDDEN_FIELD:
                fuzzed_schema = self._apply_hidden_field(fuzzed_schema)
            elif strategy == FuzzStrategy.MAKE_CONFLICTING_ENUM:
                fuzzed_schema = self._apply_conflicting_enum(fuzzed_schema)

        return fuzzed_schema

    def generate_fuzzed_schemas(
        self,
        original_schema: Dict[str, Any],
        count: int,
        strategies: Optional[List[FuzzStrategy]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Generate N mutated schema variants using a pool of strategies.

        This method creates multiple fuzzed schemas by randomly selecting from
        the provided strategies. Useful for generating diverse test cases.

        Args:
            original_schema (Dict[str, Any]): The original JSON schema to fuzz
            count (int): Number of fuzzed schemas to generate
            strategies (Optional[List[FuzzStrategy]]): List of strategies to use.
                                                      If None, uses all strategies.

        Returns:
            List[Dict[str, Any]]: List of count fuzzed schema variants

        Example:
            >>> fuzzer = SchemaFuzzer(seed=42)
            >>> schema = {"type": "object", "properties": {"name": {"type": "string"}}}
            >>> fuzzed_schemas = fuzzer.generate_fuzzed_schemas(schema, count=5)
            >>> print(len(fuzzed_schemas))
            5
        """
        if count < 0:
            raise ValueError("Count must be non-negative")

        if strategies is None:
            strategies = list(FuzzStrategy)

        if not strategies:
            raise ValueError("At least one strategy must be provided")

        fuzzed_schemas = []
        for _ in range(count):
            strategy = self.random_gen.choice(strategies)
            fuzzed_schema = self.fuzz_tool_schema(
                original_schema, strategy, mutation_count=1
            )
            fuzzed_schemas.append(fuzzed_schema)

        return fuzzed_schemas

    def generate_variants_by_strategy(
        self,
        original_schema: Dict[str, Any],
        strategies: Optional[List[FuzzStrategy]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Generate exactly one variant per strategy.

        This method is useful for systematic testing where you want one example
        of each type of mutation to ensure all strategies are covered.

        Args:
            original_schema (Dict[str, Any]): The original JSON schema to fuzz
            strategies (Optional[List[FuzzStrategy]]): List of strategies to use.
                                                      If None, uses all strategies.

        Returns:
            Dict[str, Dict[str, Any]]: Dictionary mapping strategy name to fuzzed schema

        Example:
            >>> fuzzer = SchemaFuzzer(seed=42)
            >>> schema = {"type": "object", "properties": {"name": {"type": "string"}}}
            >>> variants = fuzzer.generate_variants_by_strategy(schema)
            >>> print(len(variants))
            6
            >>> print("remove_required_field" in variants)
            True
        """
        if strategies is None:
            strategies = list(FuzzStrategy)

        variants = {}
        for strategy in strategies:
            fuzzed_schema = self.fuzz_tool_schema(
                original_schema, strategy, mutation_count=1
            )
            variants[strategy.value] = fuzzed_schema

        return variants

    def fuzz_required_fields(
        self, original_schema: Dict[str, Any], n_removals: int = 1
    ) -> Dict[str, Any]:
        """
        Remove N fields from the required list.

        This mutation tests whether agents handle optional fields correctly by
        removing fields from the required constraint.

        Args:
            original_schema (Dict[str, Any]): The original JSON schema
            n_removals (int): Number of required fields to remove (default: 1)

        Returns:
            Dict[str, Any]: Schema with N fields removed from required list

        Raises:
            ValueError: If n_removals is negative or greater than required fields count

        Example:
            >>> fuzzer = SchemaFuzzer()
            >>> schema = {
            ...     "type": "object",
            ...     "required": ["name", "email", "age"],
            ...     "properties": {"name": {}, "email": {}, "age": {}}
            ... }
            >>> fuzzed = fuzzer.fuzz_required_fields(schema, n_removals=1)
            >>> len(fuzzed["required"]) == 2
            True
        """
        fuzzed_schema = deepcopy(original_schema)

        if "required" not in fuzzed_schema:
            return fuzzed_schema

        if not isinstance(fuzzed_schema["required"], list):
            return fuzzed_schema

        required_fields = fuzzed_schema["required"]

        if n_removals < 0:
            raise ValueError("n_removals must be non-negative")

        if n_removals > len(required_fields):
            raise ValueError(
                f"Cannot remove {n_removals} fields; only {len(required_fields)} required fields exist"
            )

        if n_removals == 0:
            return fuzzed_schema

        # Select random fields to remove
        fields_to_remove = self.random_gen.sample(required_fields, n_removals)
        fuzzed_schema["required"] = [
            f for f in required_fields if f not in fields_to_remove
        ]

        return fuzzed_schema

    def fuzz_type_constraint(
        self, original_schema: Dict[str, Any], property_name: str
    ) -> Dict[str, Any]:
        """
        Change the type constraint of a specific property.

        This mutation tests whether agents validate type constraints correctly by
        changing a property's type to an incompatible one.

        Args:
            original_schema (Dict[str, Any]): The original JSON schema
            property_name (str): Name of the property to modify

        Returns:
            Dict[str, Any]: Schema with modified type constraint

        Raises:
            ValueError: If property_name doesn't exist in properties

        Example:
            >>> fuzzer = SchemaFuzzer()
            >>> schema = {
            ...     "type": "object",
            ...     "properties": {"name": {"type": "string"}, "age": {"type": "integer"}}
            ... }
            >>> fuzzed = fuzzer.fuzz_type_constraint(schema, "name")
            >>> fuzzed["properties"]["name"]["type"] in ["integer", "boolean", "array"]
            True
        """
        fuzzed_schema = deepcopy(original_schema)

        if "properties" not in fuzzed_schema:
            raise ValueError("Schema has no properties")

        if property_name not in fuzzed_schema["properties"]:
            raise ValueError(f"Property '{property_name}' not found in schema")

        available_types = ["string", "integer", "number", "boolean", "array", "object"]
        current_type = fuzzed_schema["properties"][property_name].get("type")

        # Choose a different type
        alternative_types = [t for t in available_types if t != current_type]
        new_type = self.random_gen.choice(alternative_types)

        fuzzed_schema["properties"][property_name]["type"] = new_type

        return fuzzed_schema

    def _apply_type_constraint_change(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal method to apply type constraint changes.

        Args:
            schema (Dict[str, Any]): Schema to mutate

        Returns:
            Dict[str, Any]: Mutated schema
        """
        if "properties" not in schema or not schema["properties"]:
            return schema

        property_name = self.random_gen.choice(list(schema["properties"].keys()))
        return self.fuzz_type_constraint(schema, property_name)

    def _apply_contradictory_constraint(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal method to add contradictory constraints.

        Adds impossible constraints like minLength > maxLength to test error handling.

        Args:
            schema (Dict[str, Any]): Schema to mutate

        Returns:
            Dict[str, Any]: Mutated schema
        """
        fuzzed_schema = deepcopy(schema)

        if "properties" not in fuzzed_schema or not fuzzed_schema["properties"]:
            return fuzzed_schema

        # Select a random property
        property_name = self.random_gen.choice(list(fuzzed_schema["properties"].keys()))
        prop = fuzzed_schema["properties"][property_name]

        # Add contradictory constraints based on type
        if prop.get("type") == "string":
            prop["minLength"] = 100
            prop["maxLength"] = 10
        elif prop.get("type") == "number":
            prop["minimum"] = 100
            prop["maximum"] = 10
        elif prop.get("type") == "array":
            prop["minItems"] = 100
            prop["maxItems"] = 10

        return fuzzed_schema

    def _apply_duplicate_property(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal method to duplicate properties with conflicting definitions.

        Args:
            schema (Dict[str, Any]): Schema to mutate

        Returns:
            Dict[str, Any]: Mutated schema
        """
        fuzzed_schema = deepcopy(schema)

        if "properties" not in fuzzed_schema or not fuzzed_schema["properties"]:
            return fuzzed_schema

        # Select a random property to duplicate
        original_prop_name = self.random_gen.choice(
            list(fuzzed_schema["properties"].keys())
        )
        original_prop = fuzzed_schema["properties"][original_prop_name]

        # Create a conflicting copy with a modified type
        duplicate_name = f"{original_prop_name}_dup"
        duplicate_prop = deepcopy(original_prop)

        available_types = ["string", "integer", "number", "boolean", "array", "object"]
        current_type = duplicate_prop.get("type", "string")
        alternative_types = [t for t in available_types if t != current_type]

        if alternative_types:
            duplicate_prop["type"] = self.random_gen.choice(alternative_types)

        fuzzed_schema["properties"][duplicate_name] = duplicate_prop

        return fuzzed_schema

    def _apply_hidden_field(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal method to add undocumented fields to the schema.

        Args:
            schema (Dict[str, Any]): Schema to mutate

        Returns:
            Dict[str, Any]: Mutated schema
        """
        fuzzed_schema = deepcopy(schema)

        if "properties" not in fuzzed_schema:
            fuzzed_schema["properties"] = {}

        # Generate a hidden field name
        hidden_field_names = [
            "_internal",
            "__secret",
            "_hidden",
            "__debug",
            "_meta",
            "__proto__",
            "constructor",
            "_id",
            "_version",
        ]

        hidden_field_name = self.random_gen.choice(hidden_field_names)

        # Avoid overwriting existing properties
        counter = 0
        while hidden_field_name in fuzzed_schema["properties"]:
            hidden_field_name = f"{hidden_field_name}_{counter}"
            counter += 1

        # Add the hidden field with a random type
        hidden_field_type = self.random_gen.choice(
            ["string", "integer", "boolean", "object", "array"]
        )

        fuzzed_schema["properties"][hidden_field_name] = {
            "type": hidden_field_type,
            "description": "Hidden field added for testing",
        }

        return fuzzed_schema

    def _apply_conflicting_enum(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Internal method to create enum constraints with conflicting values.

        Args:
            schema (Dict[str, Any]): Schema to mutate

        Returns:
            Dict[str, Any]: Mutated schema
        """
        fuzzed_schema = deepcopy(schema)

        if "properties" not in fuzzed_schema or not fuzzed_schema["properties"]:
            return fuzzed_schema

        # Select a random property
        property_name = self.random_gen.choice(list(fuzzed_schema["properties"].keys()))
        prop = fuzzed_schema["properties"][property_name]

        # Add enum with conflicting values
        prop["enum"] = ["value1", "value2", "value3"]

        # Add a different constraint that might conflict
        if prop.get("type") == "string":
            prop["minLength"] = 50
        elif prop.get("type") == "integer":
            prop["minimum"] = 1000
            prop["maximum"] = 2000

        return fuzzed_schema

    def reset_seed(self, seed: Optional[int] = None) -> None:
        """
        Reset the random seed for reproducibility.

        Args:
            seed (Optional[int]): New seed value. If None, uses no seed.
        """
        self.seed = seed
        self.random_gen = random.Random(seed)

    def export_schema(self, schema: Dict[str, Any], pretty: bool = True) -> str:
        """
        Export schema as formatted JSON string.

        Args:
            schema (Dict[str, Any]): Schema to export
            pretty (bool): Whether to pretty-print the JSON (default: True)

        Returns:
            str: JSON string representation of the schema
        """
        if pretty:
            return json.dumps(schema, indent=2)
        else:
            return json.dumps(schema)
