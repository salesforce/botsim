#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, copy, yaml

import xmlplain
from faker import Factory
from botsim.botsim_utils.utils import read_s3_data


############################################################
#   Parsing basic components of the bot_steps including
#   1) simple message 2) condition 3) bot invocation 4) navigation
#   Each function returns a string representation of the object
#   to be used later for creating dialog act maps and conversation
#   graph modelling
############################################################
def _parse_bot_step_simple_message(bot_steps):
    """ parse simple bot messages
    :param bot_steps: a bot_steps object/dict from the metadata
    :return str_rep: string representation of the parsed simple messages
    """
    assert isinstance(bot_steps, dict)
    message = bot_steps["botMessages"]["message"]
    message_type = bot_steps["type"]
    str_rep = "message type: " + message_type + ":" + message
    return str_rep


def _parse_botstep_conditions(bot_step_conditions):
    """ parsing the condition statements in a bot step object
    :param bot_step_conditions: a condition object/dict from the bot step
    :return: String representation of the condition: ``if left_value op_type right_value ''
    """
    assert isinstance(bot_step_conditions, dict)
    left_variable_name = bot_step_conditions["leftOperandName"]
    operation_type = bot_step_conditions["operatorType"]
    str_repr = "if " + left_variable_name + " " + operation_type
    if "rightOperandValue" in bot_step_conditions:
        str_repr += " " + bot_step_conditions["rightOperandValue"]
    return str_repr


def _parse_bot_invocation(bot_invocation):
    """Parsing botInvocation. Invocation includes calling other dialogs  or apex functions
    :param bot_invocation: botInvocation object as a list (multiple invocations) or dict (single invocation)
    :return: str_rep: A string representation of the intermediate results
    """
    mappings = []
    action_name = ""
    if isinstance(bot_invocation, dict):
        parameter_name = bot_invocation["invocationMappings"]["parameterName"]
        mapping_type = bot_invocation["invocationMappings"]["type"]
        action_name = bot_invocation["invocationActionName"]
        if "variableType" in bot_invocation["invocationMappings"]:
            variable_type = bot_invocation["invocationMappings"]["variableType"]
            variable_name = bot_invocation["invocationMappings"]["variableName"]
            mappings.append({parameter_name: variable_name,
                             "variableType": variable_type, "mappingType": mapping_type})
        else:
            mappings.append({parameter_name: "", "mappingType": mapping_type})
        str_rep = action_name + ": " + ",".join([str(m) for m in mappings])
        return str_rep
    # list of multiple invocations
    for item in bot_invocation:
        assert isinstance(item, dict)
        k = list(item.keys())[0]
        if k == "invocationActionName":
            action_name = item[k]
        elif k == "invocationMappings":
            if "variableType" in item[k]:
                variable_type = item[k]["variableType"]
                mapping_type = item[k]["type"]
                mappings.append({item[k]["parameterName"]: item[k]["variableName"],
                                 "variableType": variable_type,
                                 "mappingType": mapping_type})
            else:
                mappings.append({item[k]["parameterName"]: "", "mappingType": item[k]["type"]})
    str_rep = action_name + ": " + ",".join([str(m) for m in mappings])
    return str_rep


def _parse_bot_navigation(bot_navigation):
    """ Parsing dialog navigation.
    :param bot_navigation: A list (multiple targets) or a dict structured navigation data.
    :return: String representation (navigation type + target dialogs) of the navigation for post-processing
    """
    target_dialogs = []
    navigate_type = ""
    if isinstance(bot_navigation, list):
        for item in bot_navigation:
            assert isinstance(item, dict)
            k = list(item.keys())[0]
            if k == "type": navigate_type = item[k]
            if k == "botNavigationLinks":
                target_dialogs.append(item[k]["targetBotDialog"])
    else:
        if "botNavigationLinks" in bot_navigation:
            target_dialogs.append(bot_navigation["botNavigationLinks"]["targetBotDialog"])
        else:
            target_dialogs.append(bot_navigation["type"])
        navigate_type = bot_navigation["type"]
    return "Navigation via " + navigate_type + "[" + ",".join(target_dialogs) + "]"


