#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, json
import numpy as np

from botsim.botsim_utils.utils import dump_json_to_file, dump_s3_file
import botsim.modules.remediator.remediator_utils.visualize_cm as visualize_cm



def calculate_confusion_matrix(predictions, ground_truth, num_classes):
    confusion_matrix = np.zeros((num_classes, num_classes), dtype=int)
    ident2truth_index = {}
    for identifier, truth_index in ground_truth:
        ident2truth_index[identifier] = int(truth_index)

    if len(predictions) != len(ground_truth):
        msg = "len(predictions) = {} != {} = len(ground_truth)".format(
            len(predictions), len(ground_truth))
        raise ValueError(msg)

    for ident, pred_index in predictions:
        confusion_matrix[ident2truth_index[ident]][int(pred_index)] += 1
    return confusion_matrix


def confusion_matrix_analyze(confusion_matrix, mode, result_dir):
    """
    Perform confusion matrix analysis and prepare the data for intent confusion matrix dashboard
    :param confusion_matrix: input confusion matrix
    :param mode: dev or eval
    :param result_dir: target directory for dumping the confusion matrix visualisation data
    """
    classes = {}
    ground_truth, prediction = [], []
    index, label_id = 0, 0
    labels = []
    for intent1 in confusion_matrix:
        if intent1 not in classes:
            classes[intent1] = label_id
            labels.append(intent1)
            label_id += 1
        for intent2 in confusion_matrix[intent1]:
            if intent2 not in classes:
                classes[intent2] = label_id
                label_id += 1
                labels.append(intent2)
            for _ in range(confusion_matrix[intent1][intent2]):
                ground_truth.append((index, classes[intent1]))
                prediction.append((index, classes[intent2]))
                index += 1

    labels.append("UNK")
    confusion_matrix = calculate_confusion_matrix(prediction, ground_truth, len(classes))
    path = result_dir + "cm_" + mode + ".json"
    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        dump_s3_file(path, bytes(json.dumps(confusion_matrix.tolist(),
                                            separators=(",", ": "),
                                            ensure_ascii=False).encode("UTF-8")))
    else:
        with open(path, "w") as outfile:
            outfile.write(json.dumps(confusion_matrix.tolist(), separators=(",", ": "), ensure_ascii=False))

    report = visualize_cm.cm_analysis_report(confusion_matrix, 100, labels, None)
    dump_json_to_file(result_dir + "cm_{}_report.json".format(mode), report)
