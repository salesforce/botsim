"""Everything about clustering classes of a confusion matrix."""
#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random
import numpy as np
from botsim.botsim_utils.clana.utils import load_cfg
cfg = load_cfg()
def apply_grouping(labels, grouping):
    """
    Return list of grouped labels.

    Parameters
    ----------
    labels : List[T]
    grouping : List[bool]

    Returns
    -------
    grouped_labels

    Examples
    --------
    >>> labels = ['de', 'en', 'fr']
    >>> grouping = [False, True]
    >>> apply_grouping(labels, grouping)
    [['de', 'en'], ['fr']]
    """
    groups = []
    current_group = [labels[0]]
    for label, cut in zip(labels[1:], grouping):
        if cut:
            groups.append(current_group)
            current_group = [label]
        else:
            current_group.append(label)
    groups.append(current_group)
    return groups


def _remove_single_element_groups(hierarchy):
    """
    Flatten sub-lists of length 1.

    Parameters
    ----------
    hierarchy : List[List]

    Returns
    -------
    hierarchy : list of el / lists

    Examples
    --------
    >>> hierarchy = [[0], [1, 2]]
    >>> _remove_single_element_groups(hierarchy)
    [0, [1, 2]]
    """
    h_new = []
    for el in hierarchy:
        if len(el) > 1:
            h_new.append(el)
        else:
            h_new.append(el[0])
    return h_new


def extract_clusters(
    cm,
    labels,
    steps = 10 ** 4,
    lambda_ = 0.013,
    method = "local-connectivity",
    interactive= False,
):
    """
    Find clusters in cm.

    Idea:
        mininmize lambda (error between clusters) - (count of clusters)
        s.t.: Each inter-cluster accuracy has to be lower than the overall
              accuracy

    Parameters
    ----------
    cm : np.ndarray
    labels : List[str]
    steps : int
    lambda_ : float
        The closer to 0, the more groups
        The bigger, the bigger groups
    method : {'local-connectivity', 'energy'}
    interactive : bool

    Returns
    -------
    clustes : List[bool]
    """
    if method == "energy":
        n = len(cm)
        grouping = np.zeros(n - 1)
        minimal_score = get_score(cm, grouping, lambda_)
        best_grouping = grouping.copy()
        for _ in range(steps):
            pos = random.randint(0, n - 2)
            grouping = best_grouping.copy()
            grouping[pos] = (grouping[pos] + 1) % 2
            current_score = get_score(cm, grouping, lambda_)
            if current_score < minimal_score:
                best_grouping = grouping
                minimal_score = current_score
    elif method == "local-connectivity":
        if interactive:
            thres = find_thres_interactive(cm, labels)
        else:
            thres = find_thres(cm, cfg["visualize"]["threshold"])
        best_grouping = split_at_con_thres(cm, thres, labels, interactive=interactive)
    else:
        raise NotImplementedError(f"method='{method}'")
    return best_grouping


def create_weight_matrix(grouping):
    """
    Create a matrix which contains the distance to the diagonal.

    Parameters
    ----------
    grouping : List[int]

    Returns
    -------
    weight_matrix : np.ndarray
        A symmetric matrix
    """
    n = len(grouping) + 1
    weight_matrix = np.zeros((n, n))
    for i in range(n):
        seen_1 = False
        for j in range(i + 1, n):
            if seen_1:
                weight_matrix[i][j] = 1
            elif grouping[j - 1] == 1:
                seen_1 = True
                weight_matrix[i][j] = 1
    return weight_matrix + weight_matrix.transpose()


def get_score(cm, grouping, lambda_):
    """
    Get the score of a confusion matrix.

    Parameters
    ----------
    cm : np.ndarray
    grouping : List[int]
    lambda_ : float

    Returns
    -------
    score : float
    """
    # First party
    from botsim.botsim_utils.clana.optimize import calculate_score

    inter_cluster_err = 0.0
    weights = create_weight_matrix(grouping)
    inter_cluster_err = calculate_score(cm, weights)
    return lambda_ * inter_cluster_err - sum(grouping)


def find_thres(cm, percentage):
    """
    Find a threshold for grouping.

    Parameters
    ----------
    cm : np.ndarray
    percentage : float
        Probability that two neighboring classes belong togehter

    Returns
    -------
    connectivity : float
    """
    n = int(len(cm) * (1.0 - percentage)) - 1
    con = sorted(get_neighboring_connectivity(cm))
    return con[n]


def find_thres_interactive(cm, labels):
    """
    Find a threshold for grouping.

    The threshold is the minimum connection strength for two classes to be
    within the same cluster.

    Parameters
    ----------
    cm : np.ndarray
    labels : List[str]

    Returns
    -------
    pos_str : float
    """
    n = len(cm)
    con = sorted(zip(get_neighboring_connectivity(cm), zip(range(n - 1), range(1, n))))
    # pos_low = 0
    pos_str = None

    # Lowest position from which we know that they are connected
    pos_up = n - 1

    # Highest position from which we know that they are not connected
    neg_low = 0
    # neg_up = n - 1
    while pos_up - 1 > neg_low:
        print(f"pos_up={pos_up}, neg_low={neg_low}, pos_str={pos_str}")
        pos = int((pos_up + neg_low) / 2)
        con_str, (i1, i2) = con[pos]
        should_be_conn = input(
            "Should {} and {} be in one cluster?"
            " (y/n): ".format(labels[i1], labels[i2])
        )
        if should_be_conn == "n":
            neg_low = pos
        elif should_be_conn == "y":
            pos_up = pos
            pos_str = con_str
        else:
            print(f"Please type only 'y' or 'n'. You typed {should_be_conn}.")
    assert pos_str is not None
    return pos_str


def get_neighboring_connectivity(cm):
    """
    Get how strong neighboring classes are connected.

    Parameters
    ----------
    cm : np.ndarray

    Returns
    -------
    con : List[float]
    """
    con = []
    n = len(cm)
    for i in range(n - 1):
        con.append(cm[i][i + 1] + cm[i + 1][i])
    return con


def split_at_con_thres(cm, thres, labels, interactive):
    """
    Two classes are not in the same group if they are not connected strong.

    Minimum connection strength is thres. The bigger this value, the more
    clusters / the smaller clusters you will get.
    """
    con = get_neighboring_connectivity(cm)
    grouping = []
    for i, el in enumerate(con):
        if el == thres and interactive:
            should_conn = "-"
            while should_conn not in ["y", "n"]:
                should_conn = input(
                    "Should {} and {} be in one "
                    "cluster? (y/n): ".format(labels[i], labels[i + 1])
                )
                if should_conn == "y":
                    grouping.append(False)
                elif should_conn == "n":
                    grouping.append(True)
                else:
                    print("please type either 'y' or 'n'")
        else:
            grouping.append(el < thres)
    return grouping
