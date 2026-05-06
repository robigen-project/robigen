"""
Model configurations for the Multi-Agent VLM Adversarial Testing System.

Defines supported models and their API configurations.
"""

MODELS = {
    "gemini": {
        "name": "Gemini",
        "provider": "google",
        "model_id": "gemini-2.5-flash",
        "env_key": "GOOGLE_API_KEY",
        "description": "Google's Gemini vision-language model"
    },
    "gpt": {
        "name": "GPT-4o",
        "provider": "openai",
        "model_id": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "description": "OpenAI's GPT-4o vision model"
    },
    "gemini-er": {
        "name": "Gemini Robotics-ER 1.5",
        "provider": "google",
        "model_id": "gemini-robotics-er-1.5-preview",
        "env_key": "GOOGLE_API_KEY",
        "description": "Google's robotics-specialized VLM with embodied reasoning"
    },
    "gemini-er-1.6": {
        "name": "Gemini Robotics-ER 1.6",
        "provider": "google",
        "model_id": "gemini-robotics-er-1.6-preview",
        "env_key": "GOOGLE_API_KEY",
        "description": "Google's robotics-specialized VLM with embodied reasoning (April 2026 release)"
    },
}

# List of valid model types for CLI validation
VALID_MODEL_TYPES = list(MODELS.keys())


def get_model_config(model_type: str) -> dict:
    """
    Retrieves the configuration for a specific model type.

    Args:
        model_type: One of 'gemini', 'gpt'

    Returns:
        Model configuration dictionary

    Raises:
        ValueError: If model_type is not recognized
    """
    if model_type not in MODELS:
        valid_models = ", ".join(MODELS.keys())
        raise ValueError(f"Unknown model type: '{model_type}'. Valid models: {valid_models}")
    return MODELS[model_type]
