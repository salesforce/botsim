

#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

class Parser:
    """
    Parser interface. The parser takes in raw bot definitions either via MetaData (Salesforce Einstein BotBuilder) or
    API calls as inputs and performs the following tasks:
    1) Extracts bot design related data including the dialog act maps, ontology
    2) Models bot designs as graphs
    """
    def __init__(self, parser_config={}):
        """
        Attributes of the parser class.
        """
        self.config = parser_config
        self.dialog_act_maps = {}
        self.dialog_ontology = {}
        self.customer_entities = {}
        # For some platforms, e.g., Salesforce Einstein BotBuilder, users are allowed to rename the
        # intent labels, causing inconsistency between the API variable name to the user-defined labels.
        # api_name_to_intent_label is used to bridge the map to map API name to intent labels
        self.api_name_to_intent_label = {}
        # dialog_with_intents_label \in dialog_with_intents
        self.dialog_with_intents = set()
        self.dialog_with_intents_labels = None
        self.local_dialog_act = {}
        self.conv_graph_visualisation_data = {}

    def dump_intent_training_utterances(self, target_dir):
        """
        Dump the intent training utterances to local for subsequent paraphrasing
        :param target_dir: target directory
        """
        raise NotImplementedError

    def extract_ontology(self):
        """
        Extract the ontology containing a list of mappings from intent/dialog names to entities
        The values for each entity are randomly initialised according to some rules/heuristics.
        BotSIM users are REQUIRED to revise the generated json file to include real entity values
        if they want to test the entity recognition models as well
        """
        raise NotImplementedError

    def extract_dialog_act_templates(self):
        """ Extract the dialog act templates for all dialogs to generate the question file
        """
        return self.dialog_act_maps

    def extract_local_dialog_act_map(self):
        """ Extract local dialog act maps for each dialog
        """
        raise NotImplementedError

    def conversation_graph_modelling(self, local_dialog_act):
        """Perform conversation graph modelling to generate the aggregated dialog act maps
        :param local_dialog_act: local dialog act maps (one per dialog) from the initial parsing
        :return:
            dialog_act_maps: aggregated dialog act maps (to be reviewed/revised and used as BotSIM NLU)
            conv_graph_visualisation_data: conversation flow visualisation data
        """
        raise NotImplementedError

    def parse(self):
        # extract local dialog act maps which are later modelled as graph nodes
        local_dialog_act = self.extract_local_dialog_act_map()
        self.local_dialog_act = local_dialog_act
        self.dialog_act_maps, self.conv_graph_visualisation_data = \
            self.conversation_graph_modelling(local_dialog_act)
        self.dialog_with_intents_labels = set(self.dialog_act_maps.keys())
        self.dialog_with_intents = set(self.dialog_act_maps.keys())

        self.dialog_ontology, self.customer_entities = self.extract_ontology()
