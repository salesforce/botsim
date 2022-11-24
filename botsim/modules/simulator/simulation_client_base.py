#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, random, json
from botsim.botsim_utils.utils import read_s3_json, seed_everything

seed_everything(42)


class UserSimulatorClientInterface:
    def __init__(self, config):
        self.config = config
        self.start_episode = 0
        self.intent_name = ""
        self.mode = "dev"
        self.dialog_errors = {}
        self.dialog_logs = {}
        self.config = config
        self.batch_size = 25

    def _prepare_simulation(self):
        simulation_config = self.config["simulation"]
        intent = list(simulation_config.keys())[0]
        self.continue_episode = simulation_config[intent]["continue_from"]
        self.mode = simulation_config[intent]["mode"]
        para_setting = simulation_config[intent]["para_setting"]

        if "num_utterances" in simulation_config:
            if simulation_config["num_utterances"] == -1:
                para_setting += "_all_utts"
            else:
                para_setting += "_" + str(simulation_config["num_utterances"])+"_utts"

        identifier = self.mode + "_" + para_setting + "_paraphrases"

        if simulation_config["num_simulations"] != -1:
            identifier += "_" + str(simulation_config["num_simulations"]) + "_sessions"
        else:
            identifier += "_all_sessions"
        goal_json = "{}/{}_{}.{}.paraphrases.goal.json".format(
            simulation_config[intent]["goal_dir"], intent, para_setting, self.mode)

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            user_goals = (read_s3_json("botsim", goal_json)["Goal"]).values()
        else:
            user_goals = (json.load(open(goal_json, "r"))["Goal"]).values()

        self.intent_name = intent

        log_file_name = self.config["remediator"]["file_paths"]["simulation_log"]. \
            replace(".txt", "").replace("<intent>", intent).replace("_eval","")

        simulation_log_dir = os.path.dirname(log_file_name)
        os.makedirs(simulation_log_dir, exist_ok=True)

        chatlog = "{}/logs_{}.json".format(simulation_log_dir, identifier)
        simulation_errors = "{}/errors_{}.json".format(simulation_log_dir, identifier)

        simulation_goals = [x for x in user_goals if x["name"] == intent.replace("_eval", "")]
        if simulation_config["num_simulations"] != -1:
            simulation_goals = random.sample(simulation_goals,
                                             min(len(simulation_goals), simulation_config["num_simulations"]))
        return simulation_goals, chatlog, simulation_errors

    def simulation_summary(self,
                           header,
                           total_episodes,
                           total_turns,
                           success,
                           intent_error,
                           ner_error,
                           other_error):
        summary = header
        summary += "total_episodes: " + str(total_episodes) + "\n"
        summary += "success_rate: " + str(success / total_episodes) + "\n"
        summary += "average_turns: " + str(int(total_turns / total_episodes)) + "\n"
        summary += "total_success: " + str(success) + "\n"
        summary += "total_failure: " + str(intent_error + ner_error + other_error) + "\n"
        summary += "intent_errors: " + str(intent_error) + "\n"
        summary += "NER_errors: " + str(ner_error) + "\n"
        summary += "other_errors: " + str(other_error) + "\n"
        self.dialog_logs["summary"][total_episodes] = summary
        return summary

    def dump_simulation_logs(self,
                             summary,
                             database,
                             total_episodes,
                             total_turns,
                             success,
                             intent_error,
                             ner_error,
                             other_error,
                             chatlog_file,
                             user_error_turns_file):

        if database:
            database.save_result_to_database(self.config["id"],
                                             self.intent_name,
                                             self.mode,
                                             total_episodes,
                                             success,
                                             intent_error,
                                             ner_error,
                                             other_error,
                                             total_turns
                                             )
        print(summary)
        self.dialog_logs["summary"][total_episodes] = summary

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            from botsim.botsim_utils.utils import dump_s3_file
            dump_s3_file(chatlog_file, bytes(json.dumps(self.dialog_logs, indent=2).encode("UTF-8")))
            dump_s3_file(user_error_turns_file, bytes(json.dumps(self.dialog_errors, indent=2).encode("UTF-8")))
        else:
            with open(chatlog_file, "w") as log_file:
                json.dump(self.dialog_logs, log_file, indent=2)
            with open(user_error_turns_file, "w") as error_file:
                json.dump(self.dialog_errors, error_file, indent=2)

        ret = {"summary": summary}
        return json.dumps(ret)

    def simulate_conversation(self, database=None):
        raise NotImplementedError

    def perform_batch_simulation(self, simulation_goals, simulation_intent, start_episode, simulation_config):
        raise NotImplementedError
