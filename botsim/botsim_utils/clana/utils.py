"""Utility functions for clana."""

#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

# Core Library
import csv
import os
from typing import Any, Dict, List, Optional
import numpy as np
import yaml
from pkg_resources import resource_filename


def load_labels(labels_file: str, n: int) -> List[str]:
    """
    Load labels from a CSV file.

    Parameters
    ----------
    labels_file : str
    n : int

    Returns
    -------
    labels : List[str]
    """
    if n < 0:
        raise ValueError(f"n={n} needs to be non-negative")
    if os.path.isfile(labels_file):
        # Read CSV file
        with open(labels_file) as fp:
            reader = csv.reader(fp, delimiter=";", quotechar='"')
            next(reader, None)  # skip the headers
            parsed_csv = list(reader)
            labels = [el[0] for el in parsed_csv]  # short by default
    else:
        labels = [str(el) for el in range(n)]
    return labels


def load_cfg(
    yaml_filepath: Optional[str] = None, verbose: bool = False
) -> Dict[str, Any]:
    """
    Load a YAML configuration file.

    Parameters
    ----------
    yaml_filepath : str, optional (default: package config file)

    Returns
    -------
    cfg : Dict[str, Any]
    """
    if yaml_filepath is None:
        yaml_filepath = resource_filename("botsim.botsim_utils.clana", "config.yaml")
    # Read YAML experiment definition file
    if verbose:
        print(f"Load config from {yaml_filepath}...")
    with open(yaml_filepath) as stream:
        cfg = yaml.safe_load(stream)
    cfg = make_paths_absolute(os.path.dirname(yaml_filepath), cfg)
    return cfg


def make_paths_absolute(dir_: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Make all values for keys ending with `_path` absolute to dir_.

    Parameters
    ----------
    dir_ : str
    cfg : Dict[str, Any]

    Returns
    -------
    cfg : Dict[str, Any]
    """
    for key in cfg.keys():
        if hasattr(key, "endswith") and key.endswith("_path"):
            if cfg[key].startswith("~"):
                cfg[key] = os.path.expanduser(cfg[key])
            else:
                cfg[key] = os.path.join(dir_, cfg[key])
            cfg[key] = os.path.abspath(cfg[key])
        if type(cfg[key]) is dict:
            cfg[key] = make_paths_absolute(dir_, cfg[key])
    return cfg

def get_accuracy(cm: np.ndarray) -> float:
    """
    Get the accuracy by the confusion matrix cm.

    Parameters
    ----------
    cm : ndarray

    Returns
    -------
    accuracy : float
    """
    if cm.sum() == 0:
        return 1.0
    else:
        return float(sum(cm[i][i] for i in range(len(cm)))) / float(cm.sum())