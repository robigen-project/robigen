"""
Dataset registry for the Multi-Agent VLM Adversarial Testing System.

Maps dataset short names to their directory paths under images/.
"""

import os

DATASETS = {
    "droid": {
        "path": "images/droid",
        "description": "DROID — large-scale robot manipulation scenes"
    },
    "egothink": {
        "path": "images/egothink",
        "description": "EgoThink — egocentric viewpoint reasoning images"
    },
    "hope": {
        "path": "images/hope",
        "description": "HOPE dataset — household objects in multi-object tabletop scenes"
    },
    "robo2vlm": {
        "path": "images/robo2vlm",
        "description": "Robo2VLM — robotics-to-VLM evaluation images"
    },
    "robovqa": {
        "path": "images/robovqa",
        "description": "RoboVQA — visual question-answering scenes for robotics"
    },
}


def resolve_dataset_path(name_or_path: str) -> str:
    """
    Resolves a dataset name or raw path to an actual directory path.

    Args:
        name_or_path: Either a registered dataset name (e.g., 'hope', 'ocid')
                      or a direct path to a directory.

    Returns:
        Resolved directory path.
    """
    if name_or_path in DATASETS:
        return DATASETS[name_or_path]["path"]
    return name_or_path
