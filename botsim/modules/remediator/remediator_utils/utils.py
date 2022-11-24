#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from rapidfuzz import process
from botsim.botsim_utils.utils import read_s3_json
import os, json


def match_intent(intent_query, intent_success_messages):
    """
    Get the intent prediction label given utterance
    :param intent_query: intent query
    :param intent_success_messages:  intent success messages
    :return:
      best_matched_intent: best matched intent given the query among all intents
      best_matched_intent_success_message: the best success message of the matched intent
      matched_candidates: candidates with the same match score of max_score
    """
    score_to_candidates = {}
    max_score = 0
    for intent in intent_success_messages:
        candidates = intent_success_messages[intent]
        if len(candidates) == 0:
            continue
        matched_success_message, score, matched_candidate_index = process.extractOne(intent_query, candidates)
        if score not in score_to_candidates:
            score_to_candidates[score] = []
        score_to_candidates[score].append((matched_success_message, intent))
        if score >= max_score:
            max_score = score
            best_matched_intent = intent
            best_matched_intent_success_message = matched_success_message
    matched_candidates = score_to_candidates[max_score]
    return best_matched_intent, best_matched_intent_success_message, matched_candidates


def process_success_episode(summary, episode):
    start = summary.find(":")
    total_turn = int(summary[start + 1:])
    episode["error"] = "Success"
    episode["turn"] = str(total_turn)
    episode["error_turn"] = "-1"
    episode["filled_slots"] = ""


def complete_ner_errors(dialog_error, episode_ner_error, customer_entities, episode_index):
    """ Provide detailed NER info from the input customer_entities file
        1) episode_ner_error[ner_error_slot]["extraction_type"]
        2) episode_ner_error[ner_error_slot]["pattern"]/["value"] depending on the extraction type
        3) episode_ner_error[ner_error_slot]["remediation"] suggestions to fix the NER error
    :param dialog_error: the error info entry corresponding to the current episode from error_info_json
    :param episode_ner_error: a dictionary to accumulate the NER info across all episodes
    :param customer_entities: customer_entities mapping produced by the parser
    :param episode_index: episode index
    :return: updated episode_ner_error with remediation suggestions
    """
    ner_error_slot = dialog_error["error_slot"]
    if ner_error_slot not in episode_ner_error:
        episode_ner_error[ner_error_slot] = {"extraction_type": "UNK"}
        if ner_error_slot not in customer_entities["variable_to_entity"]:
            return None
        entity = customer_entities["variable_to_entity"][ner_error_slot]
        episode_ner_error[ner_error_slot]["entity_name"] = entity
        # figure out the entity extraction methods, e.g., regex, value
        if entity in customer_entities["Pattern"]:
            episode_ner_error[ner_error_slot]["extraction_type"] = "regex"
            episode_ner_error[ner_error_slot]["pattern"] = \
                customer_entities["Pattern"][entity]
        else:
            episode_ner_error[ner_error_slot]["extraction_type"] = "value"
            if entity in customer_entities["Value"]:
                episode_ner_error[ner_error_slot]["values"] = \
                    customer_entities["Value"][entity]
            else:  # discard the episode
                return None

    error_type = dialog_error["ner_errors"]["error_type"]
    if error_type not in episode_ner_error[ner_error_slot]:
        episode_ner_error[ner_error_slot][error_type] = []
    error_case = {"error_turn": dialog_error["error_turn"], "error_session": episode_index}
    episode_ner_error[ner_error_slot][error_type].append(error_case)
    if episode_ner_error[ner_error_slot]["extraction_type"] == "regex":
        episode_ner_error[ner_error_slot]["remediation"] = \
            ["Regex not covering the entity values, consider revising regex",
             "Consider model-based entity extraction"]
    elif episode_ner_error[ner_error_slot]["extraction_type"] == "value":
        episode_ner_error[ner_error_slot]["remediation"] = [
            "Value list not covering the entity values, include the value in the list",
            "Consider regex if the entity values have a pattern",
            "Consider model-based entity extraction"]

    return episode_ner_error


