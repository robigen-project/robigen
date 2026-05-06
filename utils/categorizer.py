"""
Auto-categorizer for successful adversarial attacks.

Classifies attacks into failure categories based on the action agent's
output fields (op, object, falsification_logic, location_description).
"""

import json
from config.failure_categories import FAILURE_CATEGORIES


def categorize_attack(action_json: dict) -> list[str]:
    """
    Categorize an attack based on the action agent's output.

    Args:
        action_json: The action JSON from the action agent containing
                    op, object, properties.falsification_logic, etc.

    Returns:
        List of matching category keys (e.g., ["transparent_object", "physical_constraint"])
    """
    # Extract searchable text from the action JSON
    searchable_parts = []

    searchable_parts.append(action_json.get("op", ""))
    searchable_parts.append(action_json.get("object", ""))
    searchable_parts.append(action_json.get("location_description", ""))

    properties = action_json.get("properties", {})
    if isinstance(properties, dict):
        searchable_parts.append(properties.get("material", ""))
        searchable_parts.append(properties.get("color", ""))
        searchable_parts.append(properties.get("relation_to_target", ""))
        searchable_parts.append(properties.get("falsification_logic", ""))

    # Combine all text for keyword matching
    combined_text = " ".join(str(p) for p in searchable_parts).lower()

    # Match against categories
    matched_categories = []
    for category_key, category_info in FAILURE_CATEGORIES.items():
        for keyword in category_info["keywords"]:
            if keyword.lower() in combined_text:
                matched_categories.append(category_key)
                break  # One keyword match is enough per category

    # If nothing matched, use a generic category
    if not matched_categories:
        matched_categories.append("uncategorized")

    return matched_categories


def get_category_names(category_keys: list[str]) -> list[str]:
    """Convert category keys to human-readable names."""
    names = []
    for key in category_keys:
        if key in FAILURE_CATEGORIES:
            names.append(FAILURE_CATEGORIES[key]["name"])
        else:
            names.append(key.replace("_", " ").title())
    return names
