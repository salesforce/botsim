#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, json
import numpy as np
from botsim.botsim_utils.utils import (
    read_s3_json,
    dump_s3_file,
    file_exists,
    read_s3_data,
    convert_list_to_dict,
    S3_BUCKET_NAME)
from sentence_transformers import SentenceTransformer


def color_cell(val, threshold=60):
    color = "black"
    if val < threshold:
        color = "red"
    elif val >= 90:
        color = "green"
    return f"color: {color}"


def extract_sentence_transformer_embedding(sentence_transformer, utterances, intent):
    embedding = sentence_transformer.encode(utterances, convert_to_tensor=True)
    labels = [intent] * embedding.shape[0]
    return embedding, labels


def get_embedding(intents, database, test_id="169", paraphrase=False, para_setting="20_20"):
    config = dict(database.get_one_bot_test_instance(test_id))
    goals_dir = "data/bots/{}/{}/goals_dir".format(config["type"], test_id)
    dev_embedding, dev_labels = np.empty((0, 384)), {"label": []}

    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        if file_exists(S3_BUCKET_NAME, goals_dir + "/dev_embedding.npy") and \
                file_exists(S3_BUCKET_NAME, goals_dir + "/dev_embedding_label.npy"):
            dev_embedding = np.frombuffer(read_s3_data(S3_BUCKET_NAME, goals_dir + "/dev_embedding.npy")).reshape(-1,
                                                                                                                  384)
            dev_labels = read_s3_json(S3_BUCKET_NAME, goals_dir + "/dev_embedding_label.npy")["label"]
            return dev_embedding, dev_labels
    else:
        if os.path.exists(goals_dir + "/dev_embedding.npy"):
            with open(goals_dir + "/dev_embedding.npy", "rb") as f:
                dev_embedding = np.load(f)
            with  open(goals_dir + "/dev_embedding_label.npy", "rb") as f:
                dev_labels = np.load(f, allow_pickle=True)
            return dev_embedding, dev_labels.item().get("label")

    sentence_transformer = SentenceTransformer("paraphrase-MiniLM-L6-v2")
    for i, intent in enumerate(intents):
        file_name = goals_dir + "/" + intent + "_" + para_setting + ".paraphrases.json"
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            if not file_exists(S3_BUCKET_NAME, file_name):
                paraphrase = False
                file_name = goals_dir + "/" + intent + ".json"
                utterances = read_s3_json(S3_BUCKET_NAME, file_name)[intent]
            else:
                print("processing", intent)
                paras = read_s3_json(S3_BUCKET_NAME, file_name)
                utterances = []
                for p in paras:
                    utterances.append(p["source"])
                    if paraphrase:
                        utterances.extend(p["cands"])
        else:
            if not os.path.exists(file_name):
                paraphrase = False
                file_name = goals_dir + "/" + intent + ".json"
                utterances = json.load(open(file_name))[intent]
            else:
                paras = json.load(open(file_name))
                utterances = []
                for p in paras:
                    utterances.append(p["source"])
                    if paraphrase:
                        utterances.extend(p["cands"])

        embedding, labels = extract_sentence_transformer_embedding(sentence_transformer, utterances, intent)
        dev_embedding = np.concatenate((dev_embedding, embedding))
        dev_labels["label"].extend([intent] * embedding.shape[0])

    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        dump_s3_file(goals_dir + "/dev_embedding.npy", dev_embedding.tobytes())
        dump_s3_file(goals_dir + "/dev_embedding_label.npy", bytes(json.dumps(dev_labels, indent=2).encode("UTF-8")))
    else:
        with open(goals_dir + "/dev_embedding.npy", "wb") as f:
            np.save(f, dev_embedding, allow_pickle=False)
        with  open(goals_dir + "/dev_embedding_label.npy", "wb") as f:
            np.save(f, dev_labels, allow_pickle=True)

    return dev_embedding, dev_labels.get("label")