def complete_episode_error_info(history, episode, dialog_error, ner_errors,
                                customer_entities, target_intent, intent_success,
                                classified_intent, error="Other_error"):
    """
    Complete the episode information with errors
    :param history: dialog history
    :param episode: episode error information
    :param dialog_error: dialog error entry of the current episode
    :param ner_errors: ner errors
    :param customer_entities: customer entities produced by parser
    :param target_intent: ground truth intent
    :param intent_success: whether correct intent has been detected
    :param classified_intent: predicted intent
    :param error: error type
    :return: updated episode error information
    """
    if "ner_errors" in dialog_error:
        error_message = "{}>>> {} >>> ({})".format(episode["episode"], episode["error_turn"],
                                                   dialog_error["error_slot"])
        episode["error"] = "NER Error"
        episode["filled_slots"] = error_message
        episode_index = episode["episode"].replace("E", "")
        episode_ner_error = complete_ner_errors(dialog_error,
                                                ner_errors[target_intent],
                                                customer_entities,
                                                episode_index)
        if not episode_ner_error:
            return None
        ner_errors[target_intent] = episode_ner_error
    elif error == "Other_error":
        if intent_success:
            episode["intent_prediction"] = classified_intent
            episode["error"] = "Other Error"
            episode["filled_slots"] = history[-1]
            episode["intent_success"] = "yes"
        else:
            episode["error"] = "Intent Error"
            if "intent_error" not in dialog_error:
                dialog_error["intent_error"] = {}
                dialog_error["error_turn"] = episode["error_turn"]
    else:
        episode["error"] = "Intent Error"
        if "intent_error" not in dialog_error:
            dialog_error["intent_error"] = {}
            dialog_error["error_turn"] = episode["error_turn"]
    return episode


def _parse_episode_summary(summary_message):
    """
    Extract error info from the summary message at the end of each simulated conversation
    :param summary_message: the summary message
    :return: a tuple of error type, index of dialog turn causing the error, total number of dialog turns
    """
    start, end = summary_message.find("due to"), summary_message.find("Error")
    error_type = summary_message[start + 7:end].strip().lower().capitalize()
    error_type = error_type.replace("Ner", "NER").replace("User", "Other") + "_error"
    start, end = summary_message.find("turns: "), summary_message.find(" =")
    total_number_of_turns = int(summary_message[start + 7:end]) + 1
    error_turn_index = -1
    for item in summary_message.split():
        if item.find(">>") != -1:
            start = item.find(">>")
            error_turn_index = int(item[start + 2:])
    return error_type, error_turn_index, total_number_of_turns


