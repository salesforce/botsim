#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random
from faker import Factory
import sre_yield
from google.cloud.dialogflowcx_v3beta1.services.agents import AgentsClient
from google.cloud.dialogflowcx_v3beta1.services.sessions import SessionsClient
from google.cloud.dialogflowcx_v3beta1.services.entity_types import EntityTypesClient
from google.cloud.dialogflowcx_v3beta1.types import IntentView, \
    ListIntentsRequest, ListFlowsRequest, ListPagesRequest, ListEntityTypesRequest

from botsim.botsim_utils.utils import seed_everything
seed_everything(42)
"""
Parser utilities  to deal with highly platform-dependent details
"""


############################################################
#   Retrieve metadata including intents, entities via APIs
############################################################

def create_session(agent_path):
    """ Create a DialogFlow CX session client
    :param agent_path: The absolute path to the CX agent/bot. For example,
    projects/["project_id"]/locations/["location_id"]/agents/["agent_id"]"
    :return:
        client_options
        session_client
    """
    agent_components = AgentsClient.parse_agent_path(agent_path)
    location_id = agent_components["location"]
    if location_id != "global":
        api_endpoint = f"{location_id}-dialogflow.googleapis.com:443"
        client_options = {"api_endpoint": api_endpoint}
    session_client = SessionsClient(client_options=client_options)
    return client_options, session_client


def list_intents(agent_path, intent_client):
    """ List all intents using API
    :param agent_path: parent agent path
    :param intent_client: dialogflow CX intent client
    :return:
       name_to_display_name: maps from raw intent names (random string representation) to human-readable names
       intents_to_phrases: maps from intents to their training phrases
    """
    name_to_display_name = {}
    intents_to_phrases = {}
    request = ListIntentsRequest(parent=agent_path, intent_view=IntentView.INTENT_VIEW_FULL)
    intents = intent_client.list_intents(request)
    for intent in intents:
        display_name = intent.display_name.replace(" ", "_").replace("/", "")
        name_to_display_name[intent.name] = display_name
        intents_to_phrases[display_name] = intent.training_phrases
    return name_to_display_name, intents_to_phrases


def list_entity_types(agent_path, client_options):
    """ List entity types using API
    :param agent_path: dialogflow CX agent path
    :param client_options: client options
    :return:
        name_to_display_name: maps from internal entity names to human-readable display names
        entities:  entities used in the bot
    """
    name_to_display_name = {}
    entities = {}
    entity_type_client = EntityTypesClient(client_options=client_options)
    entity_type_request = ListEntityTypesRequest(parent=agent_path)
    entity_types = entity_type_client.list_entity_types(entity_type_request)
    for et in entity_types:
        display_name = et.display_name.replace(" ", "_").replace("/", "")
        name_to_display_name[et.name] = display_name
        kind = et.kind
        if display_name not in entities:
            entities[display_name] = {"kind": kind}
        for ent in et.entities:
            value = ent.value
            synonyms = ent.synonyms
            entities[display_name][value] = list(synonyms)
    return name_to_display_name, entities


############################################################
#   Parse flows
############################################################