############################################################
#   Parsing a bot step
############################################################
def _parse_bot_steps_list(bot_steps):
    """ parsing a list of bot_steps objects
    :param bot_steps: a botSteps object/dict
    :return:
      parsed_dialog_turns: a list of intermediate parsing results (from the above basic component
      parsing functions) for the object
      If the step is of type VariableOperation, the entity related info is given in the following two elements:
        variable_name: the variable name related to the entities if the step is VariableOperation
        entity_name: entity name of the requested variable
    """
    assert isinstance(bot_steps, list)
    parsed_dialog_turns, conditions = [], []
    pre_condition = False
    variable_name, entity_name = "", ""
    for item in bot_steps:
        key = list(item.keys())[0]
        if key == "botStepConditions":
            condition_name = _parse_botstep_conditions(item[key])
            conditions.append(condition_name)
        elif key == "botSteps":  # nested bot step
            if len(conditions) > 0:
                k = " and ".join(conditions)
                pre_condition = True
            step_type = item[key]["type"]  # Navigation
            value = ""
            step = item[key]
            if step_type == "Navigation":
                value = _parse_bot_navigation(step["botNavigation"])
            elif step_type == "VariableOperation":
                value, variable_name, entity_name = parse_bot_variable_operations(step["botVariableOperation"])
            elif step_type == "Invocation":
                value, target, mappings = _parse_bot_invocation(step["botInvocation"])
            elif step_type == "Message":
                value = _parse_bot_step_simple_message(step)
            if pre_condition:
                assert isinstance(value, str)
                parsed_dialog_turns.append(k + " " + value)
            else:
                parsed_dialog_turns.append(value)
            pre_condition = False
        elif key == "type":
            assert item[key] == "Group"
    return parsed_dialog_turns, variable_name, entity_name


def _parse_bot_steps(bot_steps):
    """ Parsing one bot step with the following step types: ``Message``, ``Navigation``, ``VariableOperation``,
    ``Invocation`` and ``Group``
    :param bot_steps: a botStep object
    :return:
      parsed_dialog_turns:  intermediate parsing results (from the above basic component
      parsing functions) for the object
      If the step is of type VariableOperation, the entity related info is given in the following two elements:
        variable_name: the variable name related to the entities if the step is VariableOperation
        entity_name: entity name of the requested variable
    """
    parsed_dialog_turns = []
    variable_name, entity_name = "", ""
    if isinstance(bot_steps, list):  # multiple conditions and multiple steps/branches
        return _parse_bot_steps_list(bot_steps)
    assert isinstance(bot_steps, dict)
    if bot_steps["type"] == "Message":
        parsed_dialog_turns.append(_parse_bot_step_simple_message(bot_steps))
    elif bot_steps["type"] == "Navigation":
        parsed_dialog_turns.append(_parse_bot_navigation(bot_steps["botNavigation"]))
    elif bot_steps["type"] == "VariableOperation":
        operation = bot_steps["botVariableOperation"]
        parsed_dialog_turn, variable_name, entity_name = parse_bot_variable_operations(operation)
        parsed_dialog_turns.append(parsed_dialog_turn)
    elif bot_steps["type"] == "Invocation":
        parsed_dialog_turns.append(_parse_bot_invocation(bot_steps["botInvocation"]))
    elif bot_steps["type"] == "Group":
        parsed_dialog_turn, variable_name, entity_name = parse_bot_steps_group(bot_steps)
        parsed_dialog_turns.append(parsed_dialog_turn)
    return parsed_dialog_turns, variable_name, entity_name


def parse_bot_steps_group(bot_steps_group):
    """
    Parsing botSteps with a group of operations
    1) bot_steps is a dict and its first key is botStepConditions and second key is BotSteps data
    2) no botStepConditions, just another normal operation,
       e.g., type: Navigation, type: VariableOperation
    :param bot_steps_group: a bot step group object
    :return:
    """
    parsed_condition, message = "", ""
    variable_name = ""
    entity_name = ""
    group = []
    if "botStepConditions" in bot_steps_group:
        parsed_condition = \
            _parse_botstep_conditions(bot_steps_group["botStepConditions"])
    if "botSteps" not in bot_steps_group:  return None
    operation = bot_steps_group["botSteps"]["type"]
    step = bot_steps_group["botSteps"]
    if operation == "Navigation":
        message = _parse_bot_navigation(step["botNavigation"])
    elif operation == "VariableOperation":
        message, variable_name, entity_name = parse_bot_variable_operations(step["botVariableOperation"])
    elif operation == "Invocation":
        message = _parse_bot_invocation(step["botInvocation"])
    elif operation == "message":
        message = _parse_bot_step_simple_message(step)
    else:
        message = operation
    assert isinstance(message, str)
    group.append(parsed_condition + " " + message)
    if len(parsed_condition) == 0:
        return message, variable_name, entity_name
    return group, variable_name, entity_name