def analyse_one_simulation_episode(goal, history, intent, dialog_errors, ner_errors,
                                   intent_classification_to_queries,
                                   customer_entities,
                                   paraphrase_intent_queries,
                                   intent_success_messages, intent_query_index):
    """
    Analyse one episode  of simulation from the json simulation log produced by the simulator.
    :param goal: the goal name
    :param history: dialog history of the episode
    :param intent: dialog/intent name
    :param dialog_errors: mapping from intents to their dialog error info obtained from the dialog error json
    :param ner_errors:
    :param intent_classification_to_queries: a mapping from a target intent to the predicted intent with the intent
                                             queries
    :param customer_entities: customer entities from the generator/parser
    :param paraphrase_intent_queries: mapping from intent to its paraphrase intent queries
    :param intent_success_messages: mapping from intent to its success messages
    :param intent_query_index: the dialog turn index of the intent query
    """
    assert len(dialog_errors) > 0
    if len(history) == 0:
        return None, None
    summary = history[-1]
    if not summary[0] == "=":  # discard episodes with API communication errors
        return None, None
    session_index = int((summary.split()[2]).strip())
    episode = {"dialog_history": history, "episode": "E" + str(session_index),
               "goal": goal, "intent_prediction": intent}

    intent_enquiry = history[intent_query_index].replace('"', "").strip()
    intent_enquiry = " ".join(intent_enquiry.split()[2:])
    intent_enquiry = intent_enquiry.replace("..", ".").replace("?.", "?").replace("!.", "!").replace(",.", ",")
    if len(intent_enquiry) == 0:
        return None, None

    intent_success = False
    bot_message = history[intent_query_index + 1].replace('"', "").strip()
    bot_message = " ".join(bot_message.split()[2:])
    classified_intent, _, candidates = match_intent(bot_message, intent_success_messages)

    candidate_intents = set([x[1] for x in candidates])

    if len(candidates) <= 2 and intent in candidate_intents:
        intent_success = True
        classified_intent = intent

    if summary.find("SUCCESS") != -1:
        process_success_episode(summary, episode)
    else:
        error, error_turn_index, total_turns = _parse_episode_summary(summary)
        if session_index not in dialog_errors[intent]:
            return None, None
        episode["error_turn"] = str(error_turn_index)
        episode["turn"] = str(total_turns)
        dialog_error = dialog_errors[intent][session_index]
        dialog_error["error_turn_index"] = error_turn_index
        dialog_error["num_turns"] = total_turns
        episode_completed = complete_episode_error_info(history, episode, dialog_error,
                                                        ner_errors,
                                                        customer_entities,
                                                        intent, intent_success,
                                                        classified_intent,
                                                        error)
        if not episode_completed:
            return None, None

    if episode["error"] == "Intent Error":
        dialog_errors[intent][session_index]["intent_error"]["classified_as"] = classified_intent
        error_message = "E" + str(session_index) + ">>>" + \
                        dialog_errors[intent][session_index]["error_turn"] + \
                        ">>> (intent error as " + \
                        dialog_errors[intent][session_index]["intent_error"]["classified_as"] + ")"
        episode["filled_slots"] = error_message
        paraphrase_intent_queries[intent].add(intent_enquiry)
        if len(candidates) == 1:
            episode["intent_prediction"] = classified_intent
            if classified_intent not in intent_classification_to_queries[intent]:
                intent_classification_to_queries[intent][classified_intent] = set()
            intent_classification_to_queries[intent][classified_intent].add(intent_enquiry)
        else:
            episode["intent_prediction"] = "out_of_domain"
            intent_classification_to_queries[intent]["others"].add(intent_enquiry)
    else:
        if intent not in intent_classification_to_queries[intent]:
            intent_classification_to_queries[intent][intent] = set()
        if classified_intent in intent_classification_to_queries[intent]:
            intent_classification_to_queries[intent][classified_intent].add(intent_enquiry)

    if len(history) < intent_query_index + 1:
        return None, None
    episode["intent_query"] = history[intent_query_index]
    return episode, session_index