def parse_flow_transition_routes(flow_object, name_to_display_name):
    """ Parse the transition information of a flow.
    The transition information is in the "Routes" section, i.e., flow.transition_routes. The routes include
    1) an intent 2) a condition branch, 3) a fulfillment 4) another flow 5) another page
    :param flow_object: a DialogFlow CX  flow object
    :param name_to_display_name: mapping from an internal flow name to a human-readable display name
    :return: outgoing connections from this flow
    """
    transition = {"intent": {}, "condition": {}, "fulfillment": {}, "flow": [], "page": []}
    for i, transition_to in enumerate(flow_object.transition_routes):
        target = ""
        if transition_to.target_flow:
            target_flow = \
                name_to_display_name[transition_to.target_flow].strip().replace(" ", "_").replace("/", "")
            transition["flow"].append(target_flow)
            target = target_flow
        if transition_to.target_page:
            if transition_to.target_page not in name_to_display_name:
                assert transition_to.target_page.find("END_FLOW") != -1
                transition["page"].append("END_FLOW")
                target = "END_FLOW"
            else:
                target_page = \
                    name_to_display_name[transition_to.target_page].strip().replace(" ", "_").replace("/", "")
                transition["page"].append(target_page)
                target = target_page
        if transition_to.intent:
            # Some intents do not have any fulfilment messages, such as the Frequent Flyer Program page
            # (flights.frequent_flyer_club)
            message = ""
            transition["intent"].update({name_to_display_name[str(transition_to.intent)]: target})
            if not transition_to.trigger_fulfillment.messages:
                transition["fulfillment"].update({name_to_display_name[str(transition_to.intent)]: message})
            else:
                for msg in transition_to.trigger_fulfillment.messages:
                    message = ""
                    for t in msg.text.text:
                        t = remove_variable_name(t)
                        message = message + " " + str(t).replace("\n", "")
                if message == "": continue
                transition["fulfillment"].update({name_to_display_name[str(transition_to.intent)]: message})
        if transition_to.condition:
            transition["condition"].update({str(transition_to.condition): target})
    return transition


############################################################
#   Parse page transitions and forms
############################################################

def parse_page_transition_routes(page, name_to_display_name):
    """Parse page transitions/routes to the following types of destinations:
    1) an intent 2) a condition branch, 3) a fulfillment 5) another page
    :param page: a DialogFlow CX page object from API
    :param name_to_display_name: mapping from internal name to human-readable display name
    :return: outgoing connections from this page
    """
    entry_messages = []
    transition = {"intent": {}, "condition": {}, "fulfillment": {}, "flow": [], "page": [], "entry_messages": []}
    for i, transition_to in enumerate(page.transition_routes):
        target = ""
        if transition_to.target_flow:
            if transition_to.target_flow in name_to_display_name:
                target_flow = \
                    name_to_display_name[transition_to.target_flow].strip().replace(" ", "_").replace("/", "")
            else:
                target_flow = transition_to.target_flow.split("/")[-1]
            target = target_flow
            transition["flow"].append(target_flow)
        if transition_to.target_page:
            if transition_to.target_page in name_to_display_name:
                target_page = \
                    name_to_display_name[transition_to.target_page].strip().replace(" ", "_").replace("/", "")
            else:
                target_page = transition_to.target_page.split("/")[-1]
            transition["page"].append(target_page)
            target = target_page
        if transition_to.intent:
            if transition_to.trigger_fulfillment:
                message = ""
                for msg in transition_to.trigger_fulfillment.messages:
                    message = ""
                    for t in msg.text.text:
                        t = remove_variable_name(t)
                        message = message + " " + str(t).replace("\n", "")
                transition["intent"].update({name_to_display_name[str(transition_to.intent)]: target})
                transition["fulfillment"].update({name_to_display_name[str(transition_to.intent)]: message})
        if transition_to.condition:
            if transition_to.trigger_fulfillment:
                message = ""
                for msg in transition_to.trigger_fulfillment.messages:
                    message = ""
                    for t in msg.text.text:
                        t = remove_variable_name(t)
                        message = message + " " + str(t).replace("\n", "")
                transition["fulfillment"].update({str(transition_to.condition): message})
                transition["condition"].update({str(transition_to.condition): target})
    message = ""
    for msg in page.entry_fulfillment.messages:
        for t in msg.text.text:
            t = remove_variable_name(t)
            message = message + " " + str(t).replace("\n", "")
    if message != "":
        entry_messages.append(message.strip())
    transition["page_entry_messages"] = entry_messages
    return transition