############################################################
#   Parsing a dialog
############################################################

def _parse_bot_dialogs(dialog_info_list, intent_sets):
    """ Parse a dialog object step by step
    :param dialog_info_list: a list of dialog related infos including
        1) ``botSteps``: dialog definition in a set of bot steps
        2) ``mlIntent``: the intent set name for training the dialog intent
    :param intent_sets: the intent set containing the intent training utterances
    :return: parsed dialog and its entities
    """
    parsed_dialog_turns = []
    parsed_dialog = {}
    dialog_api_to_intent_set_api = {}
    # note one intent may have multiple intent sets
    intent_set_api_names = set()
    variable_to_entity = {}

    for info in dialog_info_list:
        if not isinstance(info, dict): continue
        k = list(info.keys())[0]
        if k == "botSteps":
            bot_steps, variable_name, entity_name = _parse_bot_steps(info[k])
            for step in bot_steps:
                while isinstance(step, list) and len(step) == 1:
                    step = step[0]
                if step and len(step) > 0:
                    parsed_dialog_turns.append(step)
            if variable_name != "":
                variable_to_entity[variable_name] = entity_name
        elif k == "developerName":
            dialog_api_name = info[k]
            parsed_dialog[dialog_api_name] = parsed_dialog_turns
        elif k == "mlIntent":
            intent_set_api_name = info[k]
            intent_utt_set = {}
            if "Intent_set" in intent_sets:
                intent_utt_set = intent_sets["Intent_set"]
            if "Intent_utts" in intent_sets:
                intent_utt_set.update(intent_sets["Intent_utts"])

            if intent_set_api_name in intent_utt_set:
                intent_set_api_names.add(intent_set_api_name)
                dialog_api_to_intent_set_api[dialog_api_name] = intent_set_api_name
    return parsed_dialog, dialog_api_to_intent_set_api, intent_set_api_names, variable_to_entity


def parse_botversions(bot_versions, api_name_to_intent_label, intent_sets):
    """Parse botversions metadata. The metadata contains the dialog definitions of the bot across all bot versions.
    This serves as the ``entry`` function of the parser to get the bot definitions
    :param bot_versions: the bot_version metadata retrieved from workbench
    :param api_name_to_intent_label: mapping from dialog api name to intent label
    :param intent_sets: intent set containing the intent training utterances
    :return:
    """

    parsed_dialogs = {}
    dialog_api_to_intent_set_api_map = {}
    dialog_to_intent_sets = set()

    variable_to_type = {}
    dialog_with_intents_labels = set()
    botversion_metadata = bot_versions

    if "botVersions" in bot_versions:
        botversion_metadata = bot_versions["botVersions"]
    for item in botversion_metadata:
        key = list(item.keys())[0]
        if key == "botDialogs":
            parsed_dialog, \
            dialog_api_to_intent_set_api, \
            intent_set_api_names, \
            variables = _parse_bot_dialogs(item[key], intent_sets)
            parsed_dialogs.update(parsed_dialog)
            dialog_api_to_intent_set_api_map.update(dialog_api_to_intent_set_api)
            dialog_to_intent_sets.update(intent_set_api_names)
            variable_to_type.update(variables)
        elif key == "conversationVariables":
            variable_to_type[item[key]["developerName"]] = item[key]["dataType"]

    for intent_api_name in dialog_to_intent_sets:
        intent_label_name = api_name_to_intent_label[intent_api_name].replace(" ", "_")
        dialog_with_intents_labels.add(intent_label_name)

    return parsed_dialogs, dialog_api_to_intent_set_api_map, dialog_to_intent_sets, \
           dialog_with_intents_labels, variable_to_type


