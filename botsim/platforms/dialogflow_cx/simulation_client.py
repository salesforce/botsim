#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import uuid, os

from google.api_core.exceptions import InvalidArgument
from google.cloud.dialogflowcx_v3beta1.types import session
from botsim.modules.simulator.simulation_client_base import UserSimulatorClientInterface

from botsim.modules.simulator.user_simulator import UserSimulator
from botsim.modules.generator.utils.dialogflow_cx import parser_utils
from botsim.botsim_utils.utils import cut_string, seed_everything

seed_everything(42)


class DialogFlowCXClient(UserSimulatorClientInterface):

    def __init__(self, config):
        super().__init__(config)

    def perform_batch_simulation(self, simulation_goals, simulation_intent,
                                 start_episode, simulation_config):
        """
        Perform one batch of dialog simulation
        :param simulation_goals: list of simulation goals
        :param simulation_intent: intent for simulation
        :param start_episode: episode index to start
        :param simulation_config: the simulation configuration
        """
        project_id = simulation_config["api"]["project_id"]
        location_id = simulation_config["api"]["location_id"]
        agent_id = simulation_config["api"]["agent_id"]
        google_cloud_agent_path = f"projects/{project_id}/locations/{location_id}/agents/{agent_id}"

        batch_success, batch_ner_error, batch_intent_error, batch_other_error = 0, 0, 0, 0
        batch_turns, num_simulations = 0, 0
        user_simulator = UserSimulator(simulation_goals, simulation_config)

        while start_episode < len(simulation_goals) and num_simulations < self.batch_size:
            discard_episode = False
            # print("Episode ", start_episode)
            user_simulator.reset(start_episode)
            self.dialog_logs[start_episode] = {"goal": user_simulator.goal, "chat_log": []}

            bot_action_frame = {"inform_slots": {}, "request_slots": {}, "round": 1, "action": "", "message": ""}
            session_finished = False
            session_path, session_client = parser_utils.create_session(google_cloud_agent_path)
            session_id = google_cloud_agent_path + "/sessions/" + str(uuid.uuid4())
            normal_message = []

            while not session_finished:
                res = user_simulator.enqueue_bot_actions_from_bot_messages(
                    "DialogFlow CX", normal_message, bot_action_frame, start_episode, self.dialog_logs)
                if res and not discard_episode:
                    if "to_discard" in res:
                        discard_episode = True
                        break
                    episode_success, \
                    episode_intent_error, \
                    episode_ner_error, \
                    episode_other_error, \
                    episode_turns = \
                        user_simulator.log_episode_simulation_results(res, start_episode, self.dialog_logs,
                                                                      self.dialog_errors)
                    batch_success += episode_success
                    batch_turns += episode_turns
                    batch_ner_error += episode_ner_error
                    batch_intent_error += episode_intent_error
                    batch_other_error += episode_other_error
                    break
                print(bot_action_frame["round"], "BotSIM: ")

                concat_user_response = "{} BotSIM: ".format(bot_action_frame["round"])

                # responding to multiple system actions in one turn
                for act in user_simulator.state["bot_action_queue"]:
                    if act["action"] == "inform":
                        continue
                    usr_action, user_response, user_response_slots = user_simulator.policy(act)
                    user_simulator.state["user_response"] = user_response
                    print("\t" + cut_string(user_response, 15))

                    concat_user_response += " {} ".format(user_response)

                    if user_simulator.state["action"] == "fail":
                        self.dialog_logs[start_episode]["chat_log"].append(concat_user_response)
                        result = user_simulator.backtrack_simulation_errors()
                        session_finished = True
                    elif "Goodbye" in user_simulator.state["inform_slots"] \
                            or user_simulator.state["action"] == "goodbye":

                        print("=" * 10 + " SUCCESS dialog " + "=" * 10)

                        self.dialog_logs[start_episode]["chat_log"].append(concat_user_response)
                        result = {"num_turns": bot_action_frame["round"], "error": "Success", "status": 0,
                                  "error_turn_index": -1, "error_turn": "", "error_turn_slots": "", "error_slot": ""}
                        session_finished = True
                    if session_finished:
                        episode_success, episode_intent_error, episode_ner_error, \
                        episode_other_error, episode_turns = user_simulator.log_episode_simulation_results(
                            result, start_episode, self.dialog_logs, self.dialog_errors)
                        batch_success += episode_success
                        batch_turns += episode_turns
                        batch_ner_error += episode_ner_error
                        batch_intent_error += episode_intent_error
                        batch_other_error += episode_other_error
                        break
                user_simulator.dialog_turn_stack.append(
                    (usr_action,
                     bot_action_frame["round"],
                     user_response,
                     user_response_slots,
                     simulation_intent))
                bot_action_frame["round"] = bot_action_frame["round"] + 1
                user_simulator.state["bot_action_queue"] = []
                self.dialog_logs[start_episode]["chat_log"].append(concat_user_response)
                # post user response to agent
                if len(user_response) > 0:
                    text_input = session.TextInput(text=user_response)
                    query_input = session.QueryInput(text=text_input, language_code="en")
                    try:
                        request = session.DetectIntentRequest(session=session_id, query_input=query_input)
                        response = session_client.detect_intent(request=request)
                    except InvalidArgument:
                        raise

                    text = [" ".join(txt.replace("\n", "").split())
                            for msg in response.query_result.response_messages
                            for txt in msg.text.text]
                    normal_message = text
            start_episode += 1
            if not discard_episode:
                num_simulations += 1

        return batch_success, batch_ner_error, batch_intent_error, batch_other_error, batch_turns, num_simulations

    def simulate_conversation(self, database=None):

        intent_goals, chatlog_file, user_error_turns_file = self._prepare_simulation()
        success, ner_error, intent_error, other_error, total_turns, total_episodes = 0, 0, 0, 0, 0, 0
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.config["api"]["cx_credential"]
        self.dialog_logs["summary"] = {}
        for episode_index in range(self.continue_episode, len(intent_goals), self.batch_size):
            succ, ner, intent, other, turns, episode_processed = \
                self.perform_batch_simulation(
                    intent_goals,
                    self.intent_name.replace("_eval", ""),
                    episode_index, self.config)
            success += succ
            ner_error += ner
            intent_error += intent
            other_error += other
            total_turns += turns
            total_episodes += episode_processed
            # time.sleep(60)
            if total_episodes % 50 == 0 and total_episodes > 0:
                header = "\n\n========= Simulation up to Episode " + \
                         str(total_episodes) + ": ==========\n"
                self.simulation_summary(header, total_episodes, total_turns, success, intent_error, ner_error,
                                        other_error)

        header = "\n\n========= Simulation summary: ==========\n"
        summary = self.simulation_summary(header, total_episodes, total_turns, success, intent_error, ner_error,
                                          other_error)
        return self.dump_simulation_logs(summary,
                                         database,
                                         total_episodes,
                                         total_turns,
                                         success,
                                         intent_error,
                                         ner_error,
                                         other_error,
                                         chatlog_file,
                                         user_error_turns_file)