def get_number_dialogs(overall_performance, mode):
    data = overall_performance[mode.lower()]
    num_dialogs = 0
    num_success_dialogs = 0
    intent_to_errors = {}
    for intent in data:
        for p in data[intent]["intent_predictions"]:
            num_dialogs += data[intent]["intent_predictions"][p]
        num_success_dialogs += data[intent]["overall_performance"]["Success"]
        intent_to_errors[intent] = (data[intent]["overall_performance"]["Success"],
                                    data[intent]["overall_performance"]["Intent Error"],
                                    data[intent]["overall_performance"]["NER Error"],
                                    data[intent]["overall_performance"]["Other Error"])
    return num_dialogs, num_success_dialogs, intent_to_errors


def get_bot_health_reports(database, test_id):
    config = dict(database.get_one_bot_test_instance(test_id))
    report_path = "data/bots/{}/{}/aggregated_report.json".format(config["type"], test_id)

    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        if not file_exists(S3_BUCKET_NAME, report_path):
            return None, None, None
        report = read_s3_json(S3_BUCKET_NAME, report_path)
    else:
        if not os.path.exists(report_path):
            return None, None, None
        report = json.load(open(report_path, "r"))

    dataset_info = report["dataset_info"]
    overall_performance = report["overall_performance"]
    detailed_performance = report["intent_reports"]
    return dataset_info, overall_performance, detailed_performance


def get_entities(database, test_id):
    config = dict(database.get_one_bot_test_instance(test_id))
    entity_path = "data/bots/{}/{}/goals_dir/entities.json".format(config["type"], test_id)
    entities = None

    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        if file_exists(S3_BUCKET_NAME, entity_path):
            entities = read_s3_json(S3_BUCKET_NAME, entity_path)
    else:
        if os.path.exists(entity_path):
            entities = json.load(open(entity_path, "r"))

    return entities


def get_wrong_paraphrase_episode_id(chatlog, intent_query_index=1):
    query_to_episode = {}
    for episode in chatlog:
        if episode["error"] == "Intent Error":
            query = " ".join(episode["intent_query"].split()[2:]).strip()
            query_to_episode[query] = episode
            query_to_episode[query[:-1]] = episode
    return query_to_episode


def parse_confusion_matrix(database, test_id, mode):
    config = dict(database.get_one_bot_test_instance(test_id))
    cm_report_path = "data/bots/{}/{}/remediation/cm_{}_report.json".format(config["type"], test_id, mode)

    if file_exists(S3_BUCKET_NAME, cm_report_path):
        report = read_s3_json(S3_BUCKET_NAME, cm_report_path)
    else:
        return None, None, None, None, None, None, None
    rows = report["cm_table"]["body_row"]
    recalls, precisions, F1_scores = convert_list_to_dict(report["recall"]), \
                                     convert_list_to_dict(report["precision"]), \
                                     convert_list_to_dict(report["F1"])

    intent_clusters = {}
    if "clusters" in report:
        clusters = report["clusters"]
        for i, cluster in enumerate(clusters):
            for intent in cluster["intents"]:
                intent_clusters[intent] = i + 1
    else:
        for i, intent in enumerate(F1_scores):
            intent_clusters[intent] = i + 1

    intent_supports = {}

    intent_names_to_id = {}
    predictions = {}
    num_labels = 0
    classes = []
    for row in rows:
        support = row["support"]
        for r in row["row"]:
            if "recall" in r:
                intent_name = r["label"]
                if intent_name not in intent_names_to_id:
                    intent_names_to_id[intent_name] = num_labels
                    num_labels += 1
                    classes.append(intent_name)
                    intent_supports[intent_name] = support
            elif r["label"] != "":
                if r["ground_truth"] not in predictions:
                    predictions[r["ground_truth"]] = {}
                predictions[r["ground_truth"]][r["prediction"]] = int(r["label"])
    confusion_matrix = np.zeros((num_labels, num_labels))
    for intent in intent_names_to_id:
        ground_truth = intent
        if ground_truth not in predictions:
            continue
        for p in predictions[ground_truth]:
            if ground_truth in predictions and ground_truth in intent_names_to_id:
                confusion_matrix[intent_names_to_id[ground_truth], intent_names_to_id[p]] = predictions[ground_truth][p]
    return confusion_matrix, classes, recalls, precisions, F1_scores, intent_clusters, intent_supports
