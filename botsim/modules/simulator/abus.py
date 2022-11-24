#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random, copy

from botsim.conf.ABUS import FAILURE, botsim_default_key
from botsim.models.nlu.nlu_fuzzy_match import FuzzyMatchIntentPredictor
from botsim.models.nlg.nlg_template import TemplateNLG
from botsim.botsim_utils.utils import seed_everything

seed_everything(42)


class UserSimulatorInterface:
    """Agenda-based dialog user simulator interface.
    The interface, data structures and some functions are adapted from the GO-Bot-DRL repo
    (https://github.com/maxbren/GO-Bot-DRL/blob/master/user_simulator.py)
    """

    def __init__(self, simulation_goals, simulation_configs):
        """
        :param simulation_goals: a list of simulation goals
        :param simulation_configs: configurations for simulation
        """

        self.constraint_check = None
        self.state = None
        self.goal_list = simulation_goals
        self.max_round = simulation_configs["simulator"]["run_time"]["max_round_num"]
        self.default_key = botsim_default_key

        self.nlu_model = \
            FuzzyMatchIntentPredictor( simulation_configs["generator"]["file_paths"]["revised_dialog_act_map"])

        self.nlg_model = TemplateNLG(simulation_configs["generator"]["file_paths"]["response_template"])

        # a stack for keeping track of BotSIM dialog turns. Each element includes
        # 1. user dialog acts
        # 2. dialog_error_turn_index
        # 3. user_natural_lang_response
        # 4. user_natural_lang_response with slots
        # 5. the dialog/intent name for simulation
        self.dialog_turn_stack = []
        #  We check whether intents have been correctly recognized at intent_check_turn_index.
        #  Depending on who takes the first dialog turn, the index can be 2 (BotSIM-initiated like Einstein BotBuilder)
        #  or 3 (bot-initiated dialog like DialogFlow CX).
        self.intent_check_turn_index = int(simulation_configs["simulator"]["run_time"]["intent_check_turn_index"])

    def reset(self, index=-1):
        """
        Reset the simulation state by either randomly sampling or indexing
        """
        self.goal = random.choice(self.goal_list)
        if index >= 0:
            self.goal = self.goal_list[index]
        goals = list(self.goal["request_slots"].keys())
        self.default_key = goals[0]
        self.goal["request_slots"][self.default_key] = "UNK"
        """
        simulation state contains the following info:
        action: the current dialog state
        inform/request_slots: the current inform or request slots
        history_slots: slots that have been fulfilled in the past
        rest_slots: slots yet to be informed/requested
        user_response: natural language response from user
        ner/intent/runtime_error: keeping track of the errors
        bot_action_queue: a queue for agent dialog actions parsed from agent response to be processed one by one
        """
        self.state = {"action": "",
                      "inform_slots": {},
                      "request_slots": {},
                      "history_slots": {},
                      "rest_slots": {},
                      "user_response": "",
                      "ner_errors": {},
                      "intent_error": {},
                      "runtime_error": "",
                      "informed_user_turn": {},
                      "bot_action_queue": []}
        self.state["rest_slots"].update(self.goal["inform_slots"])
        self.state["rest_slots"].update(self.goal["request_slots"])
        self.constraint_check = FAILURE
        self.state["intent_succeed"] = False
        self.dialog_turn_stack = []

        return self._start_conversation()

    def _start_conversation(self):
        """
        Prepare the initial dialog state and BotSIM state for simulation.
        """

        self.state["action"] = "initial_action"
        self.goal["request_slots"].pop(self.default_key)
        if self.goal["request_slots"]:
            req_key = random.choice(list(self.goal["request_slots"].keys()))
        else:
            req_key = self.default_key
        self.goal["request_slots"][self.default_key] = "UNK"
        self.state["request_slots"][req_key] = "UNK"

        botsim_response = {"action": self.state["action"],
                           "request_slots": copy.deepcopy(self.state["request_slots"]),
                           "inform_slots": copy.deepcopy(self.state["inform_slots"]),
                           "response": ""}
        if "init_response" in self.goal:
            botsim_response["response"] = random.choice(self.goal["init_response"])
        self.state["user_response"] = botsim_response["response"]

        return botsim_response

    def enqueue_bot_actions_from_bot_messages(self,
                                              bot_name,
                                              bot_api_response,
                                              bot_action,
                                              episode_index,
                                              log_file):
        """ Convert bot_api_response (a consecutive bot messages), to a list of dialog acts
        and put them to a queue
        :param bot_name: name of the bot, e.g., TemplateBotSIM150
        :param bot_api_response: agent response list obtained from API calls, may contain multiple lines of messages
        :param bot_action: the current agent action
        :param episode_index:
        :param log_file:
        """
        raise NotImplementedError

    def policy(self, agent_action, episode=-1):
        """ Rule-based policy for BotSIM
        :param agent_action: input agent action
        :param episode: input agent action
        """
        raise NotImplementedError

    def _response_to_request(self, bot_action):
        """
        Response to bot request dialog acts
        :param bot_action: a semantic frame representation of bot request actions
        """
        raise NotImplementedError

    def _response_to_inform(self, bot_action):
        """ Response to bot inform dialog acts
        :param bot_action: a semantic frame representation of bot inform actions
        """

        raise NotImplementedError

    def _response_to_greeting(self):
        """ Response to the first system greeting message.
        """
        return self._start_conversation()

    def _response_to_confirm(self, bot_action):
        """ Response to bot confirm dialog acts
        :param bot_action: a semantic frame representation of bot confirm actions
        """
        raise NotImplementedError
