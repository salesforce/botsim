#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json, time, asyncio, requests, httpx

from botsim.modules.simulator.user_simulator import UserSimulator
from botsim.botsim_utils.utils import cut_string, seed_everything
from botsim.modules.simulator.simulation_client_base import UserSimulatorClientInterface

seed_everything(42)

# disable the TLS certification warnings
requests.packages.urllib3.disable_warnings(
    requests.packages.urllib3.exceptions.InsecureRequestWarning)

headers_raw = {
    "X-LIVEAGENT-AFFINITY": "",
    "X-LIVEAGENT-API-VERSION": "50"
}


class LiveAgentClient(UserSimulatorClientInterface):
    def __init__(self, config):
        super().__init__(config)

    def _process_bot_response_messages(self, api_response, processed_count, chat_messages, rich_messages):
        chat_response_json = json.loads(api_response.text)
        bot_message_sequence = chat_response_json["sequence"]
        processed_count += 1
        bot_name = ""
        message_type = chat_response_json["messages"][0]["type"]
        if message_type not in ("ChatMessage", "RichMessage"):
            return processed_count, "", bot_message_sequence
        for message in chat_response_json["messages"]:
            message_type = message["type"]
            if message_type == "ChatMessage":
                chat = message["message"]["text"].replace("\n", " ")
                chat_messages.append(chat)
                bot_name = message["message"]["name"]
            elif message_type == "RichMessage":
                for item in message["message"]["items"]:
                    text = item["text"].replace("\n", " ")
                    rich_messages.append(text)
        return processed_count, bot_name, bot_message_sequence

    async def perform_batch_simulation(self,
                                       simulation_goals,
                                       simulation_intent,
                                       start_episode,
                                       simulation_config):
        """ Async python client for calling LiveAgent API to perform dialog simulation starting from a given
        episode in a batch of 25 sessions as we need to reset the event loop for 25 sessions

        :param simulation_goals: list of simulation goals
        :param simulation_intent: intent for simulation
        :param start_episode: episode index to start
        :param simulation_config: the simulation setting configuration including
                                  the LiveAgent API end_pointers
        """

        batch_success, batch_ner_error, batch_intent_error, batch_other_error = 0, 0, 0, 0
        batch_turns, num_simulations = 0, 0

        user_simulator = UserSimulator(simulation_goals, simulation_config)

        end_point = simulation_config["api"]["end_point"]
        while start_episode < len(simulation_goals) and num_simulations < self.batch_size:
            failed = 0
            discard_episode = False
            print("Episode ", start_episode)
            user_simulator.reset(start_episode)
            self.dialog_logs[start_episode] = {"goal": user_simulator.goal, "chat_log": []}
            bot_action_frame = {"inform_slots": {}, "request_slots": {}, "round": 1,
                                "action": "", "question": ""}
            # The following message loop between BotSIM and bot follows LiveAgent API document at
            # https://developer.salesforce.com/docs/atlas.en-us.live_agent_rest.meta/live_agent_rest/live_agent_rest_API_requests.htm
            async with httpx.AsyncClient(verify=False) as client:
                # Step 1: create a live agent session
                retry = False  # retry for failed session connections
                api_response = ""
                try:
                    api_response = await client.get(end_point + "/rest/System/SessionId", headers=headers_raw)
                except httpx.RequestError as ex:
                    time.sleep(30)
                    retry = True
                if retry:
                    try:
                        api_response = await client.get(end_point + "/rest/System/SessionId", headers=headers_raw)
                    except httpx.RequestError:
                        time.sleep(30)
                        failed += 1
                        if failed == 3:  # return error if failed three times
                            return batch_success, \
                                   batch_ner_error, batch_intent_error, batch_other_error, \
                                   batch_turns, num_simulations
                        continue
                # Step 2: create a chat visitor session
                session_response = json.loads(api_response.text)
                client_poll_timeout = session_response["clientPollTimeout"] * 0.1
                chasitor_data = {
                    "agentId": None,
                    "buttonId": simulation_config["api"]["button_Id"],
                    "buttonOverrides": [],
                    "deploymentId": simulation_config["api"]["deployment_Id"],
                    "doFallback": True,
                    "isPost": True,
                    "language": "en-US",
                    "organizationId": simulation_config["api"]["org_Id"],
                    "prechatDetails": [],
                    "prechatEntities": [],
                    "receiveQueueUpdates": True,
                    "screenResolution": "2560x1440",
                    "sessionId": session_response["id"],
                    "userAgent": "LiveAgent Python Client v1.0.0",
                    "visitorName": "BotSIM"
                }
                retry = False
                try:
                    api_response = await client.post(end_point + "/rest/Chasitor/ChasitorInit",
                                                     data=json.dumps(chasitor_data),
                                                     headers={
                                                         "X-LIVEAGENT-API-VERSION": "50",
                                                         "X-LIVEAGENT-AFFINITY": session_response["affinityToken"],
                                                         "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                                     })
                except httpx.RequestError:
                    retry = True
                    time.sleep(10)
                if retry:
                    try:
                        api_response = await client.post(end_point + "/rest/Chasitor/ChasitorInit",
                                                         data=json.dumps(chasitor_data),
                                                         headers={
                                                             "X-LIVEAGENT-API-VERSION": "50",
                                                             "X-LIVEAGENT-AFFINITY": session_response["affinityToken"],
                                                             "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                                         })
                        if api_response.status_code != 200:
                            discard_episode = True
                    except httpx.RequestError:
                        print("ChasitorId retried", api_response, api_response.text)
                        time.sleep(10)
                        continue

                # Step 3 begin conversation
                bot_name = ""
                # The bot API response can have two types of messages, namely ChatMessage messages and RichMessage
                chat_messages = []
                rich_messages = []
                sequence = -1
                processed_count = 0
                session_finished = False
                # polling the first agent message
                while True:
                    try:
                        api_response = await client.get(end_point + "/rest/System/Messages",
                                                        headers={
                                                            "X-LIVEAGENT-API-VERSION": "50",
                                                            "X-LIVEAGENT-AFFINITY": session_response["affinityToken"],
                                                            "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                                        },
                                                        timeout=client_poll_timeout,
                                                        params={"ack": sequence, "pc": processed_count})
                    except httpx.RequestError:
                        break
                    if api_response.status_code != 200:
                        break
                    processed_count, bot_name, sequence = self._process_bot_response_messages(api_response,
                                                                                              processed_count,
                                                                                              chat_messages,
                                                                                              rich_messages)
                    if bot_name == "":
                        continue
                # meaning the initial message from agent is empty, continue for another try
                if len(chat_messages) == 0:
                    continue
                # Start the conversation between BotSIM and bot
                while not session_finished:
                    if len(chat_messages) == 0 \
                            and (user_simulator.state["action"] == "inform" or
                                 user_simulator.state["action"] == "request") \
                            and ("Goodbye" not in user_simulator.state["inform_slots"]):
                        discard_episode = True
                        break
                    # get a list of bot actions to respond based on bot messages  and put them
                    # to a queue user_simulator.state["bot_action_queue"]
                    # Meanwhile, the chat_messages will be checked for potential simulation errors and return
                    # the error info in "res". Otherwise, None will be returned
                    res = user_simulator.enqueue_bot_actions_from_bot_messages(bot_name,
                                                                               chat_messages,
                                                                               bot_action_frame,
                                                                               start_episode,
                                                                               self.dialog_logs)
                    if res and not discard_episode:
                        if "to_discard" in res or len(res) == 0:
                            discard_episode = True
                            break
                        episode_success, \
                        episode_intent_error, \
                        episode_ner_error, \
                        episode_other_error, \
                        episode_turns = user_simulator.log_episode_simulation_results(res,
                                                                                      start_episode,
                                                                                      self.dialog_logs,
                                                                                      self.dialog_errors)
                        batch_success += episode_success
                        batch_turns += episode_turns
                        batch_ner_error += episode_ner_error
                        batch_intent_error += episode_intent_error
                        batch_other_error += episode_other_error
                        break

                    # now the agent actions of the turn is in bot_action_frame_queue, we need to
                    # process them one by one
                    print(bot_action_frame["round"], "BotSIM: ")

                    concat_user_response = "{} BotSIM: ".format(bot_action_frame["round"])
                    # responding to multiple system actions in one turn
                    for act in user_simulator.state["bot_action_queue"]:
                        usr_action, natural_language_user_response, user_response_slots = user_simulator.policy(act)
                        user_simulator.state["user_response"] = natural_language_user_response
                        user_response = natural_language_user_response

                        user_simulator.dialog_turn_stack.append(
                            (usr_action,
                             bot_action_frame["round"],
                             natural_language_user_response,
                             user_response_slots,
                             simulation_intent))

                        print("\t" + cut_string(user_response, 15))

                        concat_user_response += " {} ".format(user_response)

                        replies = user_response
                        reply = {"text": replies}

                        if user_simulator.state["action"] == "fail":
                            self.dialog_logs[start_episode]["chat_log"].append(concat_user_response)
                            result = user_simulator.backtrack_simulation_errors()
                            session_finished = True
                        elif "Goodbye" in user_simulator.state["inform_slots"] \
                                or user_simulator.state["action"] == "thanks":
                            print("=" * 10 + " SUCCESS dialog " + "=" * 10)
                            self.dialog_logs[start_episode]["chat_log"].append(concat_user_response)
                            result = {"num_turns": bot_action_frame["round"], "error": "Success", "status": 0,
                                      "error_turn_index": -1, "error_turn": "", "error_turn_slots": "",
                                      "error_slot": ""}
                            session_finished = True
                        if session_finished:
                            episode_success, episode_intent_error, episode_ner_error, episode_other_error, \
                            episode_turns = user_simulator.log_episode_simulation_results(result,
                                                                                          start_episode,
                                                                                          self.dialog_logs,
                                                                                          self.dialog_errors)
                            batch_success += episode_success
                            batch_turns += episode_turns
                            batch_ner_error += episode_ner_error
                            batch_intent_error += episode_intent_error
                            batch_other_error += episode_other_error
                            break

                    self.dialog_logs[start_episode]["chat_log"].append(concat_user_response)

                    bot_action_frame["round"] = bot_action_frame["round"] + 1
                    user_simulator.state["bot_action_queue"] = []

                    # post  BotSIM response to bot
                    retry = False
                    try:
                        await client.post("{}/rest/Chasitor/ChatMessage".format(end_point),
                                          headers={
                                              "X-LIVEAGENT-API-VERSION": "50",
                                              "X-LIVEAGENT-AFFINITY": session_response["affinityToken"],
                                              "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                          }, data=json.dumps(reply))
                    except httpx.RequestError:
                        time.sleep(2)
                        retry = True

                    if retry:
                        try:
                            api_response = await client.post("{}/rest/Chasitor/ChatMessage".format(end_point),
                                                             headers={
                                                                 "X-LIVEAGENT-API-VERSION": "50",
                                                                 "X-LIVEAGENT-AFFINITY": session_response[
                                                                     "affinityToken"],
                                                                 "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                                             }, data=json.dumps(reply))
                            if api_response.status_code != 200:
                                discard_episode = True
                        except httpx.RequestError:
                            time.sleep(5)
                            break

                    bot_name = ""
                    chat_messages = []
                    rich_messages = []
                    api_response = None
                    # polling the next agent message
                    while True:
                        try:
                            api_response = await client.get("{}/rest/System/Messages".format(end_point),
                                                            headers={
                                                                "X-LIVEAGENT-API-VERSION": "50",
                                                                "X-LIVEAGENT-AFFINITY": session_response[
                                                                    "affinityToken"],
                                                                "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                                            },
                                                            timeout=client_poll_timeout,
                                                            params={"ack": sequence, "pc": processed_count})
                        except httpx.RequestError:
                            if api_response:
                                pass
                            break
                        if api_response.status_code != 200:
                            discard_episode = True
                            break
                        processed_count, bot_name, sequence = self._process_bot_response_messages(api_response,
                                                                                                  processed_count,
                                                                                                  chat_messages,
                                                                                                  rich_messages)
                        if bot_name == "":
                            continue
                retry = False
                try:
                    await client.post("{}/rest/Chasitor/ChatEnd".format(end_point),
                                      headers={
                                          "X-LIVEAGENT-API-VERSION": "50",
                                          "X-LIVEAGENT-AFFINITY": session_response["affinityToken"],
                                          "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                      },
                                      data=json.dumps({"type": "ChatEndReason", "reason": "client"}))
                    await client.aclose()
                except httpx.RequestError:
                    time.sleep(60)
                    retry = True
                if retry:
                    try:
                        api_response = await client.post("{}/rest/Chasitor/ChatEnd".format(end_point),
                                                         headers={
                                                             "X-LIVEAGENT-API-VERSION": "50",
                                                             "X-LIVEAGENT-AFFINITY": session_response["affinityToken"],
                                                             "X-LIVEAGENT-SESSION-KEY": session_response["key"]
                                                         },
                                                         data=json.dumps({"type": "ChatEndReason", "reason": "client"}))
                        if api_response.status_code != 200:
                            discard_episode = True
                        await client.aclose()
                    except httpx.RequestError:
                        print("ChatEnd retry exception")

            start_episode += 1
            if not discard_episode:
                num_simulations += 1

        return batch_success, batch_ner_error, batch_intent_error, batch_other_error, \
               batch_turns, num_simulations

    def simulate_conversation(self, database=None):
        simulation_goals, chatlog_file, user_error_turns_file = self._prepare_simulation()
        success, ner_error, intent_error, other_error, total_turns, total_episodes = 0, 0, 0, 0, 0, 0

        self.dialog_logs = {"summary": {}}
        self.dialog_errors = {}

        for episode_index in range(self.continue_episode, len(simulation_goals), self.batch_size):
            event_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(event_loop)
            episode_success, episode_ner_error, episode_intent_error, episode_other_error, episode_turns, episode_processed = \
                event_loop.run_until_complete(
                    self.perform_batch_simulation(
                        simulation_goals,
                        self.intent_name,  # .replace("_eval", ""),
                        episode_index, self.config))
            success += episode_success
            ner_error += episode_ner_error
            intent_error += episode_intent_error
            other_error += episode_other_error
            total_turns += episode_turns
            total_episodes += episode_processed

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

            time.sleep(3)
            if total_episodes % 50 == 0 and total_episodes > 0:
                header = "\n\n========= Simulation up to Episode " + \
                         str(total_episodes) + ": ==========\n"
                self.simulation_summary(header, total_episodes, total_turns, success, intent_error, ner_error,
                                        other_error)
        if total_episodes == 0:
            raise ConnectionRefusedError("all dialogs have been discarded")
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