############################################################
#   Infer dialog acts from bot messages
############################################################
def _parse_collect_bot_variable(bot_variable_operation):
    """ Parsing bot messages for collecting/requesting entities from users.
    The messages will be converted to ``request`` dialog acts in the dialog act maps.
    Meanwhile, the requested entities are extracted for ontology file
    :param bot_variable_operation: the botVariableOperation object (list or dict). The object associates
        bot messages with user entities.
    :return:
      dialog_act: the dialog act in the format of "request_"+variable_name+"~"+entity_name +":"+message
      variable_name: the variable which the entity value will be assigned to (for developers, targetName)
      entity_name: the entity name exposed to users (for users, sourceName)
    """
    message, entity_name = "", ""
    retry_messages = []
    if isinstance(bot_variable_operation, list):
        for item in bot_variable_operation:
            assert isinstance(item, dict)
            k = list(item.keys())[0]
            if k == "botMessages": message = item[k]["message"]
            if k == "botVariableOperands":
                variable_name = item[k]["targetName"]
                entity_name = item[k]["sourceName"]
            if k == "type": assert item[k] == "Collect"
            if k == "retryMessages": retry_messages.append(item[k]["message"])
    else:
        assert isinstance(bot_variable_operation, dict)
        assert bot_variable_operation["type"] == "Collect"
        message = bot_variable_operation["botMessages"]["message"]
        bot_variable_operands = bot_variable_operation["botVariableOperands"]
        variable_name = bot_variable_operands["targetName"]
        entity_name = bot_variable_operands["sourceName"]
        if "retryMessages" in bot_variable_operands:
            retry_messages.append(bot_variable_operands["retryMessages"])

    dialog_act = "request_" + variable_name + "~" + entity_name + ":" + message
    if len(retry_messages) > 0:  dialog_act += " [" + "&".join(retry_messages) + "]"
    return dialog_act, variable_name, entity_name


def parse_bot_variable_operations(bot_variable_operation):
    """ Parsing bot variable operations. The operation can be of the following types
    1) ``botInvocation`` to call other dialogs or apex code
    2) ``Unset`` or ``Set`` variables
    3) ``Collect`` information from user
    Note the list might not be comprehensive to cover all possible variable operations.
    :param bot_variable_operation: a dict or a list containing the bot_variable_operation object
    :return: String representation of the extracted dialog act as well as the entities
    """

    if isinstance(bot_variable_operation, list):
        return _parse_collect_bot_variable(bot_variable_operation)
    bot_variable_op_type = bot_variable_operation["type"]
    bot_variable_message = None
    variable_name = ""
    entity_name = ""
    if "botInvocation" in bot_variable_operation:
        invocation = \
            _parse_bot_invocation(bot_variable_operation["botInvocation"])
        bot_variable_message = bot_variable_op_type + " " + invocation
    elif bot_variable_op_type == "Unset":
        target_name = bot_variable_operation["botVariableOperands"]["targetName"]
        bot_variable_message = "Unset " + target_name
    elif bot_variable_op_type == "Set":
        print("Set ", bot_variable_operation)
    else:
        assert bot_variable_op_type == "Collect"
        bot_variable_message, \
        variable_name, \
        entity_name = _parse_collect_bot_variable(bot_variable_operation)
    return bot_variable_message, variable_name, entity_name


############################################################
#   Parse mlIntent for extracting intent utterances
############################################################

def _parse_multiple_ml_intents(ml_intents):
    """ Parse a list of mlIntent objects. Each object corresponds to a set of intent training utterances.
    Each mlIntent object may be used by multiple intent sets specified in ``relatedMlIntent''
    :param ml_intents: a list of mlIntent objects
    :return:
      related_intent_sets: names of intent sets  that are related to the mlIntent object
      intent_utterances: list of intent utterances aggregated across all mlIntents
      intent_set_api_name: api name of the intent set for developers
      intent_set_label: intent set label for users
    """
    assert isinstance(ml_intents, list)
    related_intent_sets, intent_utterances = [], []
    intent_set_api_name, intent_set_label = "", ""
    for item in ml_intents:
        k = list(item.keys())[0]
        if k == "developerName":
            intent_set_api_name = item[k]
        elif k == "mlIntentUtterances":
            utterance = item[k]["utterance"].replace('"', "").replace("\\u2019", "'")
            intent_utterances.append(utterance)
        elif k == "label":
            intent_set_label = item[k]
        elif k == "relatedMlIntents":
            related_intent_sets.append(item[k]["relatedMlIntent"])
    return related_intent_sets, intent_utterances, intent_set_api_name, intent_set_label