def parse_page_form(form_object, name_to_display_name) -> list:
    """ Parse page form to get bot messages for requesting user entities.
    The page form contains parameters that are required to ``fulfill`` the page.
    They serve as the ``request`` entities for the dialog act map.
    For example, on the "Ask Amount" page, one required parameter is "amount_queried"
    with entity_type "@sys.unit-currency". The parameter is also associated with  a set
    of "initial prompt fulfillment" bot messages to collect values of such entities from users.
    :param form_object: the raw form data retrieved via API
    :param name_to_display_name: mapping from internal name to human-readable display name
    :return: a dict mapping from request dialog act to messages
    """
    request_to_messages = {}
    if form_object.parameters:
        for parameter in form_object.parameters:
            if parameter.entity_type in name_to_display_name:
                entity_type = "@" + name_to_display_name[parameter.entity_type]
            else:
                entity_type = "@" + (parameter.entity_type.split("/"))[-1]
            entity_name = parameter.display_name
            request_messages = []
            if parameter.fill_behavior:
                for prompt in parameter.fill_behavior.initial_prompt_fulfillment.messages:
                    message = ""
                    for msg in prompt.text.text:
                        msg = remove_variable_name(msg)
                        message = message + " " + str(msg).replace("\n", "")
                    # parameter.fill_behavior.initial_prompt_fulfillment.messages.text.text
                    request_messages.append(message)
                retry_messages = []
                for handler in parameter.fill_behavior.reprompt_event_handlers:
                    for trigger_message in handler.trigger_fulfillment.messages:
                        message = ""
                        for msg in trigger_message.text.text:
                            # parameter.fill_behavior.initial_prompt_fulfillment.messages.text.text:
                            msg = remove_variable_name(msg)
                            message = message + " " + str(msg).replace("\n", "")
                        retry_messages.append(message + "@" + handler.event)
            request_to_messages["request_" + entity_name + entity_type] = request_messages
    return request_to_messages


############################################################
# Infer dialog acts from flow/page messages
############################################################
def extract_intent_entry_and_success_messages_from_flow(transition_routes):
    """ Prepare intent_success_message from flow transition routes
    :param transition_routes: previously extracted flow transition routes
    :return:
      intent_success_message: bot message indicating the intent has been successfully recognised
    """
    request_intent_message = ""
    intent_to_flow = transition_routes["intent"]
    flow_to_intents = {}
    flow_to_intent_success_messages = {}
    for key in intent_to_flow:
        flow = intent_to_flow[key]
        if len(flow) > 0:
            if flow not in flow_to_intents:
                flow_to_intents[flow] = []
                flow_to_intent_success_messages[flow] = []
            flow_to_intents[flow].append(key)
            if key in transition_routes["fulfillment"]:
                flow_to_intent_success_messages[flow].append(transition_routes["fulfillment"][key])
        else:
            assert key == "Default_Welcome_Intent"
            if key in transition_routes["fulfillment"]:
                request_intent_message = transition_routes["fulfillment"][key]
    dialog_act = {}
    for flow in flow_to_intent_success_messages:
        dialog_act[flow] = {"intent_success_message": flow_to_intent_success_messages[flow]}
    return dialog_act, request_intent_message, flow_to_intents


