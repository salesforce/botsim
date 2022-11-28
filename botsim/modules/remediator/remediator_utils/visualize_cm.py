#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

"""
The code is adapted from the clana library: https://github.com/MartinThoma/clana
For confusion matrix visualisation. The raw confusion matrix data is computed by
the remediator and provided here for visualisation purpose only.
"""
import json, math

from botsim import botsim_utils
import botsim.botsim_utils.clana.io
import botsim.botsim_utils.clana.utils
from botsim.botsim_utils.clana.optimize import (
    calculate_score,
    simulated_annealing,
)
import botsim.botsim_utils.clana.clustering as clana_clustering
cfg = botsim_utils.clana.utils.load_cfg()


def cm_analysis_report(
        confusion_matrix,
        steps,
        labels,
        limit_classes=None
):
    """
    Run optimization and generate output.
    @param confusion_matrix
    @param steps: number of optimization steps
    @param labels: list of labels
    @param limit_classes: limit number of classes for analyse
    """

    n, m = confusion_matrix.shape
    perm = range(n)
    if n != m:
        raise ValueError(
            f"Confusion matrix is expected to be square, but was {n} x {m}"
        )
    if len(labels) - 1 != n:
        print(
            "Confusion matrix is {n} x {n}, but len(labels)={nb_labels}".format(
                n=n, nb_labels=len(labels)
            )
        )

    return_json = {}
    cm_orig = confusion_matrix.copy()

    acc = botsim.botsim_utils.clana.utils.get_accuracy(cm_orig)
    if int(acc) == 1:
        perm = range(1)
        labels = [labels[i] for i in perm]
        class_indices = list(range(len(labels)))
        class_indices = [class_indices[i] for i in perm]
        cm = cm_orig
        # return
    else:
        # get_cm_problems(confusion_matrix, labels)
        # weights = calculate_weight_matrix(len(confusion_matrix))
        # print("Score: {}".format(calculate_score(confusion_matrix, weights)))
        # print(confusion_matrix)
        result = simulated_annealing(
            confusion_matrix, perm, score=calculate_score, deterministic=True, steps=steps
        )
        # print("Score: {}".format(calculate_score(result.cm, weights)))
        # print("Perm: {}".format(list(result.perm)))
        # clana.io.ClanaCfg.store_permutation(cm_file, result.perm, steps)
        labels = [labels[i] for i in result.perm]
        class_indices = list(range(len(labels)))
        class_indices = [class_indices[i] for i in result.perm]
        acc = botsim.botsim_utils.clana.utils.get_accuracy(cm_orig)
        cm = result.cm
    return_json["Accuracy"] = "{:0.2f}%".format(acc * 100)
    print("Accuracy: {:0.2f}%".format(acc * 100))
    start = 0
    if limit_classes is None:
        limit_classes = len(confusion_matrix)
    if len(confusion_matrix) < 3:
        print(
            "You only have {} classes. Clustering for less than 3 classes "
            "should be done manually.".format(len(confusion_matrix))
        )

    else:
        grouping = clana_clustering.extract_clusters(cm, labels)
        y_pred = [0]
        cluster_i = 0
        for el in grouping:
            if el:
                cluster_i += 1
            y_pred.append(cluster_i)
        with open(cfg["visualize"]["hierarchy_path"], "w") as outfile:
            hierarchy = clana_clustering.apply_grouping(class_indices, grouping)
            hierarchy_mixed = clana_clustering._remove_single_element_groups(hierarchy)
            str_ = json.dumps(
                hierarchy_mixed,
                indent=4,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            outfile.write(str_)

        # Print nice
        return_json["clusters"] = []
        for group in clana_clustering.apply_grouping(labels, grouping):
            print("\t{}: {}".format(len(group), list(group)))
            grp = {"size": len(group), "intents": list(group)}
            if len(group) > 1:
                grp["remediation"] = "Resolve confusions among intents in the group"
            else:
                grp["remediation"] = ""
            return_json["clusters"].append(grp)

    header_cell, body_row, recall, precision, F1 = \
        compute_cm_json(
            cm[start:limit_classes, start:limit_classes],
            labels=labels[start:limit_classes]
        )
    return_json["cm_table"] = {}
    return_json["cm_table"]["header_cell"] = header_cell
    return_json["cm_table"]["body_row"] = body_row
    return_json["recall"] = recall
    return_json["precision"] = precision
    return_json["F1"] = F1
    return return_json


def compute_cm_json(cm, labels):
    """
    Plot a confusion matrix.
    @param cm: confusion matrix
    @param labels: list of labels. If this is not given, then numbers are assigned to the classes
    """
    if labels is None:
        labels = [str(i) for i in range(len(cm))]
    el_max = 20000

    recall_score = {}
    precision_score = {}
    F1_score = {}
    cm_t = cm.transpose()
    header_cells = []
    for i, label in enumerate(labels):
        if sum(cm_t[i]) == 0:
            precision = 0
        else:
            precision = cm[i][i] / float(sum(cm_t[i]))
            precision_score[label] = precision
        background_color = "transparent"
        if precision < 0.2:
            background_color = "red"
        elif precision > 0.98:
            background_color = "green"
        header_cells.append(
            {
                "precision": f"{precision:0.2f}",
                "background-color": background_color,
                "label": label,
            }
        )

    body_rows = []
    for i, label, row in zip(range(len(labels)), labels, cm):
        body_row = []
        row_str = [str(el) for el in row]
        support = int(sum(row))
        if support == 0:
            recall = 0
        else:
            recall = cm[i][i] / float(support)
        if label in precision_score:
            recall_score[label] = recall
            f1 = 2 * recall * precision_score[label] / (recall + precision_score[label])
            if math.isnan(f1):
                f1 = 0.0
            F1_score[label] = f1
        background_color = "transparent"
        if recall < 0.2:
            background_color = "red"
        elif recall >= 0.98:
            background_color = "green"
        body_row.append(
            {
                "label": label,
                "recall": f"{recall:.2f}",
                "background-color": background_color,
            }
        )
        for _j, pred_label, el in zip(range(len(labels)), labels, row_str):
            background_color = "transparent"
            if el == "0":
                el = ""
            else:
                background_color = get_color_code(float(el), el_max)

            body_row.append(
                {
                    "label": el,
                    "ground_truth": label,
                    "prediction": pred_label,
                    "background-color": background_color,
                }
            )

        body_rows.append({"row": body_row, "support": support})

    ## classes ordered  by descending precision
    recall_sorted = sorted(recall_score.items(), key=lambda x: x[1], reverse=True)
    precision_sorted = sorted(precision_score.items(), key=lambda x: x[1], reverse=True)
    F1_sorted = sorted(F1_score.items(), key=lambda x: x[1], reverse=True)

    return header_cells, body_rows, recall_sorted, precision_sorted, F1_sorted


def get_color(white_to_black):
    """
    Get grayscale color.
    @param white_to_black: scale from white to black (0 to 1)
    """
    if not (0 <= white_to_black <= 1):
        raise ValueError("white_to_black={} is not in the interval [0, 1]")
    index = 255 - int(255 * white_to_black)
    r, g, b = index, index, index
    return int(r), int(g), int(b)


def get_color_code(val, max_val):
    """
    Get a HTML color code which is between 0 and max_val.
    @param val
    @param max_val: max value of the HTML color code
    """
    value = min(1.0, float(val) / max_val)
    r, g, b = get_color(value)
    return f"#{r:02x}{g:02x}{b:02x}"