def _parse_ml_intents(ml_intents):
    """ Parsing mlIntent metadata of intent training utterances grouped into intent sets.
    :param ml_intents: mlIntents MetaData (list of multiple mlIntent objects or dict of single object).
    :return:
        intent_set_api_name: intent set developer/API name
        intent_utts_type: type of the intent utterances, ``Intent_set`` or ``Intent_utts``,
        intent_utts or related_intent_sets: list of intent utterances (if type == Intent_utts) or
        related intent sets (if type == Intent_set)
        intent_label_to_api_name: mapping from intent labels to api names
        api_name_to_intent_label: mapping from developer api names to user defined intent labels
    """
    intent_set_api_name, intent_set_label = "", ""
    related_intent_sets, intent_utts = [], []
    intent_label_to_api_name = {}
    api_name_to_intent_label = {}
    intent_utts_type = "Intent_utts"
    if isinstance(ml_intents, list):
        related_intent_sets, intent_utts, intent_set_api_name, intent_set_label = _parse_multiple_ml_intents(ml_intents)
    else:
        assert isinstance(ml_intents, dict)
        intent_set_api_name = ml_intents["developerName"]
        if "label" in ml_intents:
            intent_set_label = ml_intents["label"]
        if "relatedMlIntents" in ml_intents:
            if isinstance(ml_intents["relatedMlIntents"], dict):
                related_intent_sets.append(ml_intents["relatedMlIntents"]["relatedMlIntent"])
            else:
                assert isinstance(ml_intents["relatedMlIntents"], list)
                for item in ml_intents["relatedMlIntents"]:
                    k = list(item.keys())[0]
                    related_intent_sets.append(item[k])
    intent_label_to_api_name[intent_set_label] = intent_set_api_name
    api_name_to_intent_label[intent_set_api_name] = intent_set_label

    if len(related_intent_sets) > 0:
        intent_utts_type = "Intent_set"
        return intent_set_api_name, intent_utts_type, related_intent_sets, intent_label_to_api_name, api_name_to_intent_label
    return intent_set_api_name, intent_utts_type, intent_utts, intent_label_to_api_name, api_name_to_intent_label


############################################################
#   Parse ontology related metadata mlSlot
############################################################

def _parse_ml_slot_classes_dict(ml_slot_classes):
    """ Parse variables and their entity types.
    :param ml_slot_classes:
    :return:
      api_name: entity developer API name
      extract_type: Value, Pattern/Regex, UNKNOWN
      values: entity values if extract_type == Value
    """
    values, regex = set(), ""
    api_name = ml_slot_classes["developerName"]
    extract_type = ml_slot_classes["extractionType"]
    if "extractionRegex" in ml_slot_classes:
        assert extract_type == "Pattern"
        regex = ml_slot_classes["extractionRegex"]
        return api_name, "Pattern", regex
    if extract_type == "Value":
        if "mlSlotClassValues" not in ml_slot_classes:
            return api_name, extract_type, list(values)
        assert "mlSlotClassValues" in ml_slot_classes
        values.add(ml_slot_classes["mlSlotClassValues"]["value"])
        if "synonymGroup" not in ml_slot_classes["mlSlotClassValues"]:
            return api_name, extract_type, list(values)
        for item in ml_slot_classes["mlSlotClassValues"]["synonymGroup"]:
            assert isinstance(item, dict)
            k = list(item.keys())[0]
            if k == "terms":
                values.add(item[k])
        return api_name, extract_type, list(values)
    return api_name, "UNKNOWN", list(values)


def parse_ml_slot_classes(ml_slot_classes):
    """ parsing customer entities
    :param ml_slot_classes: customer entities in MetaData
    :return:
        api_name: entity API name of the entity
        intent_utt_type: entity extraction type: Pattern for regex, "Value" for value list
        values: if regex, return the regex pattern, otherwise return a set of values
    """
    values = set()
    entity_api_name = ""
    extract_type = "Value"
    if isinstance(ml_slot_classes, dict):
        return _parse_ml_slot_classes_dict(ml_slot_classes)
    assert isinstance(ml_slot_classes, list)
    for item in ml_slot_classes:
        k = list(item.keys())[0]
        if k == "developerName":
            entity_api_name = item[k]
        elif k == "mlSlotClassValues":
            values.add(item[k]["value"])
            if "synonymGroup" not in item[k]:
                continue
            if isinstance(item[k]["synonymGroup"], dict):
                values.add(item[k]["synonymGroup"]["terms"])
            else:
                assert isinstance(item[k]["synonymGroup"], list)
                for itm in item[k]["synonymGroup"]:
                    key = list(itm.keys())[0]
                    if key == "terms":
                        values.add(itm[key])
        return entity_api_name, extract_type, list(values)