def extract_dialog_success_messages_from_page(page_name, page_transition_routes, conversation_flows):
    """ Prepare ``dialog_success_messages``  from the parsed page data
    :param page_name: page name
    :param page_transition_routes: previously parsed page transition routes
    :param conversation_flows: the current conversation flows (will be updated in the function)
    :return:
      conversation_flows: updated conversation flow
      page_to_intents: mapping from page to its associated intents
    """
    page_to_intents = {}
    page_to_success_messages = {}
    for key in page_transition_routes["intent"]:
        target = page_transition_routes["intent"][key]
        if len(target) > 0:
            if target not in page_to_intents:
                page_to_intents[target] = []
                page_to_success_messages[target] = []
            page_to_intents[target].append(key)
            if key in page_transition_routes["fulfillment"]:
                page_to_success_messages[target].append(page_transition_routes["fulfillment"][key])

    for key in page_transition_routes["condition"]:
        target = page_transition_routes["condition"][key]
        if len(target) > 0:
            if target not in page_to_intents:
                page_to_intents[target] = []
                page_to_success_messages[target] = []
            page_to_intents[target].append(key)
            if key in page_transition_routes["fulfillment"]:
                page_to_success_messages[target].append(page_transition_routes["fulfillment"][key])
        else:
            if key in page_transition_routes["fulfillment"]:
                message = page_transition_routes["fulfillment"][key]
                act = "request_" + page_name + "@" + page_name
                if page_name not in page_to_success_messages:
                    page_to_success_messages[page_name] = []
                if page_name not in conversation_flows:
                    conversation_flows[page_name] = {}
                if act not in conversation_flows[page_name]:
                    conversation_flows[page_name][act] = []
                page_to_success_messages[page_name].append(page_transition_routes["fulfillment"][key])
                conversation_flows[page_name][act].append(message)

    for page in page_to_success_messages:
        if page not in conversation_flows:
            conversation_flows[page] = {"intent_success_message": page_to_success_messages[page]}
            conversation_flows[page].update({"flows": page_transition_routes["flow"]})
            conversation_flows[page].update({"pages": page_transition_routes["page"]})
        else:
            if "intent_success_message" not in conversation_flows[page]:
                conversation_flows[page]["intent_success_message"] = []
            if "flows" not in conversation_flows[page]:
                conversation_flows[page]["flows"] = []
            if "pages" not in conversation_flows[page]:
                conversation_flows[page]["pages"] = []

            conversation_flows[page]["intent_success_message"].extend(page_to_success_messages[page])
            conversation_flows[page]["flows"].extend(page_transition_routes["flow"])
            conversation_flows[page]["pages"].extend(page_transition_routes["page"])

    return conversation_flows, page_to_intents


def infer_dialog_act_from_page_entry_messages(page_entry_messages, node):
    """ Infer dialog acts from page entry messages according to heuristics/rules.
    This serves as a reference for users to design their own rules to map page entry messages
    to desired dialog acts. For this implementation, we are only dealing with two dialog acts,
    namely request and inform. All other "acts" are converted to these two types.
    :param page_entry_messages: page entry message
    :param node: the page node name
    :return: the inferred dialog act name
    """
    page_name = node.lower()
    if page_name.find("confirm_") != -1:
        dialog_act = "request_confirm_" + page_name + "@" + page_name
    elif page_name.find("show_") != -1 or page_name.find("confirmation") != -1:
        dialog_act = "inform_" + page_name
    elif page_name.find("display") != -1:
        dialog_act = "request_confirm_" + page_name + "@" + page_name
        for msg in page_entry_messages:
            if msg.find("?") == -1:
                dialog_act = "inform_" + page_name
    elif page_entry_messages[-1].find("?") != -1:
        dialog_act = "request_" + node + "@" + node
    else:
        dialog_act = "inform_" + page_name
    return dialog_act


############################################################
# Initialise entities for ontology
############################################################
def generate_entity_values(variable_name, cx_entities, number_values=200):
    """
    Generate entity values according to their types according to rules to kickstart simulation. This is because
    BotSIM does not have access to customer data that it can use during simulation.
    Users are advised to replace the randomly initialised values with real ones from their data.
    For example, the fake email addresses can be replaced with real ones.
    The rules listed here are by no means exhaustive, users may need more to initialise their novel entities.
    :param variable_name: variable name
    :param cx_entities: the entity information from list_entities
    :return:
        candidates: candidate values for the variable
        customer_entities: aggregated customer entities for ontology
    """
    customer_entities = {"Value": {}, "Pattern": {}, "System": {}, "variable_to_entity": {}}
    kind = str(cx_entities["kind"])
    key = list(cx_entities.keys())[0]
    candidates = []
    entity_name, entity_type = variable_name.split("@")
    for variable in cx_entities:
        if variable == "kind": continue
        if kind == "Kind.KIND_LIST":
            for ent in cx_entities[variable]:
                candidates.extend(generate_fake_values(ent, number_values))
                if entity_type not in customer_entities["System"]:
                    customer_entities["System"][entity_type] = []
                customer_entities["System"][entity_type].append(ent)
            customer_entities["variable_to_entity"][variable_name] = entity_type
        if kind == "Kind.KIND_MAP":
            for ent in cx_entities[variable]:
                candidates.append(ent)
            customer_entities["variable_to_entity"][variable_name] = entity_type
            if entity_type not in customer_entities["Value"]:
                customer_entities["Value"][entity_type] = []
            customer_entities["Value"][entity_type].extend(cx_entities[variable])
            customer_entities["variable_to_entity"][variable_name] = entity_type
        if kind == "Kind.KIND_REGEXP":  # regular expression
            value = sre_yield.AllStrings(variable)
            target_number = min(len(value), 100)
            candidates.extend(random.sample(list(value[:10000]), target_number))
            if key not in customer_entities["Pattern"]:
                customer_entities["Pattern"][key] = []
            customer_entities["Pattern"][key].append(cx_entities[variable])
            customer_entities["variable_to_entity"][key] = key
    return candidates, customer_entities


