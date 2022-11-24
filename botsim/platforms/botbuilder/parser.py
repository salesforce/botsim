#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, warnings, re, random, json
from abc import ABC
import networkx as nx
from botsim.modules.generator.parser import Parser
from botsim.modules.generator.utils.botbuilder import parser_utils
from botsim.botsim_utils.utils import dump_s3_file, file_exists, seed_everything

warnings.filterwarnings("ignore")
seed_everything(42)


class EinsteinBotMetaDataParser(Parser, ABC):
    """
    Parser for Einstein BotBuilder platform
    """

    def __init__(self, config):
        super().__init__(config)

        # A dict to store raw dialog messages or conditions extracted from the botversions metadata.
        # It is later processed to get the local dialog act maps
        self.parsed_dialogs = dict()
        self.variable_to_type = dict()
        # MlDomain is the MetaData for intent training utterances
        # Some bots may have multiple MlDomain metadata
        self.ml_domains = set()
        # a mapping from a MlDomain metadata to its intent members
        self.ml_domain_to_intents = dict()

        # The following two dicts map from intent labels (defined by the user)
        # and the api name (the underlying API name)
        self.api_name_to_intent_label = dict()
        self.intent_label_to_api = dict()

        # mapping from dialog/intent API name to its training utterances organised as intent sets
        self.dialog_api_to_intent_set_api = dict()

        # intent training utterances can either be organized as intent sets or simply list of utterances
        self.intent_to_utterances = None  # {"Intent_set": {}, "Intent_utts": {}}
        # Aggregate all the customer entities and they can either be value-based (Value) or regex-based (Pattern)
        self.customer_entities = {"Value": {}, "Pattern": {}}
        self.variable_to_entity = {}

        self.conversation_flow = {}

    def extract_ontology(self):
        """
        Extract ontology file from the dialog act maps.
        Ontology contains a list of entities and their sample values for each dialog/intent.
        The values are randomly initialised as BotSIM does not have access to real entity values that
        are usually related to users" products/services.
        BotSIM users are REQUIRED to revise the generated ontology file to replace the random values with
        real ones if they want to reliably test the entity models.
        :return dialog_ontology: a dict structured ontology
        """
        dialog_ontology = {}
        if len(self.dialog_act_maps) == 0:
            raise ValueError("Dialog act maps should have been completed at this point.")
        for dialog in self.dialog_act_maps:
            dialog_ontology[dialog] = {}
            for key in self.dialog_act_maps[dialog]:
                if key.find("request_") != -1:
                    variable = "_".join((key.split("_"))[1:])
                    variable_type = ""
                    variable_name = variable.split("@")[0]
                    if variable_name in self.variable_to_type:
                        variable_type = self.variable_to_type[variable_name]
                    dialog_ontology[dialog][variable] = []
                    # rule-based initialisation of entity values
                    dialog_ontology[dialog][variable] = \
                        parser_utils.generate_entity_values(variable, variable_type)
                elif key == "dialog_success_message":
                    tmp = []
                    informs = set()
                    for item in self.dialog_act_maps[dialog][key]:
                        if item != "":
                            tmp.append(item)
                            entities = re.findall("%s([a-zA-Z0-9_\.]*)%s" % ("{!", "}"), item)
                            informs.update(entities)
                    if len(informs) > 0:
                        if "success_informs" not in dialog_ontology[dialog]:
                            dialog_ontology[dialog]["success_informs"] = set()
                        dialog_ontology[dialog]["success_informs"].update(informs)
                    self.dialog_act_maps[dialog][key] = tmp

            if "success_informs" in dialog_ontology[dialog]:
                dialog_ontology[dialog]["success_informs"] = \
                    list(dialog_ontology[dialog]["success_informs"])
        return dialog_ontology

    def dump_intent_training_utterances(self, goals_dir, dev_ratio=0.6):
        """
        Extract and dump intent training utterances to files from the metadata.
        :param goals_dir: directory of the mlDomain metadata
        :param dev_ratio: dev set percentage of the original intent training utterances
        """
        excluded_dialogs = self.config["excluded_dialogs"]
        intent_utterances_meta = None
        if "MIUtterances_xml" in self.config:
            intent_utterances_meta = self.config["MIUtterances_xml"]
        intents_to_utts = parser_utils.extract_intent_utterances(goals_dir,
                                                                 self.ml_domain_to_intents,
                                                                 intent_utterances_meta)
        for intent in self.dialog_api_to_intent_set_api:
            intent_set_name = self.dialog_api_to_intent_set_api[intent]
            utterances = set()
            if intent_set_name in excluded_dialogs or \
                    (intent_set_name in self.api_name_to_intent_label and
                     self.api_name_to_intent_label[intent_set_name] in excluded_dialogs):
                continue
            if "Intent_set" in self.intent_to_utterances:
                # one intent set might be used  by multiple intents or an (meta) intent might use utterances
                # from multiple intent sets, i.e., related_intent_set
                for related_intent_set in self.intent_to_utterances["Intent_set"][intent_set_name]:
                    if related_intent_set in intents_to_utts:
                        utterances.update(intents_to_utts[related_intent_set])
            elif "Intent_utts" in self.intent_to_utterances:
                utterances.update(self.intent_to_utterances["Intent_utts"][intent_set_name])

            intent_utterances = list(utterances)
            # split the original intent utterances into dev and eval set according to the train_ratio
            random.shuffle(intent_utterances)
            dev_utts = intent_utterances[0:int(len(intent_utterances) * dev_ratio)]
            eval_utts = intent_utterances[int(len(intent_utterances) * dev_ratio):]
            target_eval_utts = "{}/{}_eval.json".format(goals_dir, intent)
            target_dev_utts = "{}/{}.json".format(goals_dir, intent)

            if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                if not file_exists("botsim", target_eval_utts):
                    dump_s3_file(target_dev_utts,
                                 bytes(json.dumps({intent: list(dev_utts)}, indent=2).encode("UTF-8")))
                    dump_s3_file(target_eval_utts,
                                 bytes(json.dumps({intent + "_eval": list(eval_utts)}, indent=2).encode("UTF-8")))
                else:
                    dump_s3_file(target_dev_utts,
                                 bytes(json.dumps({intent: list(intent_utterances)}, indent=2).encode("UTF-8")))
            else:
                if not os.path.exists(target_eval_utts):
                    with open(target_dev_utts, "w") as json_file:
                        json.dump({intent: list(dev_utts)}, json_file, indent=2)
                    with open(target_eval_utts, "w") as json_file:
                        json.dump({intent + "_eval": list(eval_utts)}, json_file, indent=2)
                else:
                    with open(target_dev_utts, "w") as json_file:
                        json.dump({intent: list(intent_utterances)}, json_file, indent=2)

        self.customer_entities["variable_to_entity"] = self.variable_to_type

        customer_entity_json = goals_dir + "/entities.json"
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            dump_s3_file(customer_entity_json,
                         bytes(json.dumps(self.customer_entities, indent=2).encode("UTF-8")))
        else:
            with open(customer_entity_json, "w") as json_file:
                json.dump(self.customer_entities, json_file, indent=2)

    def extract_local_dialog_act_map(self):
        """
        Extract local intent/dialog act maps ignoring the transitions from the parsed dialogs.
        The local dialog act maps are modelled as graph nodes for conversation graph modelling.
        In particular, the messages for the two special dialog acts, namely "intent_success_message"
        and "dialog_success_message" are also generated here according to the following heuristics:
            "intent_success_message" contains the first request message and all its previous normal messages
            "dialog_success_message" contains the last messages.
        There is another special dialog act, "small_talk", which contains all messages that are not informative
        to the intent/dialog. For example, "I can help you with that.", "I see you have previously contacted us".
        The matching of the "small_talk" act will be ignored by BotSIM during dialog simulation.
        """
        local_intent_dialog_acts = {}
        # remove variable names inside {} in the bot messages for better NLU performance via fuzzy matching
        regex = r"\{.*?\}"
        for dialog in self.parsed_dialogs:
            if dialog not in local_intent_dialog_acts:
                local_intent_dialog_acts[dialog] = {}
            i = 0
            last_message, first_request_message = "", ""
            # go through all the messages/actions of the dialog
            while i < len(self.parsed_dialogs[dialog]):
                turn = self.parsed_dialogs[dialog][i]
                if isinstance(turn, dict):
                    assert len(turn) == 1
                    condition = list(turn.keys())[0]
                    turn = condition + " " + turn[condition]
                if turn.find("request_") != -1:
                    dialog_act = (turn.split(":")[0]).split("~")[0]
                    entity = "_".join(dialog_act.split("_")[1:])
                    message = ":".join(turn.split(":")[1:])
                    message = re.sub(regex, "{}", message)

                    if message.find("[") != -1:
                        retry_messages = message[message.find("[") + 1:-1].split("&")
                        message = message[:message.find("[")]
                        message = re.sub(regex, "{}", message)
                        local_intent_dialog_acts[dialog]["NER_error_" + entity] = retry_messages
                    local_intent_dialog_acts[dialog][(turn.split(":")[0]).replace("~", "@")] = [message]
                    last_message = message

                    if first_request_message == "":
                        if "intent_success_message" in local_intent_dialog_acts[dialog]:
                            last_intent_success_message = \
                                local_intent_dialog_acts[dialog]["intent_success_message"][-1]
                            local_intent_dialog_acts[dialog]["intent_success_message"].append(
                                last_intent_success_message + " " + message)
                        else:
                            local_intent_dialog_acts[dialog]["intent_success_message"] = [message]
                        first_request_message = message
                # process non-request messages, e.g., inform or small talks
                elif turn.find("message type") != -1:
                    # case 1: normal messages
                    if turn.find("message type") == 0:
                        messages = []
                        message = ":".join(turn.split(":")[2:])
                        message = re.sub(regex, "{}", message)
                        messages.append(message)
                        j = i + 1
                        # The following while loop concat several consecutive messages into one
                        while j < len(self.parsed_dialogs[dialog]) and \
                                self.parsed_dialogs[dialog][j].find("message type") != -1:
                            turn = self.parsed_dialogs[dialog][j]
                            msg = ":".join(turn.split(":")[2:])
                            msg = re.sub(regex, "{}", msg)
                            message += msg
                            messages.append(msg)
                            j += 1
                        last_message = message
                        # if these messages are the first messages of the dialog
                        if "intent_success_message" not in local_intent_dialog_acts[dialog]:
                            local_intent_dialog_acts[dialog]["intent_success_message"] = messages
                        else:
                            local_intent_dialog_acts[dialog]["small_talk"] = messages
                        if j == len(self.parsed_dialogs[dialog]):
                            local_intent_dialog_acts[dialog]["dialog_success_message"] = messages
                        i = j - 1
                    else:  # if Pre_Chat_Case IsSet: "message type: Message:Looks like you\u2019ve already reported
                        index = turn.find("message type")
                        message = ":".join(turn[index:].split(":")[2:])
                        message = re.sub(regex, "{}", message)
                        local_intent_dialog_acts[dialog]["small_talk"] = [message]
                i += 1
            if last_message != "" and "dialog_success_message" not in local_intent_dialog_acts[dialog]:
                local_intent_dialog_acts[dialog]["dialog_success_message"] = [last_message]
                if "small_talk" in local_intent_dialog_acts[dialog] and \
                        last_message in local_intent_dialog_acts[dialog]["small_talk"]:
                    local_intent_dialog_acts[dialog].pop("small_talk")
        return local_intent_dialog_acts

    def conversation_graph_modelling(self, local_dialog_act, success_dialog="End_Chat",
                                     entry_dialog="Welcome",
                                     agent_confused_dialog="Confused"):
        """
        Performance conversation graph modelling on the local dialog act maps
        :param local_dialog_act: local dialog act maps for each dialog
        :param entry_dialog: the entry dialog of the bot, e.g., "Welcome"
        :param success_dialog: the ending dialog, e.g., "End Chat"
        :param agent_confused_dialog: the dialog for handling failed intent recognition gracefully.
        :return:
          dialog_act_maps: the aggregated dialog act maps from graph traversal source --> success_dialog
          visualisation_data: graph data for supporting dialog path visualisation
        """
        visualisation_data = {}
        node_set = set()
        for edge in self.conversation_flow:
            src, tgt = edge.split()
            node_set.add(src)
            node_set.add(tgt)
            condition = self.conversation_flow[edge]
            if src not in visualisation_data:
                visualisation_data[src] = {}
                visualisation_data[src]["flow"] = []
            if "page" not in visualisation_data[src]:
                visualisation_data[src]["page"] = []
            visualisation_data[src]["page"].extend(tgt.split(","))
            if "condition" not in visualisation_data[src]:
                visualisation_data[src]["condition"] = {}
            if condition != "":
                visualisation_data[src]["condition"][condition] = tgt

        conv_graph = nx.MultiDiGraph()  # Initialize a Graph object
        conv_graph.add_nodes_from(node_set)  # Add nodes to the Graph
        for e in self.conversation_flow:
            source, target = e.split(" ")[0], e.split(" ")[1]
            for tgt in target.split(","):
                conv_graph.add_edge(source, tgt, key=self.conversation_flow[e])
        dialog_act_maps = {}
        for dialog in self.dialog_api_to_intent_set_api:
            dialog_act_maps[dialog] = local_dialog_act[dialog]
            dialog_act_maps[dialog]["request_intent"] = local_dialog_act[entry_dialog]["dialog_success_message"]
            if dialog == success_dialog: continue
            for _, tgt in conv_graph.out_edges(dialog):
                if tgt == entry_dialog: continue
                for dialog_act in local_dialog_act[tgt]:
                    if dialog_act not in dialog_act_maps[dialog]:
                        dialog_act_maps[dialog][dialog_act] = local_dialog_act[tgt][dialog_act]
            paths = nx.all_simple_paths(conv_graph, dialog, success_dialog)
            for path in paths:
                for node in path[1:-1]:
                    for dialog_act in local_dialog_act[node]:
                        if dialog_act not in dialog_act_maps[dialog]:
                            dialog_act_maps[dialog][dialog_act] = local_dialog_act[node][dialog_act]
            if success_dialog in local_dialog_act and success_dialog != dialog:
                dialog_act_maps[dialog]["dialog_success_message"].extend(
                    local_dialog_act[success_dialog]["dialog_success_message"])

            if agent_confused_dialog in local_dialog_act:
                dialog_act_maps[dialog]["intent_failure_message"] = \
                    local_dialog_act[agent_confused_dialog]["intent_success_message"]

        return dialog_act_maps, visualisation_data

    def parse(self):
        """Einstein BotBuilder parser from botversions and MlDomain metadata"""
        # step 1: extract the botVersions and MlDomain MetaData
        bot_versions, ml_domains = parser_utils.extract_bot_version(self.config)
        # extract the MLDomain metadata containing intent training utterances
        self.intent_to_utterances, self.customer_entities, self.intent_label_to_api, self.api_name_to_intent_label = \
            parser_utils.parse_ml_domain(ml_domains["botMlDomain"])

        # step 2: parse botVersions data to get the dialog designs
        self.parsed_dialogs, self.dialog_api_to_intent_set_api, \
        self.dialog_with_intents, self.dialog_with_intents_labels, \
        self.variable_to_type = \
            parser_utils.parse_botversions(bot_versions, self.api_name_to_intent_label, self.intent_to_utterances)
        assert len(self.dialog_with_intents) > 0
        for intent in self.dialog_with_intents:
            if "Intent_set" not in self.intent_to_utterances: continue
            for related_intent_set in self.intent_to_utterances["Intent_set"][intent]:
                items = related_intent_set.split(".")
                if len(items) == 2:
                    domain, intent_name = related_intent_set.split(".")
                    self.ml_domains.add(domain)
                    if domain not in self.ml_domain_to_intents:
                        self.ml_domain_to_intents[domain] = []
                    self.ml_domain_to_intents[domain].append(intent_name)

        local_intent_dialog_act_maps = self.extract_local_dialog_act_map()
        self.local_dialog_act = local_intent_dialog_act_maps
        self.conversation_flow = parser_utils.get_dialog_transitions(self.parsed_dialogs)
        self.dialog_act_maps, self.conv_graph_visualisation_data = \
            self.conversation_graph_modelling(local_intent_dialog_act_maps)

        self.dialog_ontology = self.extract_ontology()
