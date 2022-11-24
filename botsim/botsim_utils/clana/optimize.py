"""Optimize the column order of a confusion matrix."""

#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random
from typing import Callable, List, Optional, Tuple
from typing import NamedTuple

# Third party
import numpy as np


class OptimizationResult(NamedTuple):
    """The result of a matrix column/row order optimiataion (CMO)."""

    cm: np.ndarray
    perm: np.ndarray


def calculate_score(cm: np.ndarray, weights: np.ndarray) -> int:
    """
    Calculate a score how close big elements of cm are to the diagonal.

    Parameters
    ----------
    cm : np.ndarray
        The confusion matrix
    weights : np.ndarray
        The weights matrix.
        It has to have the same shape as the confusion matrix

    Examples
    --------
    >>> cm = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
    >>> weights = calculate_weight_matrix(3)
    >>> weights.shape
    (3, 3)
    >>> calculate_score(cm, weights)
    32
    """
    assert cm.shape == weights.shape
    return int(np.tensordot(cm, weights, axes=((0, 1), (0, 1))))


def simulated_annealing(
    current_cm: np.ndarray,
    current_perm: Optional[np.ndarray] = None,
    score: Callable[[np.ndarray, np.ndarray], float] = calculate_score,
    steps: int = 2 * 10 ** 5,
    temp: float = 100.0,
    cooling_factor: float = 0.99,
    deterministic: bool = False,
) -> OptimizationResult:
    """
    Optimize current_cm by randomly swapping elements.

    Parameters
    ----------
    current_cm : np.ndarray
    current_perm : None or iterable, optional (default: None)
    score: Callable[[np.ndarray, np.ndarray], float], optional
        (default: )
    steps : int, optional (default: 2 * 10**4)
    temp : float > 0.0, optional (default: 100.0)
        Temperature
    cooling_factor: float in (0, 1), optional (default: 0.99)

    Returns
    -------
    best_result : OptimizationResult
    """
    if temp <= 0.0:
        raise ValueError(f"temp={temp} needs to be positive")
    if cooling_factor <= 0.0 or cooling_factor >= 1.0:
        raise ValueError(
            "cooling_factor={} needs to be in the interval "
            "(0, 1)".format(cooling_factor)
        )
    n = len(current_cm)

    # Load the initial permutation
    if current_perm is None:
        current_perm = list(range(n))
    current_perm = np.array(current_perm)

    # Pre-calculate weights
    weights = calculate_weight_matrix(n)

    # Apply the permutation
    current_cm = apply_permutation(current_cm, current_perm)
    current_score = score(current_cm, weights)

    best_cm = current_cm
    best_score = current_score
    best_perm = current_perm

    for step in range(steps):
        tmp_cm = np.array(current_cm, copy=True)
        perm, make_swap = generate_permutation(n, current_perm, tmp_cm)
        tmp_score = score(tmp_cm, weights)

        # Should be swapped?
        if deterministic:
            chance = 1.0
        else:
            chance = random.random()
            temp *= 0.99
        hot_prob_thresh = min(1, np.exp(-(tmp_score - current_score) / temp))
        if chance <= hot_prob_thresh:
            changed = False
            if best_score > tmp_score:  # minimize
                best_perm = perm
                best_cm = tmp_cm
                best_score = tmp_score
                changed = True
            current_score = tmp_score
            current_cm = tmp_cm
            current_perm = perm
    return OptimizationResult(cm=best_cm, perm=best_perm)


def calculate_weight_matrix(n: int) -> np.ndarray:
    """
    Calculate the weights for each position.

    The weight is the distance to the diagonal.

    Parameters
    ----------
    n : int

    Examples
    --------
    >>> calculate_weight_matrix(3)
    array([[0.  , 1.01, 2.02],
           [1.01, 0.  , 1.03],
           [2.02, 1.03, 0.  ]])
    """
    weights = np.abs(np.arange(n) - np.arange(n)[:, None])
    weights = np.array(weights, dtype=np.float)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            weights[i][j] += (i + j) * 0.01
    return weights


def generate_permutation(
    n: int, current_perm: List[int], tmp_cm: np.ndarray
) -> Tuple[List[int], bool]:
    """
    Generate a new permutation.

    Parameters
    ----------
    n : int
    current_perm : List[int]
    tmp_cm : np.ndarray

    Return
    ------
    perm, make_swap : List[int], bool
    """
    swap_prob = 0.5
    make_swap = random.random() < swap_prob
    if n < 3:
        # In this case block-swaps don't make any sense
        make_swap = True
    if make_swap:
        # Choose what to swap
        i = random.randint(0, n - 1)
        j = i
        while j == i:
            j = random.randint(0, n - 1)
        # Define permutation
        perm = swap_1d(current_perm.copy(), i, j)
        # Define values after swap
        tmp_cm = swap(tmp_cm, i, j)
    else:
        # block-swap
        block_len = n
        while block_len >= n - 1:
            from_start = random.randint(0, n - 3)
            from_end = random.randint(from_start + 1, n - 2)
            block_len = from_start - from_end
        insert_pos = from_start
        while not (insert_pos < from_start or insert_pos > from_end):
            insert_pos = random.randint(0, n - 1)
        perm = move_1d(current_perm.copy(), from_start, from_end, insert_pos)

        # Define values after swap
        tmp_cm = move(tmp_cm, from_start, from_end, insert_pos)
    return perm, make_swap


