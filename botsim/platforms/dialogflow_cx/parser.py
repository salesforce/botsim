#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random, os, json
from abc import ABC
import networkx as nx

from google.cloud.dialogflowcx_v3beta1.services.intents import IntentsClient
from google.cloud.dialogflowcx_v3beta1.services.flows import FlowsClient
from google.cloud.dialogflowcx_v3beta1.services.pages import PagesClient
from google.cloud.dialogflowcx_v3beta1.types import IntentView, \
    ListIntentsRequest, ListFlowsRequest, ListPagesRequest, ListEntityTypesRequest

from botsim.botsim_utils.utils import dump_s3_file, file_exists, seed_everything
from botsim.modules.generator.parser import Parser
from botsim.modules.generator.utils.dialogflow_cx import parser_utils

seed_everything(42)


class DialogFlowCXParser(Parser, ABC):

    def __init__(self, config):
        super().__init__(config)

        self.flow_to_training_utts = None

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = config["cx_credential"]
        self.google_cloud_agent_path = \
            f'projects/{config["project_id"]}/locations/{config["location_id"]}/agents/{config["agent_id"]}'
        self.client_options, self.session_client = parser_utils.create_session(self.google_cloud_agent_path)
        self.intent_client = IntentsClient(client_options=self.client_options)
        self.customer_entities = {"Value": {}, "Pattern": {}, "System": {}, "variable_to_entity": {}}

        intent_name_to_display_name, self.intents_to_phrases = parser_utils.list_intents(
            self.google_cloud_agent_path, self.intent_client)
        entity_name_to_display_name, self.entities = \
            parser_utils.list_entity_types(self.google_cloud_agent_path, self.client_options)
        # mapping from internal random string api name to human-readable display name
        self.name_to_display_name = {}
        self.name_to_display_name.update(intent_name_to_display_name)
        self.name_to_display_name.update(entity_name_to_display_name)

        # the following dicts are used to support graph modelling and dialog path visualisation
        self.flow_graphs = {}
        self.page_graphs = {}
        self.flow_page_to_intents = {}

    def dump_intent_training_utterances(self, goal_dir, dev_ratio = 0.6):
        """
        Extract and dump intent training utterances to files from the metadata.
        :param goal_dir: target directory for storing intent utterances and goals
        :param dev_ratio: dev set percentage of the original intent training utterances
        """
        for flow in self.flow_to_training_utts:
            utterances = list(self.flow_to_training_utts[flow])
            random.shuffle(utterances)
            dev_utts = utterances[:int(len(utterances) * dev_ratio)]
            eval_utts = utterances[int(len(utterances) * dev_ratio):]

            target_eval_utts = "{}/{}_eval.json".format(goal_dir, flow)
            target_dev_utts = "{}/{}.json".format(goal_dir, flow)
            if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                if not file_exists("botsim", target_eval_utts):
                    dump_s3_file(target_dev_utts,
                                 bytes(json.dumps({flow: dev_utts}, indent=2).encode("UTF-8")))
                    dump_s3_file(target_eval_utts,
                                 bytes(json.dumps({flow + "_eval": eval_utts}, indent=2).encode("UTF-8")))
                else:
                    dump_s3_file(target_dev_utts,
                                 bytes(json.dumps({flow: utterances}, indent=2).encode("UTF-8")))
            else:
                if not os.path.exists(target_eval_utts):
                    with open(target_dev_utts, "w") as json_file:
                        json.dump({flow: dev_utts}, json_file, indent=2)
                    with open(target_eval_utts, "w") as json_file:
                        json.dump({flow + "_eval": eval_utts}, json_file, indent=2)
                else:
                    with open(target_dev_utts, "w") as json_file:
                        json.dump({flow: utterances}, json_file, indent=2)

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

        local_dialog_act_maps = {}
        flow_client = FlowsClient(client_options=self.client_options)
        page_client = PagesClient(client_options=self.client_options)
        raw_flows = flow_client.list_flows(ListFlowsRequest(parent=self.google_cloud_agent_path))

        # set up the mapping from internal api name to human readable display name
        for flow in raw_flows:
            self.name_to_display_name[flow.name] = flow.display_name.replace(" ", "_").replace("/", "")
            # a flow has a set of pages
            page_request = ListPagesRequest(parent=flow.name)
            pages = page_client.list_pages(page_request)
            for p in pages:
                self.name_to_display_name[p.name] = p.display_name.replace(" ", "_").replace("/", "")

        for flow in raw_flows:
            flow_name = flow.display_name.replace(" ", "_").replace("/", "")
            self.name_to_display_name[flow.name] = flow_name
            # get the transition routes from the current flow and store it as a graph node
            flow_transition = parser_utils.parse_flow_transition_routes(flow, self.name_to_display_name)
            self.flow_graphs[flow_name] = flow_transition

            # Extract the flow success message and its sets of intents (a flow may have multiple intents).
            flow_dialog_act_maps, request_intent_message, self.flow_to_intent = \
                parser_utils.extract_intent_entry_and_success_messages_from_flow(flow_transition)
            self.flow_page_to_intents.update(self.flow_to_intent)
            local_dialog_act_maps.update(flow_dialog_act_maps)

            # In addition to the flow routes/transitions, a flow can also lead to a page
            pages = page_client.list_pages(ListPagesRequest(parent=flow.name))
            # parse all pages of the current flow
            for p in pages:
                page_json = {}
                self.name_to_display_name[p.name] = p.display_name
                page_name = p.display_name.replace(" ", "_").replace("/", "")
                if page_name not in page_json:  page_json[page_name] = {}
                page_transition = parser_utils.parse_page_transition_routes(p, self.name_to_display_name)
                self.page_graphs[page_name] = page_transition
                page_to_success_messages, page_to_intents = \
                    parser_utils.extract_dialog_success_messages_from_page(page_name, page_transition,
                                                                           local_dialog_act_maps)
                self.flow_page_to_intents.update(page_to_intents)
                local_dialog_act_maps.update(page_to_success_messages)
                # The forms of the page contain the entities/values needed to be provided by the user
                if p.form:
                    request_to_messages = parser_utils.parse_page_form(p.form, self.name_to_display_name)
                    for dialog_act in request_to_messages:
                        page_json[page_name][dialog_act] = []
                        for msg in request_to_messages[dialog_act]:
                            msg = parser_utils.remove_variable_name(msg)
                            page_json[page_name][dialog_act].append(msg)
                        if page_name not in local_dialog_act_maps:
                            local_dialog_act_maps[page_name] = {}
                        local_dialog_act_maps[page_name].update({dialog_act: page_json[page_name][dialog_act]})
        self.flow_graphs.update(self.page_graphs)
        for key in self.flow_graphs:
            if key not in local_dialog_act_maps: continue
            local_dialog_act_maps[key]["flows"] = self.flow_graphs[key]["flow"]
            local_dialog_act_maps[key]["pages"] = self.flow_graphs[key]["page"]

        return local_dialog_act_maps

    def extract_intent_training_utterances(self):
        name_to_display_name, intents_to_phrases = \
            parser_utils.list_intents(self.google_cloud_agent_path, self.intent_client)
        self.name_to_display_name.update(name_to_display_name)
        flow_to_training_utts = {}
        for key in self.flow_page_to_intents:
            if key not in self.flow_to_intent: continue
            for intent in self.flow_to_intent[key]:
                phrases = intents_to_phrases[intent]
                flow_to_training_utts[key] = []
                for p in phrases:
                    utt = ""
                    for t in p.parts:
                        utt = utt + " " + t.text
                    flow_to_training_utts[key].append(utt.strip())
        return flow_to_training_utts

    def conversation_graph_modelling(self, local_dialog_acts, success_dialog="END_SESSION"):
        """
        Performance conversation graph modelling on the local dialog act maps
        :param local_dialog_acts: local dialog act maps for each dialog
        :param success_dialog: the ending dialog, e.g., "End Chat"
        :return:
          dialog_act_maps: the aggregated dialog act maps from graph traversal source --> success_dialog
          visualisation_data: graph data for supporting dialog path visualisation
        """
        # first we pool the flow and page graphs together
        conv_graph = self.flow_graphs
        conv_graph.update(self.page_graphs)

        all_flows = set()
        all_pages = set()
        edge_set = dict()
        node_set = set()
        # In DialogFlow CX, there are four transition types which are used as the graph edge labels
        transition_types = set(["flow", "page", "condition", "intent"])
        # Messages indicating a successfully completed (fulfilled) flow or page
        flow_page_to_fulfillment_messages = {}
        for flow in conv_graph:
            transition = conv_graph[flow]
            for transition_type in transition:
                if transition_type in transition_types:
                    for elem in transition[transition_type]:
                        if transition_type == "condition" or transition_type == "intent":
                            src = flow
                            link, tgt = elem, transition[transition_type][elem]
                        else:
                            src, tgt, link = flow, elem, transition_type
                        if transition_type == "flow":
                            all_flows.add(tgt)
                        elif transition_type == "page":
                            all_pages.add(tgt)
                        node_set.add(src)
                        node_set.add(tgt)
                        if src + " " + tgt in edge_set:
                            edge_set[src + " " + tgt] = edge_set[src + " " + tgt] + "/" + link
                        else:
                            edge_set[src + " " + tgt] = link

            for intent in conv_graph[flow]["intent"]:
                target = conv_graph[flow]["intent"][intent]
                if intent in conv_graph[flow]["fulfillment"]:
                    fulfillment = conv_graph[flow]["fulfillment"][intent]
                    if len(fulfillment) == 0: continue
                    if target not in flow_page_to_fulfillment_messages:
                        flow_page_to_fulfillment_messages[target] = set()
                    flow_page_to_fulfillment_messages[target].add(fulfillment)

        visualisation_data = {}
        graph = nx.MultiDiGraph()
        graph.add_nodes_from(node_set)
        for edge in edge_set:
            items = edge.split()
            if len(items) == 2:
                src, tgt = items[0], items[1]
            else:
                src = items[0]
                tgt = ""
            condition = edge_set[edge]
            graph.add_edge(src, tgt, key=condition)
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
        dialog_act_maps = {}
        flow_page_with_intents = \
            conv_graph["Default_Start_Flow"]["flow"] + conv_graph["Default_Start_Flow"]["page"]
        if len(conv_graph["Default_Start_Flow"]["page"]) == 0:  # fin service
            success_dialog = "END_SESSION"
        else:
            success_dialog = "END_FLOW"
        for flow in flow_page_with_intents:
            paths = nx.all_simple_paths(graph, source=flow, target=success_dialog)
            dialog_act_maps[flow] = {}
            for path in paths:
                # break the cycle by preventing the dialog to return to Default_Start_Flow
                if "Default_Start_Flow" in path: continue
                if path[0] not in local_dialog_acts: continue
                if len(local_dialog_acts[path[0]]["intent_success_message"]) > 0:
                    if "intent_success_message" not in dialog_act_maps[flow]:
                        dialog_act_maps[flow]["intent_success_message"] = set()
                    for msg in local_dialog_acts[path[0]]["intent_success_message"]:
                        dialog_act_maps[flow]["intent_success_message"].add(msg)
                if path[0] in flow_page_to_fulfillment_messages:
                    dialog_act_maps[flow]["intent_success_message"].update(
                        flow_page_to_fulfillment_messages[path[0]])
                elif len(self.page_graphs[path[0]]["page_entry_messages"]) > 0:
                    dialog_act_maps[path[0]]["intent_success_message"] = \
                        set(self.page_graphs[path[0]]["page_entry_messages"])

                # process the start and end node of the path
                if path[0] in self.page_graphs and len(
                        self.page_graphs[path[0]]["page_entry_messages"]) > 0:  # Select_Ticket_Type
                    if self.page_graphs[path[0]]["page_entry_messages"][-1].find("?") != -1:
                        dialog_act_maps[flow]["request_" + path[0] + "@" + path[0]] = \
                            self.page_graphs[path[0]]["page_entry_messages"]
                if path[-1] in local_dialog_acts and len(local_dialog_acts[path[-1]]["intent_success_message"]) > 0:
                    if "dialog_success_message" not in dialog_act_maps[flow]:
                        dialog_act_maps[flow]["dialog_success_message"] = set()
                    for msg in local_dialog_acts[path[-1]]["intent_success_message"]:
                        dialog_act_maps[flow]["dialog_success_message"].add(msg)
                if path[-1] in flow_page_to_fulfillment_messages:
                    dialog_act_maps[flow]["dialog_success_message"].update(
                        flow_page_to_fulfillment_messages[path[-1]])
                # process the rest nodes on the path
                path = path[1:-1]
                for node in path:
                    if node in all_pages:
                        page_entry_messages = self.page_graphs[node]["page_entry_messages"]
                        if len(page_entry_messages) > 0:  # possible inform messages
                            act = parser_utils.infer_dialog_act_from_page_entry_messages(page_entry_messages, node)
                            dialog_act_maps[flow][act] = page_entry_messages
                    if node not in local_dialog_acts: continue
                    for act in local_dialog_acts[node]:
                        if act == "flow" or act == "pages" or act == "intent_success_message": continue
                        if act not in dialog_act_maps[flow]:
                            dialog_act_maps[flow][act] = set(local_dialog_acts[node][act])
                        dialog_act_maps[flow][act].update(local_dialog_acts[node][act])
            if len(dialog_act_maps[flow]) == 0: dialog_act_maps.pop(flow)
        for flow in dialog_act_maps:
            if "flows" in dialog_act_maps[flow]:  dialog_act_maps[flow].pop("flows")
            for act in dialog_act_maps[flow]:
                dialog_act_maps[flow][act] = list(set(dialog_act_maps[flow][act]))

        for flow in local_dialog_acts:
            acts = local_dialog_acts[flow]
            if flow not in dialog_act_maps: continue
            for act in acts:
                if act == "flows" or act == "pages": continue
                if act not in dialog_act_maps[flow]:
                    dialog_act_maps[flow][act] = local_dialog_acts[flow][act]

        return dialog_act_maps, visualisation_data

    def extract_ontology(self):
        """
        Extract ontology file from the dialog act maps.
        Ontology contains a list of entities and their sample values for each dialog/intent.
        The values are randomly initialised as BotSIM does not have access to real entity values that
        are usually related to users" products/services.
        BotSIM users are REQUIRED to revise the generated ontology file to replace the random values with
        real ones if they want to reliably test the entity models.
        :return $Z$Z$ontology: a dict structured ontology
        """
        ontology = {}
        self.customer_entities = {"Value": {}, "Pattern": {}, "System": {}, "variable_to_entity": {}}
        for flow in self.dialog_act_maps:
            ontology[flow] = {}
            for key in self.dialog_act_maps[flow]:
                if key.find("request_") != -1:
                    items = key.split("_")
                    entity = "_".join(items[1:])
                    entity_type = entity.split("@")[-1]
                    entity = entity.split("@")[0]
                    if entity_type in self.entities:
                        values, entity_info = \
                            parser_utils.generate_entity_values("_".join(items[1:]), self.entities[entity_type])
                        ontology[flow][entity + "@" + entity_type] = values
                        for key in self.customer_entities:
                            if len(entity_info[key]) > 0:
                                self.customer_entities[key].update(entity_info[key])
                    elif entity.find("confirm") != -1:
                        ontology[flow][entity + "@" + entity_type] \
                            = parser_utils.extract_small_talk_utts(self.intents_to_phrases)[
                            "small_talk.confirmation.no"]
                        ontology[flow][entity + "@" + entity_type].extend(
                            parser_utils.extract_small_talk_utts(self.intents_to_phrases)[
                                "small_talk.confirmation.yes"])
                    else:
                        ontology[flow][entity + "@" + entity_type] = \
                            parser_utils.generate_fake_values("@" + entity_type)
        return ontology

    def parse(self):
        local_dialog_act = self.extract_local_dialog_act_map()
        self.local_dialog_act = local_dialog_act
        self.flow_to_training_utts = self.extract_intent_training_utterances()
        self.dialog_act_maps, self.conv_graph_visualisation_data = \
            self.conversation_graph_modelling(local_dialog_act)

        self.dialog_ontology = self.extract_ontology()

        self.dialog_with_intents_labels = set(self.dialog_act_maps.keys())
        self.dialog_with_intents = set(self.dialog_act_maps.keys())
