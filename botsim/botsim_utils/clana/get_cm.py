#!/usr/bin/env python

"""Calculate the confusion matrix (CSV inputs)."""

#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

# Core Library
import csv
import numpy as np
from botsim import botsim_utils


def main(cm_dump_filepath: str, gt_filepath: str, n: int) -> None:
    """
    Calculate a confusion matrix.

    Parameters
    ----------
    cm_dump_filepath : str
        CSV file with delimter ; and quoting char "
        The first field is an identifier, the second one is the index of the
        predicted label
    gt_filepath : str
        CSV file with delimter ; and quoting char "
        The first field is an identifier, the second one is the index of the
        ground truth
    n : int
        Number of classes
    """
    cm = calculate_cm(cm_dump_filepath, gt_filepath, n)
    path = "cm.json"
    botsim_utils.clana.io.write_cm(path, cm)


def calculate_cm(cm_dump_filepath: str, gt_filepath: str, n: int) -> np.ndarray:
    """
    Calculate a confusion matrix.

    Parameters
    ----------
    cm_dump_filepath : str
        CSV file with delimter ; and quoting char "
        The first field is an identifier, the second one is the index of the
        predicted label
    gt_filepath : str
        CSV file with delimter ; and quoting char "
        The first field is an identifier, the second one is the index of the
        ground truth
    n : int
        Number of classes

    Returns
    -------
    confusion_matrix : numpy array (n x n)
    """
    cm = np.zeros((n, n), dtype=int)
    print(cm_dump_filepath, gt_filepath)

    # Read CSV files
    predictions = []
    with open(cm_dump_filepath,'r') as fp:
        reader = csv.reader(fp, delimiter=";", quotechar='"')
        predictions = list(reader)

    with open(gt_filepath) as fp:
        reader = csv.reader(fp, delimiter=";", quotechar='"')
        truths = list(reader)

    ident2truth_index = {}
    for identifier, truth_index in truths:
        ident2truth_index[identifier] = int(truth_index)

    if len(predictions) != len(truths):
        msg = 'len(predictions) = {} != {} = len(truths)"'.format(
            len(predictions), len(truths)
        )
        raise ValueError(msg)

    for ident, pred_index in predictions:
        cm[ident2truth_index[ident]][int(pred_index)] += 1

    return cm