def apply_permutation(cm: np.ndarray, perm: List[int]) -> np.ndarray:
    """
    Apply permutation to a matrix.

    Parameters
    ----------
    cm : ndarray
    perm : List[int]

    Examples
    --------
    >>> cm = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
    >>> perm = np.array([2, 0, 1])
    >>> apply_permutation(cm, perm)
    array([[8, 6, 7],
           [2, 0, 1],
           [5, 3, 4]])
    """
    return cm[perm].transpose()[perm].transpose()


def move_1d(
    perm: np.ndarray, from_start: int, from_end: int, insert_pos: int
) -> np.ndarray:
    """
    Move a block in a list.

    Parameters
    ----------
    perm : np.ndarray
        Permutation
    from_start : int
    from_end : int
    insert_pos : int

    Returns
    -------
    perm : np.ndarray
        The new permutation
    """
    if not (insert_pos < from_start or insert_pos > from_end):
        raise ValueError(
            "insert_pos={} needs to be smaller than from_start={}"
            " or greater than from_end={}".format(insert_pos, from_start, from_end)
        )
    if insert_pos > from_end:
        p_new = list(range(from_end + 1, insert_pos + 1)) + list(
            range(from_start, from_end + 1)
        )
    else:
        p_new = list(range(from_start, from_end + 1)) + list(
            range(insert_pos, from_start)
        )
    p_old = sorted(p_new)
    perm[p_old] = perm[p_new]
    return perm


def move(cm: np.ndarray, from_start: int, from_end: int, insert_pos: int) -> np.ndarray:
    """
    Move rows from_start - from_end to insert_pos in-place.

    Parameters
    ----------
    cm : np.ndarray
    from_start : int
    from_end : int
    insert_pos : int

    Returns
    -------
    cm : np.ndarray

    Examples
    --------
    >>> cm = np.array([[0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 0, 1], [2, 3, 4, 5]])
    >>> move(cm, 1, 2, 0)
    array([[5, 6, 4, 7],
           [9, 0, 8, 1],
           [1, 2, 0, 3],
           [3, 4, 2, 5]])
    """
    if not (insert_pos < from_start or insert_pos > from_end):
        raise ValueError(
            "insert_pos={} needs to be smaller than from_start={}"
            " or greater than from_end={}".format(insert_pos, from_start, from_end)
        )
    if insert_pos > from_end:
        p_new = list(range(from_end + 1, insert_pos + 1)) + list(
            range(from_start, from_end + 1)
        )
    else:
        p_new = list(range(from_start, from_end + 1)) + list(
            range(insert_pos, from_start)
        )
    p_old = sorted(p_new)
    # swap columns
    cm[:, p_old] = cm[:, p_new]
    # swap rows
    cm[p_old, :] = cm[p_new, :]
    return cm


def swap_1d(perm: np.ndarray, i: int, j: int) -> np.ndarray:
    """
    Swap two elements of a 1-D numpy array in-place.

    Parameters
    ----------
    parm : np.ndarray
    i : int
    j : int

    Examples
    --------
    >>> perm = np.array([2, 1, 2, 3, 4, 5, 6])
    >>> swap_1d(perm, 2, 6)
    array([2, 1, 6, 3, 4, 5, 2])
    """
    perm[i], perm[j] = perm[j], perm[i]
    return perm


def swap(cm: np.ndarray, i: int, j: int) -> np.ndarray:
    """
    Swap row and column i and j in-place.

    Parameters
    ----------
    cm : np.ndarray
    i : int
    j : int

    Returns
    -------
    cm : np.ndarray

    Examples
    --------
    >>> cm = np.array([[0, 1, 2], [3, 4, 5], [6, 7, 8]])
    >>> swap(cm, 2, 0)
    array([[8, 7, 6],
           [5, 4, 3],
           [2, 1, 0]])
    """
    # swap columns
    copy = cm[:, i].copy()
    cm[:, i] = cm[:, j]
    cm[:, j] = copy
    # swap rows
    copy = cm[i, :].copy()
    cm[i, :] = cm[j, :]
    cm[j, :] = copy
    return cm
