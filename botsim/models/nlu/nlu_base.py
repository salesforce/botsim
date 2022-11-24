#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.botsim_utils.utils import load_intent_examples
class IntentDetector:
    def __init__(self, dialog_act_map_path):
        self.intent_templates = None
        if dialog_act_map_path:
            dialog_act_maps = load_intent_examples(dialog_act_map_path)
            self.intent_templates = []
            for intent in dialog_act_maps:
                self.intent_templates.append({"intent": intent, "dialog_act_and_slot": dialog_act_maps[intent]})
    def predict(self, bot_message, dialog_name, *args):
        """
        Predict the intent labels given the bot message via template-matching
        :param bot_message: bot message/prompt for the intent query
        """
        raise NotImplementedError