############################################################
# Misc./utility functions
############################################################
def remove_variable_name(text):
    """ Remove variable names in a message such as $Frequent_Flyer_Number$ for better fuzzy matching performance.
    This is because some variables have very long names and the bot intent is obtained via template matching.
    """
    message = ""
    items = text.split()
    for item in items:
        item = item.replace('"', "")
        if item[0] == "$" and (not items[1].isdigit()):
            item = "$"
        message = message + " " + item
    return message.strip()


def extract_small_talk_utts(intents_to_phrases):
    """ Extract the small talk utterances. small_talk has a set of pre-defined utterances
    for answering yes/no questions
    :param intents_to_phrases: mapping from intent to training phrases
    :return small_talk_phrases: map from small talks to utterances
    """
    small_talk_phrases = {}
    for key in intents_to_phrases:
        if key.find("small_talk.confirmation") != -1 or key.find("small_talk.dont_know") != -1:
            if key not in small_talk_phrases:
                small_talk_phrases[key] = []
            for p in intents_to_phrases[key]:
                for t in p.parts:
                    small_talk_phrases[key].append(t.text)
    return small_talk_phrases


def generate_fake_values(entity, number_values=200):
    """ Generate random values for given entity with fake values or pre-defined values.
    This is to initialise the entity values of the ontology.
    More rules can be added subsequently.
    """
    fake = Factory.create("en_US")
    candidates = []
    if entity == "@sys.number" or entity == "@sys.zip-code":
        candidates.extend(random.sample([str(i) for i in range(100)], 5))
    elif entity == "@sys.date":
        for _ in range(number_values):
            candidates.append(str(fake.future_date()))
    elif entity == "@sys.address":
        for _ in range(number_values):
            candidates.append(fake.address())
    elif entity == "@sys.email":
        for _ in range(number_values):
            candidates.append(fake.email())
    elif entity == "@sys.unit-currency":
        for _ in range(number_values):
            candidates.append(fake.currency())
    elif entity == "@sys.number-sequence":
        for _ in range(number_values):
            candidates.append(fake.credit_card_number())
    elif entity == "@sys.any":
        for _ in range(number_values):
            candidates.append(fake.name())
    elif entity == "@sys.time":
        for _ in range(number_values):
            candidates.append(str(fake.time()))
    elif entity == "@Anything_Else":
        candidates.append("No, thanks")
    elif entity == "@Select_Ticket_Type":
        candidates.extend(["single", "one-way", "two-way", "round trip", "round"])
    elif entity == "@Frequent_Flyer_Program":
        candidates.extend(["Yes", "No"])
    elif entity == "@Collect_Source":
        candidates.extend(["Credit", "credit card", "check"])
    elif entity == "@Ask_Payment":
        candidates.extend(["Yes", "No"])
    elif entity.find("@Confirm_") != -1:
        candidates.extend(["Yes", "No"])
    else:
        candidates.extend([entity])
        # raise Exception("Entity {} not included in the current bot, define your own rules to"
        #                 "generate the values.".format(entity))
    return candidates