def compute_simulation_performance_metrics(intent, dialog_simulation_results):
    """
    Given the intent/dialog health reports, compute the performance metrics
    :param intent: intent name
    :param dialog_simulation_results
    """
    success, intent_error, ner_error, other_error = 0, 0, 0, 0
    intent_prediction = {intent: 0}
    total_turn = 0
    paraphrase_to_intent = {}
    for episode in dialog_simulation_results:
        error = episode["error"]
        total_turn += int(episode["turn"])
        if error == "Success":
            success += 1
            intent_prediction[intent] += 1
        elif error == "Intent Error":
            intent_error += 1
            if episode["intent_prediction"] not in intent_prediction:
                intent_prediction[episode["intent_prediction"]] = 0
            intent_prediction[episode["intent_prediction"]] += 1
            paraphrase = episode["dialog_history"][1].split()[2:]
            paraphrase = (" ".join(paraphrase)).strip().replace("?.", "?")
            paraphrase = paraphrase.replace("..", ".").replace(",.", ",").replace("!.", "!")
            paraphrase_to_intent[paraphrase] = episode["intent_prediction"]
            if not paraphrase[-1].isalnum():
                paraphrase = paraphrase[:-1]
            paraphrase_to_intent[paraphrase] = episode["intent_prediction"]
        elif error == "NER Error":
            intent_prediction[intent] += 1
            ner_error += 1
        else:
            other_error += 1
            if "intent_success" in episode:
                intent_prediction[intent] += 1

    num_simulation_episodes = len(dialog_simulation_results)
    success_rate = round(success / num_simulation_episodes, 2)
    intent_error_rate = round(intent_error / num_simulation_episodes, 2)
    ner_error_rate = round(ner_error / num_simulation_episodes, 2)
    other_error_rate = round(other_error / num_simulation_episodes, 2)
    average_turn = round(total_turn / num_simulation_episodes, 2)

    overall_performance = {"Success": success, "Intent Error": intent_error,
                           "NER Error": ner_error, "Other Error": other_error}

    metrics = {"intent": intent,
               "success_rate": success_rate,
               "intent_error_rate": intent_error_rate,
               "NER_error_rate": ner_error_rate,
               "other_error_rate": other_error_rate,
               "average_turn": average_turn,
               "overall_performance": overall_performance,
               "intent_predictions": intent_prediction,
               "paraphrase_to_intent": paraphrase_to_intent}
    return metrics


def aggregate_report_json_from_individual_reports(mode, report, configs):
    """
    Aggregate report.json for Streamlit app to visualise the remediator dashboard
    :param mode: dev or eval
    :param report: target report
    :param configs: remediator configuration
    """
    num_utterances = str(configs["generator"]["paraphraser_config"]["num_utterances"])
    num_simulations = str(configs["generator"]["paraphraser_config"]["num_simulations"])
    para_setting = str(configs["generator"]["paraphraser_config"]["num_t5_paraphrases"]) + "_" + \
                   str(configs["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    if str(num_utterances) == "-1":
        num_utterances = "all"
    if str(num_simulations) == "-1":
        num_simulations = "all"

    for intent in configs["intents"]:
        simulation_intent = intent
        aggregated_results_file = configs["remediator"]["file_paths"]["aggregated_results"].replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_utterances).replace(
            "<num_simulations>", num_simulations).replace("<intent>", simulation_intent).replace("<mode>", mode)

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            aggregated_results = read_s3_json("botsim", aggregated_results_file)
        else:
            if not os.path.exists(aggregated_results_file): continue
            with open(aggregated_results_file, "r") as f:
                aggregated_results = json.load(f)

        metrics = compute_simulation_performance_metrics(intent, aggregated_results)
        metrics["mode"] = mode
        report["overall_performance"][mode][intent] = metrics
        total_episodes = sum(list(metrics["overall_performance"].values()))
        report["dataset_info"][mode][intent] = total_episodes
        report["intent_reports"][mode][intent] = {intent: aggregated_results}
        intent_prediction_json = configs["remediator"]["file_paths"]["wrong_prediction_json"].replace(
            "<intent>", simulation_intent).replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_utterances).replace(
            "<num_simulations>", num_simulations).replace("_<mode>", "_" + mode.lower())

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            intent_predictions = read_s3_json("botsim", intent_prediction_json)
        else:
            if not os.path.exists(intent_prediction_json): continue
            with open(intent_prediction_json) as f:
                intent_predictions = json.load(f)

        report["intents"][mode][intent]["intent_errors"] = intent_predictions
        # ner errors
        ner_error_json = \
            configs["remediator"]["file_paths"]["ner_error_json"].replace("<intent>", simulation_intent).replace(
                "<para_setting>", para_setting).replace(
                "<num_utterances>", num_utterances).replace(
                "<num_simulations>", num_simulations).replace("_<mode>", "_" + mode.lower())

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            ner_errors = read_s3_json("botsim", ner_error_json)
        else:
            if not os.path.exists(ner_error_json): continue
            with open(ner_error_json) as f:
                ner_errors = json.load(f)

        report["intents"][mode][intent]["ner_errors"] = ner_errors


