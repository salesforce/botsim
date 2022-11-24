#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json, time, os
import botsim.modules.remediator.remediator_utils.utils as remediator_utils
import botsim.modules.remediator.remediator_utils.analytics as analytics
from botsim.botsim_utils.utils import read_s3_json, dump_s3_file


class Remediator:
    """ The remediator module performs analysis on the simulated conversations and produces a set of bot health reports
        to summarize the performance. It also offers a suite of analytical tools to help users better diagnose and
        troubleshoot the identified issues.
       1) aggregates the simulation results to support visualisation of  bot health reports in dashboard
       2) performs analysis on the simulation results and offers actionable suggestions to troubleshoot
          and improve bot systems.
       3) provides a suite of conversational analytic tools including intent confusion matrix analysis, tSNE clustering
       Required INPUTS are obtained from dialog simulation
       1) configs["remediator"]["file_paths"]["simulation_log"]: a json file containing chat logs (a list of
          conversation turns) and simulation goals for all simulated dialogs/episodes
       2) configs["remediator"]["file_paths"]["simulation_error_info"]: a json file containing error info for all failed
          dialogs

       Output bot health reports for each intent:
       1) aggregated_simulation_result_json report containing
          a) dialog_history b) intent_query c) intent_prediction d) error e) error_turn f) total_turns
       2) wrongly predicted intent queries together with their original utterances, remediation suggestions to support
          the intent remediation section of the dashboard
       3) ner error json to support NER remediation dashboard
    """

    def _prepare_data_paths(self, para_setting, num_seed_intent_utterances, num_simulation_episodes):
        if str(num_seed_intent_utterances) == "-1":
            num_seed_intent_utterances = "all"
        if str(num_simulation_episodes) == "-1":
            num_simulation_episodes = "all"
        self.simulation_error_info_path = self.configs["remediator"]["file_paths"]["simulation_error_info"].replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_seed_intent_utterances).replace(
            "<num_simulations>", num_simulation_episodes).replace("<mode>", self.mode)
        self.simulation_log_json_path = self.configs["remediator"]["file_paths"]["simulation_log"].replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_seed_intent_utterances).replace(
            "<num_simulations>", num_simulation_episodes).replace("<mode>", self.mode)
        self.aggregated_simulation_result_json_path = self.configs["remediator"]["file_paths"][
            "simulated_dialogs"].replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_seed_intent_utterances).replace(
            "<num_simulations>", num_simulation_episodes).replace("<mode>", self.mode)
        self.intent_prediction_json_path = self.configs["remediator"]["file_paths"]["intent_predictions"].replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_seed_intent_utterances).replace(
            "<num_simulations>", num_simulation_episodes).replace("<mode>", self.mode)
        self.intent_remediation_suggestions = self.configs["remediator"]["file_paths"]["intent_remediation"].replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_seed_intent_utterances).replace(
            "<num_simulations>", num_simulation_episodes).replace("<mode>", self.mode)
        self.ner_error_json = self.configs["remediator"]["file_paths"]["ner_error_json"].replace(
            "<para_setting>", para_setting).replace(
            "<num_utterances>", num_seed_intent_utterances).replace(
            "<num_simulations>", num_simulation_episodes).replace("<mode>", self.mode)


    def _load_paraphrases(self, para_setting, num_seed_intent_utterances):
        if str(num_seed_intent_utterances) == "-1":
            num_seed_intent_utterances = "all"
        intent_paraphrases = {}
        for intent in self.configs["intents"]:
            paraphrase_file = \
                self.configs["remediator"]["file_paths"]["paraphrases"] \
                    .replace("<intent>", intent) \
                    .replace("<num_utterances>", num_seed_intent_utterances) \
                    .replace("<para_setting>", para_setting)

            if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                intent_paraphrases[intent] = read_s3_json("botsim", paraphrase_file)
            else:
                with open(paraphrase_file, "r") as f:
                    intent_paraphrases[intent] = json.load(f)
        return intent_paraphrases

    def _init_remediation_data(self):
        self.intent_predictions = {}
        # prepare mapping between intent utterance to their paraphrases
        # one-to-many mapping from intent utterance to its paraphrases
        self.intent_utt_to_paraphrases = {}
        self.paraphrase_to_intent_utterances = {}
        self.intent_utterances = {}
        self.paraphrase_intent_queries = {}
        self.aggregated_results = {}
        self.misclassified_intent_paraphrases = {}
        for intent in self.configs["intents"]:
            self.intent_utterances[intent] = []
            self.intent_predictions[intent] = {"others": set(), intent: set()}
            self.paraphrase_intent_queries[intent] = set()
            self.paraphrase_to_intent_utterances[intent] = {}
            self.intent_utt_to_paraphrases[intent] = {}
            self.simulation_error_info[intent] = {}
            self.ner_errors[intent] = {}
            self.aggregated_results[intent] = []
            self.misclassified_intent_paraphrases[intent] = {}
            aggregated_result_dir = \
                os.path.dirname(self.aggregated_simulation_result_json_path.replace("<intent>", intent))
            if not os.path.isdir(aggregated_result_dir):
                os.makedirs(aggregated_result_dir)

        self.intent_success_messages = {"out_of_domain": set()}
        self.intent_success_messages["out_of_domain"].add("Sorry, I didn't understand that")
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            self.dialog_act_maps = read_s3_json("botsim",
                                                self.configs["generator"]["file_paths"]["revised_dialog_act_map"])
        else:
            with open(self.configs["generator"]["file_paths"]["revised_dialog_act_map"], "r") as f:
                self.dialog_act_maps = json.load(f)
        for dialog in self.dialog_act_maps["DIALOGS"].keys():
            self.intent_success_messages[dialog] = self.dialog_act_maps["DIALOGS"][dialog]["intent_success_message"]
            if "intent_failure_message" in self.dialog_act_maps["DIALOGS"][dialog]:
                self.intent_success_messages["out_of_domain"].update(
                    self.dialog_act_maps["DIALOGS"][dialog]["intent_failure_message"])
        self.intent_success_messages["out_of_domain"] = list(self.intent_success_messages["out_of_domain"])

    def _load_customer_entities(self):
        customer_entity_path = self.configs["generator"]["file_paths"]["customer_entities"]
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            customer_entities = read_s3_json("botsim", customer_entity_path)
        else:
            with open(customer_entity_path, "r") as f:
                customer_entities = json.load(f)
        return customer_entities

    def __init__(self, configs, mode="dev", intent_check_turn_index=1):
        self.configs = configs
        self.mode = mode
        self.intent_check_turn_index = intent_check_turn_index
        # Store the simulation errors from the Simulator
        self.simulation_error_info = {}
        # Categorise the NER errors according to the extraction method
        self.ner_errors = {}
        self.confusion_matrix = {}
        # self.simulation_intents = configs["intents"]
        self.remediation_results_dir = \
            os.path.dirname(configs["remediator"]["file_paths"]["intent_predictions"]).replace("<intent>", "")
        num_t5_paraphrases = configs["generator"]["paraphraser_config"]["num_t5_paraphrases"]
        num_pegasus_paraphrases = configs["generator"]["paraphraser_config"]["num_pegasus_paraphrases"]
        para_setting = "{}_{}".format(num_t5_paraphrases, num_pegasus_paraphrases)
        num_seed_intent_utterances = str(configs["generator"]["paraphraser_config"]["num_utterances"])
        num_simulation_episodes = str(configs["generator"]["paraphraser_config"]["num_simulations"])

        self._prepare_data_paths(para_setting, num_seed_intent_utterances, num_simulation_episodes)
        self.customer_entities = self._load_customer_entities()
        self.intent_paraphrases = self._load_paraphrases(para_setting, num_seed_intent_utterances)

        self._init_remediation_data()

    def prepare_intent_utt_to_paraphrases(self, intent_name):
        """
        Create the following two maps given an intent
        1) from intent utterance to paraphrases: self.intent_utt_to_paraphrases
        2) from paraphrases to intent utterances: self.paraphrase_to_intent_utterances
        :param intent_name:
        """
        for pair in self.intent_paraphrases[intent_name]:
            intent_utterance = pair["source"]
            normalised_intent_utterance = intent_utterance.strip()
            if not normalised_intent_utterance[-1].isalnum():
                normalised_intent_utterance = normalised_intent_utterance[:-1]
            self.paraphrase_to_intent_utterances[intent_name][normalised_intent_utterance] = normalised_intent_utterance
            self.paraphrase_to_intent_utterances[intent_name][intent_utterance.strip()] = normalised_intent_utterance

            discard = True
            for paraphrase in pair["cands"]:
                paraphrase = paraphrase.strip()
                if paraphrase in self.paraphrase_intent_queries[intent_name]:
                    self.paraphrase_to_intent_utterances[intent_name][paraphrase] = intent_utterance
                    discard = False
            if not discard:
                self.intent_utterances[intent_name].append(intent_utterance)
            # Add several variations of the original source utterances in intent_utt_to_paraphrases. This is to
            # handle the additional punctuations. e.g., 
            self.intent_utt_to_paraphrases[intent_name][intent_utterance] = pair["cands"]
            self.intent_utt_to_paraphrases[intent_name][intent_utterance.strip()] = pair["cands"]
            self.intent_utt_to_paraphrases[intent_name][normalised_intent_utterance] = pair["cands"]

    def intent_model_remediation_suggestions(self, target_intent):
        """
        Provide actionable suggestions for intent models based on the wrongly recognized intent paraphrases
        @param target_intent: target (correct) intent
        Returns:
        """
        misclassified_intent_utt_to_predicted_intents, misclassified_intent_utt_to_paraphrases = \
            self.intent_utterances_with_misclassified_paraphrase_queries(target_intent)

        intent_remediation_suggestions = \
            self.intent_remediation_suggestions.replace("<intent>", target_intent)

        for source_intent_utterance in misclassified_intent_utt_to_paraphrases:
            total_paraphrases = len(self.intent_utt_to_paraphrases[target_intent][source_intent_utterance])
            paraphrase_intent_prediction_pairs = misclassified_intent_utt_to_predicted_intents[source_intent_utterance]
            wrong_intent_to_error_count = {}
            wrong_intent_to_paraphrases = {}
            total_errors = 0
            for paraphrase_intent_query, wrong_intent in paraphrase_intent_prediction_pairs:
                if wrong_intent not in wrong_intent_to_paraphrases:
                    wrong_intent_to_paraphrases[wrong_intent] = []
                    wrong_intent_to_error_count[wrong_intent] = 0
                wrong_intent_to_paraphrases[wrong_intent].append(paraphrase_intent_query)
                wrong_intent_to_error_count[wrong_intent] += 1
                total_errors += 1
            wrong_intent_to_paraphrases = dict(
                sorted(wrong_intent_to_paraphrases.items(), key=lambda item: -len(item[1])))
            wrong_intent_to_error_count = dict(sorted(wrong_intent_to_error_count.items(), key=lambda item: -(item[1])))

            paraphrases = list(misclassified_intent_utt_to_paraphrases[source_intent_utterance])

            default_suggestion = \
                "Consider filtering and augmenting out-of-domain paraphrases to the intent training set"
            misclassified_intent_utt_to_paraphrases[source_intent_utterance] = \
                {"paraphrases": paraphrases,
                 "remediations": {"classified_intents": wrong_intent_to_paraphrases,
                                  "num_confusions": wrong_intent_to_error_count,
                                  "suggestions": [default_suggestion]},
                 "total_paraphrases": total_paraphrases}

            wrong_intent_to_error_count = sorted(wrong_intent_to_error_count.items(), key=lambda item: -(item[1]))

            if (wrong_intent_to_error_count[0][1] / total_paraphrases > 0.5) or \
                    (total_errors >= 3 and wrong_intent_to_error_count[0][1] / total_errors > 0.5):
                wrong_intent = wrong_intent_to_error_count[0][0]
                if wrong_intent == "others":
                    misclassified_intent_utt_to_paraphrases[source_intent_utterance]["remediations"][
                        "suggestions"].append(
                        "More than half of paraphrases have been wrongly classified as out-of-domain intent"
                        "==> consider filtering and augmenting these paraphrases to the intent training set "
                        "of " + target_intent)
                else:
                    misclassified_intent_utt_to_paraphrases[source_intent_utterance]["remediations"][
                        "suggestions"].append(
                        "More than half of paraphrases have been wrongly classified as "
                        "intent " + wrong_intent + "; wrong intent training utterance? "
                                                   "==> consider deleting or moving the training "
                                                   "utterance to intent " + wrong_intent)
        self.misclassified_intent_paraphrases[target_intent] = misclassified_intent_utt_to_paraphrases
        data = json.dumps(misclassified_intent_utt_to_paraphrases, indent=4)
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            dump_s3_file(intent_remediation_suggestions, bytes(data.encode("UTF-8")))
        else:
            with open(intent_remediation_suggestions, "w") as file:
                json.dump(misclassified_intent_utt_to_paraphrases, file, indent=2)

    def intent_utterances_with_misclassified_paraphrase_queries(self, target_intent):
        """
        Find the original intent utterances with at least one wrongly classified paraphrase intent queries. This is
        mainly for ablation study or remediation of the intent models
        @param target_intent: the target (correct) intent
        @return:
          misclassified_intent_utt_to_predicted_intents: mapping from intent utterances to a list of (paraphrase,
          wrongly predicted intent)
          misclassified_intent_utt_to_paraphrases: mapping from intent utterance to a set of wrongly classified
          paraphrased intent queries
        """
        self.prepare_intent_utt_to_paraphrases(target_intent)
        misclassified_intent_utt_to_paraphrases = {}
        misclassified_intent_utt_to_predicted_intents = {}
        for predicted_intent in self.intent_predictions[target_intent]:
            if predicted_intent != target_intent:
                for paraphrase_intent_query in self.intent_predictions[target_intent][predicted_intent]:
                    paraphrase_intent_query = paraphrase_intent_query.replace('"', "").strip()
                    if paraphrase_intent_query not in self.paraphrase_to_intent_utterances[target_intent]:
                        continue
                    source_intent_utterance = self.paraphrase_to_intent_utterances[target_intent][
                        paraphrase_intent_query]
                    if source_intent_utterance not in misclassified_intent_utt_to_paraphrases:
                        misclassified_intent_utt_to_paraphrases[source_intent_utterance] = set()
                        misclassified_intent_utt_to_predicted_intents[source_intent_utterance] = []

                    misclassified_intent_utt_to_predicted_intents[source_intent_utterance].append(
                        (paraphrase_intent_query, predicted_intent))
                    misclassified_intent_utt_to_paraphrases[source_intent_utterance].add(paraphrase_intent_query)
                    if source_intent_utterance not in self.intent_utt_to_paraphrases[target_intent] or \
                            len(self.intent_utt_to_paraphrases[target_intent][source_intent_utterance]) == 0:
                        misclassified_intent_utt_to_paraphrases.pop(source_intent_utterance)
                        misclassified_intent_utt_to_predicted_intents.pop(source_intent_utterance)

        # sort in descending order according to number of wrongly classified number of paraphrases
        misclassified_intent_utt_to_paraphrases = dict(sorted(misclassified_intent_utt_to_paraphrases.items(),
                                                              key=lambda item: -len(item[1])))
        return misclassified_intent_utt_to_predicted_intents, misclassified_intent_utt_to_paraphrases

    def parse_simulation_error_info(self, error_json_path, intent):
        """
        Parse error info files in json format dumped by the Simulator
        :param error_json_path: path to the error json file
        :param intent: intent/dialog name
        :return episode_dialog_error: a dictionary of dialog error info for all simulated dialogs with errors
            error = {"session": episode_index,
                     "error": "Other Error",
                     "error_turn_index": "TBD",
                     "error_turn": ""}
        """
        episode_dialog_error = {}
        error_file = error_json_path.replace("<intent>", intent)
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            error_info = read_s3_json("botsim", error_file)
        elif os.path.exists(error_file):
            error_info = json.load(open(error_file))
        else:
            return episode_dialog_error
        for index in error_info:
            episode_error = error_info[index]["error_info"]
            items = episode_error.split(";")
            episode_index = int(episode_error.split(";")[0])
            if episode_error.find(";;") != -1:
                error = {"session": episode_index,
                         "error": "Other Error",
                         "error_turn_index": "TBD",
                         "error_turn": ""}
                episode_dialog_error[episode_index] = error
            elif episode_error.find("@") == -1:
                # intent error or other error
                intent_query = items[1]
                error = {"session": episode_index, "error": "Intent Error",
                         "error_turn_index": self.intent_check_turn_index, "error_turn": intent_query,
                         "intent_error": {"ground_truth": intent}, "num_turns": self.intent_check_turn_index + 1}
                episode_dialog_error[episode_index] = error
            elif episode_error.find("@") != -1:  # entity error
                entity = items[-2]
                error_type = items[-1]
                chat_message = items[-3].replace("'s", "\\" + "'s").replace("'m", "\\" + "'m").replace("'d",
                                                                                                       "\\" + "'d")

                error = {"session": episode_index, "error": "NER Error", "error_turn_index": "TBD",
                         "error_turn": chat_message, "error_slot": entity, "num_turns": "TBD", "ner_errors": {}}
                error["ner_errors"]["slot"] = entity
                error["ner_errors"]["ground_truth"] = "TBD"
                error["ner_errors"]["error_type"] = error_type
                episode_dialog_error[episode_index] = error
        return episode_dialog_error

    def analyse_simulated_conversations(self, simulation_log, intent):
        """
        Parsing the json simulation chat logs for remediation and analyse by filling in the following data
        1) self.simulation_error_info,
        2) self.ner_errors,
        3) self.intent_predictions,
        #:return: aggregated_results
        """
        sessions_processed = set()
        log_path = simulation_log.replace("<intent>", intent)

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            simulation_log = read_s3_json("botsim", log_path)
        else:
            simulation_log = json.load(open(log_path, "r"))

        for index in simulation_log:
            if index == "summary":
                continue
            goal = simulation_log[index]["goal"]
            history = simulation_log[index]["chat_log"]
            episode, session_index = \
                remediator_utils.analyse_one_simulation_episode(
                    goal["name"],
                    history,
                    intent,
                    self.simulation_error_info, self.ner_errors,
                    self.intent_predictions,
                    self.customer_entities, self.paraphrase_intent_queries,
                    self.intent_success_messages, self.intent_check_turn_index)
            if episode and session_index not in sessions_processed:
                self.aggregated_results[intent].append(episode)
                sessions_processed.add(session_index)

    def generate_intent_report(self, intent):
        # Step 1: parse the error info generated by the Simulator
        self.simulation_error_info[intent] = self.parse_simulation_error_info(self.simulation_error_info_path, intent)
        # Step 2: perform analysis based on the simulation logs generated by the Simulator
        self.analyse_simulated_conversations(self.simulation_log_json_path, intent)
        aggregated_results_str = json.dumps(self.aggregated_results[intent], indent=4)

        # Step 3: dump the aggregated simulation results
        aggregated_result_path = self.aggregated_simulation_result_json_path.replace("<intent>", intent)
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            dump_s3_file(aggregated_result_path, bytes(aggregated_results_str.encode("UTF-8")))
        else:
            with open(aggregated_result_path, "w") as aggregated_result_writer:
                aggregated_result_writer.write(aggregated_results_str)
                aggregated_result_writer.close()

        # Step 4: dump intent prediction json
        intent_predictions = {}
        for predicted_intent in self.intent_predictions[intent]:
            intent_predictions[predicted_intent] = list(self.intent_predictions[intent][predicted_intent])
        data = json.dumps(intent_predictions, indent=4)
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            dump_s3_file(self.intent_prediction_json_path.replace("<intent>", intent), bytes(data.encode("UTF-8")))
        else:
            with open(self.intent_prediction_json_path.replace("<intent>", intent), "w") as file:
                json.dump(intent_predictions, file, indent=2)

        ####
        #simulation_intent = intent + "_" + self.mode
        simulation_intent = intent
        intent_prediction_counts = {simulation_intent: {}}
        overall_error_counts = {simulation_intent: {}}

        error_counts = {}
        for episode in self.aggregated_results[intent]:
            if episode["error"] not in error_counts:
                error_counts[episode["error"]] = 1
            else:
                error_counts[episode["error"]] += 1

            if episode["intent_prediction"] not in intent_prediction_counts[simulation_intent]:
                intent_prediction_counts[simulation_intent][episode["intent_prediction"]] = 1
            else:
                intent_prediction_counts[simulation_intent][episode["intent_prediction"]] += 1

        overall_error_counts[simulation_intent] = error_counts

        ####

        # Step 5: provide intent model remediation suggestions based on the predictions
        self.intent_model_remediation_suggestions(intent)

        # Step 6: dump the NER error remediation suggestions
        ner_error_json_path = self.ner_error_json.replace("<intent>", intent)
        data = json.dumps(self.ner_errors[intent], indent=4)
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            dump_s3_file(ner_error_json_path, bytes(data.encode("UTF-8")))
        else:
            with open(ner_error_json_path, "w") as file:
                json.dump(self.ner_errors[intent], file, indent=2)

        return intent_prediction_counts, overall_error_counts

    def confusion_matrix_analyze(self):
        analytics.confusion_matrix_analyze(self.confusion_matrix, self.mode, self.remediation_results_dir)
        print("confusion matrix analysis finished")

    def generate_health_reports(self, report):
        """ Generate health reports for all intents/dialogs. In particular, it aggregates a unified report to include
        all individual reports and the remediation suggestions to be used later by the Streamlit App to visualise
        the dashboard
        :param report: the unified report to support dashboard visualisation. It has the following info grouped by intent
                       1) "intent_reports", detailed intent/dialog reports
                           a) "intent_errors" with wrongly classified intent paraphrases grouped by the predicted labels.
                            It also includes the actionable suggestions based on the prediction results.
                           b) "ner_errors" with detailed NER error info, e.g., name, extraction type
                       2) dataset_info: train/eval data distribution for all intents
                       3) overall_performance: overall performance computed over all intents including task-completion
                          rates, NLU performance

        """
        aggregated_intent_prediction_counts = {}
        aggregated_overall_error_counts = {}
        for intent in self.configs["intents"]:
            intent_prediction_counts, error_counts = self.generate_intent_report(intent)
            aggregated_intent_prediction_counts[intent + "_" + self.mode] = intent_prediction_counts
            aggregated_overall_error_counts[intent + "_" + self.mode] = error_counts
            self.confusion_matrix.update(intent_prediction_counts)

            metrics = remediator_utils.compute_simulation_performance_metrics(intent, self.aggregated_results[intent])
            mode = self.mode
            metrics["mode"] = mode
            report["overall_performance"][mode][intent] = metrics
            total_episodes = sum(list(metrics["overall_performance"].values()))
            report["dataset_info"][mode][intent] = total_episodes
            report["intent_reports"][mode][intent] = {intent: self.aggregated_results[intent]}
            report["intent_reports"][mode][intent]["intent_errors"] = self.misclassified_intent_paraphrases[intent]
            report["intent_reports"][mode][intent]["ner_errors"] = self.ner_errors[intent]

        self.confusion_matrix_analyze()

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            dump_s3_file(self.remediation_results_dir + "intent_performance_{}.json".format(self.mode),
                         bytes(json.dumps(aggregated_intent_prediction_counts, indent=2).encode("UTF-8")))

            dump_s3_file(self.remediation_results_dir + "overall_performance_{}.json".format(self.mode),
                         bytes(json.dumps(aggregated_overall_error_counts, indent=2).encode("UTF-8")))
        else:
            with open(self.remediation_results_dir + "intent_performance_{}.json".format(self.mode), "w") as file:
                json.dump(aggregated_intent_prediction_counts, file, indent=2)
            with open(self.remediation_results_dir + "overall_performance_{}.json".format(self.mode), "w") as file:
                json.dump(aggregated_overall_error_counts, file, indent=2)
    @staticmethod
    def analyze_and_remediate(config):
        dev_intents = config["remediator"]["dev_intents"]
        if len(dev_intents) > 0:
            config["intents"] = dev_intents
        if config["platform"] == "DialogFlow_CX":
            intent_query_index = 0
        else:
            intent_query_index = 1

        report = {"bot_name": config["id"], "bot_id": config["id"],
                  "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "intent_reports": {"dev": {}, "eval": {}},
                  "dataset_info": {"dev": {}, "eval": {}},
                  "overall_performance": {"dev": {}, "eval": {}}}

        rem = Remediator(config, "dev", intent_check_turn_index=intent_query_index)
        rem.generate_health_reports(report)
        eval_intents = config["remediator"]["eval_intents"]
        if len(eval_intents) > 0:
            rem = Remediator(config, "eval", intent_check_turn_index=intent_query_index)
            rem.generate_health_reports(report)
        return report