def parse_ml_domain(ml_domain):
    """ Parsing the MlDomain Metadata that contains 1) intent sets (mlIntents) 2) customer entities (mlSlotClasses)
    :param ml_domain: mlDomain data from botVersions MetaData or the mlDomain MetaData
    :return:
        intent_utterances: a dict mapping from intent utterance types (intent utt or intent set) to
        a list of intent utterances
        customer_entities: a dict of customer entities and their extraction methods (Value or Pattern)
        intent_label_to_api_name: updated dict mapping from intent label to developer API name
        api_name_to_intent_label: updated dict mapping from intent api names to intent labels
    """

    intent_utterances = {}
    customer_entities = {}
    intent_label_to_api_name = {}
    api_name_to_intent_label = {}

    for item in ml_domain:
        data_type = list(item.keys())[0]
        if data_type == "mlIntents":  # intent utterances
            intent_set_api_name, intent_utterance_type, intent_utts, intent_to_api, api_to_intent_label \
                = _parse_ml_intents(item[data_type])
            intent_label_to_api_name.update(intent_to_api)
            api_name_to_intent_label.update(api_to_intent_label)
            if len(intent_utts) > 0:
                if intent_utterance_type not in intent_utterances:
                    intent_utterances[intent_utterance_type] = {}
                intent_utterances[intent_utterance_type][intent_set_api_name] = intent_utts
        if data_type == "mlSlotClasses":  # customer entities
            entity_api_name, extraction_type, values = parse_ml_slot_classes(item[data_type])
            if len(values) > 0:
                if extraction_type not in customer_entities:
                    customer_entities[extraction_type] = {}
                customer_entities[extraction_type][entity_api_name] = values
    return intent_utterances, customer_entities, intent_label_to_api_name, api_name_to_intent_label

def _apply_entity_value_initialisation_rules(variable, num_values=200):
    """
    Rules used to initialise the entity values
    """
    fake = Factory.create("en_US")
    candidates = []
    if variable.lower().find("goodbye") != -1:
        candidates.extend(["goodbye", "ciao"])
    elif variable.lower().find("email") != -1:
        for _ in range(num_values):
            candidates.append(fake.email())
    elif variable.lower().find("phone") != -1:
        for _ in range(num_values):
            candidates.append(fake.phone_number())
    elif variable.lower().find("last_name") != -1:
        for _ in range(num_values):
            candidates.append(fake.last_name())
    elif variable.lower().find("first_name") != -1:
        for _ in range(num_values):
            candidates.append(fake.first_name())
    elif variable.lower().find("name") != -1:
        for _ in range(num_values):
            candidates.append(fake.name())
    else:
        from botsim.botsim_utils.utils import random_text_generator
        candidates.append(random_text_generator())
    return candidates


def generate_entity_values(variable, variable_type, num_values=200):
    """ Generate entity values according to heuristics. More rules can be added to generate values for novel entities.
    """
    candidates = []
    if variable_type == "Text":
        candidates = _apply_entity_value_initialisation_rules(variable, num_values)
    elif variable_type == "Boolean":
        candidates = ["yes", "no"]
    else:
        candidates.append(variable)
    return candidates


############################################################
#   Convert the botversions and mlDomains metadata retrieved
#   from Salesforce Workbench to dict for subsequent
#   finer-grained parsing operations
############################################################

def extract_bot_version(parser_config):
    """ Extract botVersions  (bot designs) and botMlDomain (intent utterances) from the XML format botversions
    metadata retrieved from Salesforce Workbench. The XML data is converted to dictionaries for
    subsequent parser operations.
    Salesforce BotBuilder allows users to define intent utterances in the botversions metadata, although a
    more common approach is to organize the intent utterances into intent sets and included in the mlDomain
    metadata.
    :param parser_config: parse configuration
    :return:
      bot_versions: a dict of botVersions data
      ml_domains:  a dict of botMlDomain  data containing intent training utterances or intent set references
    """

    if os.environ.get("STORAGE") == "S3":
        botversion_xml = xmlplain.xml_to_obj(read_s3_data("botsim", parser_config["botversion_xml"]),
                                             strip_space=True, fold_dict=True)
    else:
        with open(parser_config["botversion_xml"]) as botversion_metadata:
            botversion_xml = xmlplain.xml_to_obj(botversion_metadata, strip_space=True, fold_dict=True)
    botversion_xml_yaml = xmlplain.obj_to_yaml(botversion_xml)
    data = yaml.safe_load(botversion_xml_yaml)
    ml_domains, bot_versions = {}, {}
    for item in data["Bot"]:
        if isinstance(item, dict):
            key = list(item.keys())[0]
            if key == "botMlDomain":
                ml_domains = copy.deepcopy(item)
            elif key == "botVersions":
                if isinstance(item[key], list):
                    if item[key][0]["fullName"] == "v" + parser_config["botversion"]:
                        bot_versions = copy.deepcopy(item)
                else:
                    bot_versions = copy.deepcopy(item)
    return bot_versions, ml_domains


