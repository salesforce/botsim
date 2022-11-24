#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random, copy

from botsim.conf.ABUS import INTENT_ERROR, NER_ERROR, OTHER_ERROR
from botsim.botsim_utils.utils import cut_string, seed_everything
from botsim.modules.simulator.abus import UserSimulatorInterface

seed_everything(42)


class UserSimulator(UserSimulatorInterface):

    def __init__(self, simulation_goals, simulation_configs):
        """
        Agenda-based dialog user simulator.
        @param simulation_goals: list of simulation goals
        @param simulation_configs: simulation configurations in json format
        """
        super().__init__(simulation_goals, simulation_configs)

    def _dialog_state_sanity_check(self):
        """
        Check the current dialog state to identify errors
        """
        if self.state["action"] == "request":
            assert self.state["request_slots"]
        if self.state["action"] == "inform":
            assert self.state["inform_slots"] and (not self.state["request_slots"])
        assert self.state["action"] != ""

    def generate_user_response(self, botsim_action):
        """
        Generate botsim messages based on the current user action from policy
        @param botsim_action: BotSIM action semantic frame from the policy module.
        It should contain the following info
            1. dialog_act to indicate whether it is an "inform" or "request" action
            2. "inform_slots" slots to be informed to the bot
            3. "request_slots" slots to be requested from the bot
        The user action is used to query the template-based NLG module to generate a NL response
        :return:
           nl_message: natural language user message
           semantic_message: user message before replacing slots with values
        """
        nl_message, semantic_message = "", ""
        if botsim_action["action"] != "fail":
            template_responses, slots_responses = self.nlg_model.generate(botsim_action, "user")
            if isinstance(template_responses[0], list):
                for i, responses in enumerate(template_responses):
                    j = random.choice(range(0, len(responses)))
                    nl_message += responses[j] + " "
                    semantic_message += slots_responses[i][j] + " "
            else:
                j = random.choice(range(0, len(template_responses)))
                nl_message = template_responses[j]  # str(random.choice(template_responses))
                semantic_message = slots_responses[j]
        return nl_message, semantic_message

    def policy(self, bot_action):
        """
        Rule-based dialog policy mapping from bot semantic-leval actions to user response.
        The rules are implemented as _response_to_* functions.
        @param bot_action: bot action semantic frame with the following info
            1. dialog_act to indicate whether it is an "inform" or "request" action
            2. "inform_slots" slots to be informed to the user
            3. "request_slots" slots to be requested from the user
            4. "round" is the number of dialog turns so far
            5. "question" is the current agent message
        bot_action is obtained from the dialog act map NLU which maps from bot messages to dialog acts via fuzzy matching.
        :return:
            botsim_state for keeping track of the dialog states
            nl_message: natural language response
            semantic_message: response augmented with slot names for keeping track of entities
        """
        self.state["inform_slots"].clear()
        self.state["action"] = ""

        if bot_action["round"] > self.max_round: return {}, "", ""
        if bot_action["action"] == "request":
            self._response_to_request(bot_action)
        elif bot_action["action"] == "inform":
            self._response_to_inform(bot_action)
        elif bot_action["action"] == "success":
            self.state["action"] = "done"
            self.state["request_slots"].clear()
        elif bot_action["action"] == "confirm":
            self._response_to_confirm(bot_action)
        elif bot_action["action"] == "greeting":
            self._response_to_greeting()
        else:
            raise Exception("No rule defined "
                            "for agent action type " + bot_action["action"] + " yet")
        self._dialog_state_sanity_check()
        botsim_state = {"action": self.state["action"],
                        "request_slots": copy.deepcopy(self.state["request_slots"]),
                        "inform_slots": copy.deepcopy(self.state["inform_slots"])}
        nl_message, semantic_message = self.generate_user_response(botsim_state)
        return botsim_state, nl_message, semantic_message

    @staticmethod
    def update_agent_action(matched_bot_dialog_act,
                            bot_message,
                            matched_message,
                            turn_index):
        """
        Given the matched bot dialog act from the dialog act maps, prepare bot_action frame
        :param matched_bot_dialog_act: system dialog act matched by the NLU model/templates
        :param bot_message: the original bot question/message used by template NLU to get the bot_dialog_act
        :param matched_message: the matched question/messages from the message to dialog act templates
        :param turn_index: dialog turn index
        :return: updated bot_action
        """
        bot_action = {"inform_slots": {}, "request_slots": {}, "action": "",
                      "question": bot_message, "round": turn_index}
        bot_action["request_slots"].clear()
        bot_action["inform_slots"].clear()

        if matched_bot_dialog_act == "greeting":
            bot_action["action"] = "greeting"
        elif matched_bot_dialog_act == "dialog_success_message":
            bot_action["action"] = "match_found"
            bot_action["inform_slots"]["check_answer"] = bot_message
            bot_action["question"] = matched_message
        elif matched_bot_dialog_act == "request_confirm":
            bot_action["action"] = "confirm"
            bot_action["inform_slots"]["check_answer"] = bot_message
        elif matched_bot_dialog_act.find("request_") != -1:
            slot = "_".join(matched_bot_dialog_act.split("_")[1:])
            bot_action["action"] = "request"
            bot_action["request_slots"][slot] = "UNK"
        elif matched_bot_dialog_act.find("inform_") != -1:
            slot = "_".join(matched_bot_dialog_act.split("_")[1:])
            bot_action["action"] = "inform"
            bot_action["inform_slots"][slot] = "UNK"
        return bot_action

    @staticmethod
    def _summarise_simulation_session(episode_index, error_info, chat_log_json, user_error_turns_json):
        num_dialog_turns = error_info["num_turns"]
        status = error_info["status"]
        error_type = error_info["error"]
        error = ""
        if status == 0:
            summary = "=" * 10 + " Episode {}\t {} \tNum_of_turns"":{}".format(episode_index + 1,
                                                                               "SUCCESS " + "=" * 10,
                                                                               num_dialog_turns)
            chat_log_json[episode_index]["chat_log"].append(summary)
            return summary, error
        error_turn_index = error_info["error_turn_index"]
        user_error_turns_json[episode_index] = {"error_info": "", "error_type": ""}
        if status == 1:
            summary = "=" * 10 + " Episode {}\t {} \tNum_of_turns: {}".format(episode_index + 1,
                                                                              "FAILURE due to "
                                                                              + error_type + ">>"
                                                                              + str(error_turn_index),
                                                                              str(num_dialog_turns) + " " + "=" * 10)
            error = "{};{};{}".format(str(episode_index + 1),
                                      error_turn_index, error_info["intent"].strip(), error_info["error_slot"])

        elif status == 2:
            summary = "=" * 10 + " Episode {}\t {} \tNum_of_turns: {}".format(episode_index + 1,
                                                                              "FAILURE due to "
                                                                              + error_type + ">>"
                                                                              + str(error_turn_index),
                                                                              str(num_dialog_turns) + " " + "=" * 10)
            error = "{};{};{}".format(str(episode_index + 1),
                                      error_info["error_turn"].strip(),
                                      error_info["ner_error_type"].strip())
        elif status == 3:  # other errors
            summary = "=" * 10 + " Episode {}\t {} \tNum_of_turns: {}".format(episode_index + 1,
                                                                              "FAILURE due to "
                                                                              + error_type + ">>"
                                                                              + str(error_turn_index),
                                                                              str(num_dialog_turns) + " " + "=" * 10)
            error = "{};{};{}".format(str(episode_index + 1),
                                      error_info["error_turn_slots"].strip(),
                                      error_info["error_slot"].strip())
        else:
            raise ValueError("unknown failure status")
        chat_log_json[episode_index]["chat_log"].append(summary)
        user_error_turns_json[episode_index]["error_info"] = error
        return summary, error

    @staticmethod
    def log_episode_simulation_results(error_info, episode_index, chat_log_json, user_error_turns_json):
        """
        Log simulation result for the given episode to chat log and error file
        :param error_info: simulation results. It contains the following info
            1. status: status code: 0 for success, 1 for intent error, 2 for NER error, 3 for other errors
            2. error_turn_index: the dialog turn causing the dialog errors
            3. error: string representation of the error (Success, Intent Error, NER Error, Other Error)
            4. error_slot: the entity slot. If the error is caused by intent, slot == intent
            5. intent: the intent name
            6. number_of_turns: total number of simulation turns until the error turn
            7. error_turn: the natural language response of the turn with errors
            8. error_turn_slots: same as error_turn but with additional slot information
        :param episode_index: the current episode index
        :param chat_log_json: output chat log file
        :param user_error_turns_json: output dialog error turns
        :return: binary indicator of (success, intent_error, NER_error, other_error)
                 and total number of dialog turns so far
        """
        success, intent_error, ner_error, other_error = 0, 0, 0, 0
        status = error_info["status"]
        num_dialog_turns = error_info["num_turns"]
        if status == 0:
            success += 1
        elif status == 1:
            intent_error += 1
        elif status == 2:
            ner_error += 1
        elif status == 3:
            other_error += 1
        UserSimulator._summarise_simulation_session(episode_index, error_info, chat_log_json, user_error_turns_json)
        return success, intent_error, ner_error, other_error, num_dialog_turns

    def _backtrack_intent_error(self):
        """ Trace  intent errors
        """
        error_info = {"error": "Intent Error", "status": INTENT_ERROR,
                      "error_turn_index": self.intent_check_turn_index - 2,
                      "error_turn": self.state["user_response"], "error_turn_slots": self.state["user_response"],
                      "intent": self.goal["name"], "error_slot": "intent", "num_turns": len(self.dialog_turn_stack)}
        return error_info

    def _backtrack_ner_error(self):
        """ Trace NER errors
        """
        error_info = {"error": "NER Error", "status": NER_ERROR}
        for slot in self.state["ner_errors"].keys():
            error_type, _, _ = self.state["ner_errors"][slot]
            if slot not in self.state["informed_user_turn"]:
                error_info["error"] = "Other Error"
                error_info["status"] = OTHER_ERROR
                error_info["error_turn"] = ""
                error_info["error_turn_slots"] = ""
                error_info["error_slot"] = ""
                error_info["error_turn_index"] = len(self.dialog_turn_stack)
                error_info["num_turns"] = len(self.dialog_turn_stack)
                return error_info
            i = 0
            error_info["num_turns"] = self.dialog_turn_stack[-1][1]
            # backtracking the dialog_turn_stack to locate the turn with the error entity slots
            while i < len(self.dialog_turn_stack):
                user_action, error_turn_index, botsim_message, botsim_message_semantics, _ \
                    = self.dialog_turn_stack[i]
                if error_turn_index == self.state["informed_user_turn"][slot]:
                    error_info["error_turn_index"] = error_turn_index
                    error_info["error_turn"] = botsim_message
                    error_info["error_turn_slots"] = botsim_message_semantics
                    error_info["error_slot"] = slot
                    error_info["ner_error_type"] = error_type
                    return error_info
                i += 1
        return error_info

    def backtrack_simulation_errors(self):
        """ Backtrack  simulation errors from self.dialog_turn_stack, a stack/list to store the semantic frames
            of the dialog history
            :return error_info: The error info includes the following items
              "error": type of error, e.g., Intent Error, NER Error or Other Errors
              "status": numerical code for the error
              "error_turn_index": the index of dialog turn leading to the error (zero-based)
              "error_turn": the dialog message causing the dialog error. e.g., intent queries for intent errors
              "error_turn_slots": the semantic representation of "error_turn"
              "intent": intent/dialog name
              "error_slot": the error slots of "error_turn_slots". e.g., intent for intent errors, entity name for NER errors
              "num_turns": number of total dialog turns
        """
        error_info = {}
        if len(self.state["intent_error"]) > 0:
            return self._backtrack_intent_error()

        if len(self.state["ner_errors"]) > 0:
            return self._backtrack_ner_error()

        if len(self.state["runtime_error"]) > 0:
            error_info["error"] = "Other Error"
            error_info["status"] = OTHER_ERROR
            error_info["num_turns"] = self.dialog_turn_stack[-1][1]
            dialog_turn_index = 0
            while dialog_turn_index < len(self.dialog_turn_stack):
                user_action, error_turn_index, botsim_message, botsim_message_semantics, simulation_intent = \
                    self.dialog_turn_stack[dialog_turn_index]
                if botsim_message == self.state["runtime_error"]:
                    error_info["error_turn_index"] = error_turn_index
                    error_info["error_turn"] = botsim_message
                    error_info["error_turn_slots"] = ""
                    error_info["error_slot"] = ""
                    return error_info
                dialog_turn_index += 1
        else:
            error_info["error"] = "Other Error"
            error_info["status"] = OTHER_ERROR
            error_info["error_turn_index"] = len(self.dialog_turn_stack)
            error_info["num_turns"] = len(self.dialog_turn_stack)
            error_info["error_turn"] = ""
            error_info["error_turn_slots"] = ""
            error_info["error_slot"] = ""
            return error_info

        # If the requested slots are not in the original dialog goal, an intent error must have occurred
        for request_slot in self.state["request_slots"]:
            if request_slot not in self.goal["inform_slots"]:
                error_info["error"] = "Intent Error"
                error_info["error_turn_index"] = 2 * (len(self.dialog_turn_stack)) - 1
                error_info["num_turns"] = 2 * (len(self.dialog_turn_stack))
                error_info["status"] = INTENT_ERROR
                error_info["error_turn"] = self.dialog_turn_stack[-1][2]
                error_info["error_turn_slots"] = self.dialog_turn_stack[-1][3]
                error_info["error_slot"] = ""
                error_info["intent"] = self.dialog_turn_stack[-1][-1]
                return error_info

    def terminate_simulation_session_from_message(self,
                                                  bot_response,
                                                  bot_action_frame,
                                                  episode_index,
                                                  chat_log_json,
                                                  role):
        """ Check whether some terminal dialog turns have been triggered and the dialog should be terminated
        :param bot_response: bot API response, which may contain a list of messages
        :param bot_action_frame:  a frame/dict of info related to bot actions
        :param episode_index: index of the current episode
        :param chat_log_json: name of the chat log output
        :param role: name of the conversation side, i.e., BotSIM or agent
        :return:
        """
        if len(bot_response) == 0:
            return {"to_discard": True}
        # failed simulation
        if self.state["action"] == "fail" or bot_action_frame["round"] >= self.max_round:
            bot_action_frame["request_slots"].clear()
            bot_action_frame["inform_slots"].clear()
            return self.backtrack_simulation_errors()
        # failure due to intent errors
        if bot_action_frame["round"] >= self.intent_check_turn_index + 2 \
                and not self.state["intent_succeed"]:
            self.state["request_slots"]["fall_back"] = "UNK"
            bot_message = " ".join(bot_response)
            best_matching_dialog_act, _, _, _ = self.nlu_model.predict(bot_message, self.goal["name"])
            if best_matching_dialog_act == "":
                return {"to_discard": True}
            self.state["intent_error"] = (best_matching_dialog_act, self.state["user_response"], bot_message)
            chat_log_json[episode_index]["chat_log"].append(
                "{} {}: {}".format(bot_action_frame["round"], role, bot_message))
            return self.backtrack_simulation_errors()
        # successfully finished
        if self.state["action"] == "goodbye" or "Goodbye" in self.state["inform_slots"]:
            result = {"num_turns": bot_action_frame["round"], "error": "Success",
                      "status": 0, "error_turn_index": -1,
                      "error_turn": "", "error_turn_slots": "", "error_slot": ""}
            print("=" * 10 + " SUCCESS dialog " + "=" * 10)
            bot_action_frame["action"] = "success"
            bot_action_frame["request_slots"].clear()
            return result
        return None

    def terminate_simulation_session_from_dialog_acts(self,
                                                      best_bot_dialog_act,
                                                      matched_dialog_acts,
                                                      bot_message,
                                                      bot_action,
                                                      episode_index,
                                                      chat_log_json,
                                                      role_name):
        """
        Check whether dialog session should be terminated based on the matched bot dialog acts
        :param best_bot_dialog_act: best bot dialog act matched by the dialog act map file (template NLU)
        :param matched_dialog_acts: a list of agent actions matched from agent_message
        :param bot_message: bot message used for fuzzy matching
        :param bot_action: current agent action
        :param episode_index: goal index of the current episode
        :param chat_log_json:
        :param role_name: bot or BotSIM
        :return:
        """
        request_intent = False
        intent_failure = False
        intent_success = False
        num_request_slots, other_act = 0, 0
        if best_bot_dialog_act.find("NER_error") != -1:
            for slot in list(self.state["inform_slots"].keys()):
                self.state["ner_errors"][slot] = ("missed",
                                                  self.goal["inform_slots"][slot],
                                                  self.state["informed_user_turn"])
            return self.backtrack_simulation_errors()
        if best_bot_dialog_act == "runtime_failure":
            self.state["runtime_error"] = self.state["user_response"]
            print("\t" + cut_string(bot_message, 15), "[" + best_bot_dialog_act + "]")
            chat_log_json[episode_index]["chat_log"].append(bot_action["round"],
                                                            role_name, best_bot_dialog_act)
            return self.backtrack_simulation_errors()

        confused_dialog_acts = "["
        request_slots = set()
        # check the other system acts
        for dialog_act in matched_dialog_acts:
            if dialog_act[1].find("intent_success") != -1 and \
                    bot_action["round"] == self.intent_check_turn_index:
                intent_success = True
            elif dialog_act[1].find("intent_failure") != -1:
                intent_failure = True
            elif dialog_act[1].find("request_intent") != -1:
                request_intent = True
            elif dialog_act[1].find("request_") != -1:
                request_slots.add(dialog_act[1])
                confused_dialog_acts += dialog_act[1] + ","
            else:
                other_act += 1
        confused_dialog_acts = confused_dialog_acts[:-1] + "]"
        if intent_success:  self.state["intent_succeed"] = True
        # Ideally one bot message should be mapped to only one dialog act.
        # However, during conversation, the agent may call some internal functions
        # to fulfill user requests and generate some (dynamic) messages that are not available
        # during parsing stage. Under such circumstances, these unseen messages may not
        # be matched correctly by the dialog act maps.
        # Therefore, we apply some heuristics here: if one message is mapped to multiple
        # request acts, users need to manually examine such messages and revise their dialog act maps accordingly.
        # For example, adding these messages to "small_talk" dialog act so that they can be ignored by BotSIM.
        if len(request_slots) >= 2:
            error_message = "bot intent/dialog success message:"" + \
                            agent_message + "" has been mapped to multiple request dialog acts:[ " \
                            + confused_dialog_acts + "]\n"
            error_message += "Please revise the bot question file\n"
            error_message += "Considering \n" \
                             "  1) put irrelevant messages under small_talk dialog act so they " \
                             "will be ignored\n"
            raise Exception(error_message)

        if intent_failure:
            print("\t" + cut_string(bot_message, 15), "[" + best_bot_dialog_act + "]", matched_dialog_acts)
            chat_log_json[episode_index]["chat_log"].append(
                "{} {}: {}\n".format(bot_action["round"], role_name, bot_message))
            if bot_action["round"] == self.intent_check_turn_index:
                self.state["request_slots"]["fall_back"] = "UNK"
                self.state["intent_error"] = (best_bot_dialog_act, self.state["user_response"], bot_message)
            else:
                for slot in list(self.state["inform_slots"].keys()):
                    self.state["ner_errors"][slot] = ("missed",
                                                      self.goal["inform_slots"][slot],
                                                      self.state["informed_user_turn"])
            return self.backtrack_simulation_errors()

        for dialog_act in matched_dialog_acts:
            if dialog_act[1].find("dialog_success") != -1:
                if self.state["intent_succeed"]:
                    print("{} {}: {}\n".format(bot_action["round"], role_name, cut_string(bot_message, 15)))
                    print("=" * 10 + " SUCCESS dialog " + "=" * 10)
                    chat_log_json[episode_index]["chat_log"].append(
                        "{} {}: {}".format(bot_action["round"], role_name, bot_message))
                    result = {"num_turns": bot_action["round"], "error": "Success", "status": 0,
                              "error_turn_index": -1, "error_turn": "", "error_turn_slots": "", "error_slot": ""}
                    return result
                if bot_action["round"] >= self.intent_check_turn_index:  # a failure case
                    self.state["request_slots"]["fall_back"] = "UNK"
                    self.state["intent_error"] = \
                        ("fail", self.state["user_response"], bot_message)
                    print("\t" + cut_string(bot_message, 15), "[" + best_bot_dialog_act + "]")

                    chat_log_json[episode_index]["chat_log"].append("{} {}: {}".format(bot_action["round"],
                                                                                       role_name,
                                                                                       bot_message))

                    return self.backtrack_simulation_errors()

        return None

    def enqueue_bot_actions_from_bot_messages(self,
                                              bot_name,
                                              bot_api_response,
                                              bot_action,
                                              episode_index,
                                              chat_log_json):
        """
        Convert a bot api response (a consecutive sequence of bot messages), to a list of bot dialog acts.
        put the dialog acts in a queue inside dialog state to process one by one
        :param bot_name: name of the bot, e.g., TemplateBotSIM150
        :param bot_api_response: agent response list obtained from API calls, may contain multiple lines of messages
        :param bot_action: the current agent action
        :param episode_index:
        :param chat_log_json:
        :return: None if success, else return the error info
        """
        # for bots with user-initiated conversations like DialogFlow, the first agent message is empty
        if len(bot_api_response) == 0:
            self.state["bot_action_queue"].append(self.update_agent_action("request_intent", "", "", 0))
            bot_action["round"] = 1
            return
        # first check whether the agent response indicating termination of a conversation
        terminate_info = self.terminate_simulation_session_from_message(bot_api_response,
                                                                        bot_action,
                                                                        episode_index,
                                                                        chat_log_json,
                                                                        bot_name)
        if terminate_info:
            return terminate_info
        prev_act = ""
        pending_acts = []
        print(bot_action["round"], bot_name + ":")
        for bot_message in bot_api_response:
            # process one message in the bot api response list
            best_matching_dialog_act, best_matching_message, best_matching_score, matched_dialog_acts = \
                self.nlu_model.predict(bot_message, self.goal["name"])
            if bot_action["round"] == self.intent_check_turn_index:
                # check for intent errors on the intent_check_turn
                for intent_index, task in enumerate(self.nlu_model.intent_templates):
                    if task["intent"] == self.goal["name"]: continue
                    _, _, match_score, _ = self.nlu_model.predict(bot_message, task["intent"])
                    if match_score > best_matching_score:
                        self.state["request_slots"]["fall_back"] = "UNK"
                        self.state["intent_error"] = \
                            (best_matching_dialog_act, self.state["user_response"], bot_message)
                        print("\t" + cut_string(bot_message, 15), "[" + best_matching_dialog_act + "]")
                        chat_log_json[episode_index]["chat_log"].append(
                            "{} {}: {}".format(bot_action["round"], bot_name, bot_message))
                        return self.backtrack_simulation_errors()
            # merge same dialog acts and ignoring small talk dialog acts
            if best_matching_dialog_act not in ("small_talk", prev_act):
                terminate_info = self.terminate_simulation_session_from_dialog_acts(best_matching_dialog_act,
                                                                                    matched_dialog_acts,
                                                                                    bot_message, bot_action,
                                                                                    episode_index, chat_log_json,
                                                                                    bot_name)
                if terminate_info:
                    return terminate_info
                elif best_matching_dialog_act != "intent_success_message":
                    pending_acts.append((best_matching_dialog_act, bot_message, best_matching_message))

            print("\t" + cut_string(bot_message, 15), "[" + best_matching_dialog_act + "]")
            prev_act = best_matching_dialog_act

        if bot_action["round"] >= self.intent_check_turn_index and \
                not self.state["intent_succeed"]:
            self.state["request_slots"]["fall_back"] = "UNK"
            if best_matching_dialog_act == "":
                return {"to_discard": True}
            self.state["intent_error"] = (best_matching_dialog_act, self.state["user_response"], bot_message)
            print("\t" + cut_string(bot_message, 15), "[" + best_matching_dialog_act + "]")
            chat_log_json[episode_index]["chat_log"].append(
                "{} {}: {}".format(bot_action["round"], bot_name, bot_message))
            return self.backtrack_simulation_errors()

        for pending_dialog_act in pending_acts:
            self.state["bot_action_queue"].append(
                self.update_agent_action(pending_dialog_act[0],
                                         pending_dialog_act[1],
                                         pending_dialog_act[2],
                                         bot_action["round"]))
        chat_log_json[episode_index]["chat_log"].append(
            "{} {}: {}".format(bot_action["round"], bot_name, " ".join(bot_api_response)))
        bot_action["round"] = bot_action["round"] + 1

    def _response_to_request(self, bot_action):
        """
        Responding to "request" dialog act from bot.
        @param bot_action: bot action frame
        """
        # only one request slot allowed for agent
        requested_slots = list(bot_action["request_slots"].keys())
        assert len(requested_slots) == 1
        agent_request_slot = requested_slots[0]
        # case 1: if the requested slot is in the user goal, inform it
        if agent_request_slot in self.goal["inform_slots"]:
            self.state["request_slots"].clear()
            self.state["action"] = "inform"
            value = self.goal["inform_slots"][agent_request_slot]
            # for multi-intent goals,
            if isinstance(value, list):
                if len(value) == 0:
                    self.state["action"] = "fail"
                    self.state["inform_slots"].clear()
                    self.state["request_slots"][agent_request_slot] = "UNK"
                    return
                value = self.goal["inform_slots"][agent_request_slot].pop(0)

            self.state["inform_slots"][agent_request_slot] = value
            self.state["rest_slots"].pop(agent_request_slot, None)
            self.state["history_slots"][agent_request_slot] = value
            self.state["informed_user_turn"][agent_request_slot] = bot_action["round"] + 1
        # case 2: if the requested slot has already been informed
        elif agent_request_slot in self.goal["request_slots"] \
                and agent_request_slot in self.state["history_slots"]:
            self.state["request_slots"].clear()
            self.state["action"] = "inform"
            self.state["inform_slots"][agent_request_slot] = \
                self.state["history_slots"][agent_request_slot]
            assert agent_request_slot not in self.state["rest_slots"]
        else:
            self.state["action"] = "fail"
            self.state["inform_slots"].clear()
            self.state["request_slots"][agent_request_slot] = "UNK"

    def _response_to_inform(self, bot_action):
        """
        Responding to "inform" dialog act from the agent.
        @param bot_action: agent action
        """

        inform_slot = list(bot_action["inform_slots"].keys())[0]
        inform_value = bot_action["inform_slots"][inform_slot]

        self.state["history_slots"][inform_slot] = inform_value
        self.state["rest_slots"].pop(inform_slot, None)
        self.state["request_slots"].pop(inform_slot, None)
        # If the informed slot is in user goal
        # and the value does not match, then inform the correct value
        if inform_value != \
                self.goal["inform_slots"].get(inform_slot, inform_value):
            self.state["action"] = "inform"
            self.state["inform_slots"][inform_slot] = \
                self.goal["inform_slots"][inform_slot]
            self.state["request_slots"].clear()
            self.state["history_slots"][inform_slot] = \
                self.goal["inform_slots"][inform_slot]
        else:
            # Check if there are remaining slots to be requested, if so, request it from the agent
            if self.state["request_slots"]:
                self.state["action"] = "request"
            # - otherwise pick one randomly from the rest slots for inform
            elif self.state["rest_slots"]:
                key, value = random.choice(list(self.state["rest_slots"].items()))
                if value != "UNK":
                    self.state["action"] = "inform"
                    self.state["inform_slots"][key] = value
                    self.state["rest_slots"].pop(key)
                    self.state["history_slots"][key] = value
                else:
                    self.state["action"] = "request"
                    self.state["request_slots"][key] = "UNK"
            # Otherwise, all inform/request slots have been processed, indicating a successful dialog
            else:
                self.state["action"] = "goodbye"

    def _response_to_confirm(self, agent_action):
        pass