def extract_intent_utterances(ml_domains_dir, ml_domain_to_intents, intent_utterances_meta=None):
    """ Extract the intent training utterances from the raw mlDomain metadata retrieved from workbench.
    The intent utterances are usually organized as intent sets in the mlDomain metadata.
    The mlDomain metadata also includes the customer entities.
    :param ml_domains_dir: the directory of the raw mlDomain metadata
    :param ml_domain_to_intents: mapping from mlDomain (intent sets) to a set of intents obtained from botversions
    :return: a dict mapping from intent names to intent training utterances
    """
    intent_to_utterances = {}
    for ml_domain in ml_domain_to_intents:
        # e.g., TemplateBotSIM
        intent_utt_xml = None
        if os.environ.get("STORAGE") == "S3":
            intent_utt_xml = xmlplain.xml_to_obj(
                read_s3_data("botsim", ml_domains_dir + "/" + ml_domain + ".mlDomain"),
                strip_space=True, fold_dict=True)
        elif os.path.exists(ml_domains_dir + "/" + ml_domain + ".mlDomain"):
            with open(ml_domains_dir + "/" + ml_domain + ".mlDomain") as mldomain:
                intent_utt_xml = xmlplain.xml_to_obj(mldomain, strip_space=True, fold_dict=True)
        elif intent_utterances_meta:
            with open(intent_utterances_meta) as intent_utts:
                intent_utt_xml = xmlplain.xml_to_obj(intent_utts, strip_space=True, fold_dict=True)
        if not intent_utt_xml:
            raise FileNotFoundError("intent utterance metadata {} not found".format(ml_domain + ".mlDomain"))
        intent_utt_yaml = xmlplain.obj_to_yaml(intent_utt_xml)
        data = yaml.safe_load(intent_utt_yaml)
        # process one mlDomain data
        intent_utterances, _, _, _ = parse_ml_domain(data["MlDomain"])
        for intent in ml_domain_to_intents[ml_domain]:
            combined_intent_name = ml_domain + "." + intent  # e.g., TemplateBotSIM.Connect_with_sales
            intent_to_utterances[combined_intent_name] = intent_utterances["Intent_utts"][intent]
    return intent_to_utterances


############################################################
#   Convert the botversions and mlDomains metadata retrieved
#   from Salesforce Workbench to dict for subsequent
#   finer-grained parsing operations
############################################################

def _process_navigation(turn_info):
    """
    Process navigation to other dialogs, unconditional or conditional
    :param turn_info: parsed turn data
    :return:
      condition: navigation condition (empty if unconditional)
      target: target dialog
    """
    items = turn_info.split()
    if items[0] == "Navigation":  # unconditional navigation to another dialog
        nav_type, target = items[2].split("[")
        target = target[:-1]
        condition = ""
    else:  # conditional navigation
        nav_type, target = items[-1].split("[")
        target = target[:-1]
        index = turn_info.find("Navigation")
        condition = turn_info[:index - 1].replace("if ", "").replace(" and ", "&").replace("Equals", "==")
    return condition, target


def get_dialog_transitions(parsed_dialogs):
    if len(parsed_dialogs) == 0:
        raise Exception("Fail to parse conversations from MetaData")
    edge_set = {}
    for dialog in parsed_dialogs:
        src = dialog
        i = 0
        while i < len(parsed_dialogs[dialog]):
            turn = parsed_dialogs[dialog][i]
            if isinstance(turn, dict):
                assert len(turn) == 1
                condition = list(turn.keys())[0]
                turn = condition + " " + turn[condition]
            if turn.find("Navigation via") != -1:
                condition, target = _process_navigation(turn)
                if src + " " + target not in edge_set:
                    edge_set[src + " " + target] = condition
            i += 1
    return edge_set
