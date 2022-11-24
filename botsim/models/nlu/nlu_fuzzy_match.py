#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import re
from rapidfuzz import process, fuzz

from botsim.botsim_utils.utils import load_intent_examples
from botsim.models.nlu.nlu_base import IntentDetector


class FuzzyMatchIntentPredictor(IntentDetector):
    def __init__(self, dialog_act_map_path=None, *args):
        self.intents = None
        if dialog_act_map_path:
            dialog_act_maps = load_intent_examples(dialog_act_map_path)
            self.intents = []
            for intent in dialog_act_maps:
                self.intents.append({"intent": intent, "dialog_act_and_slot": dialog_act_maps[intent]})

    def predict(self, bot_message, intent_name):
        intents = self.intents
        # remove variable names between $$
        regex = r"\$.*? "
        bot_message = re.sub(regex, "$", bot_message)
        regex = r"\[.*?\]"
        bot_message = re.sub(regex, "", bot_message)

        max_score, max_index, max_intent = -1, 0, 0
        matched_dialog_act_and_slot = ""
        best_match_example = ""
        score_to_candidates = {}

        for intent_index, intent_info in enumerate(intents):
            if intent_name.find(intent_info["intent"]) == -1:
                continue
            dialog_act_and_slots = intent_info["dialog_act_and_slot"]
            res = []
            for dialog_act_and_slot in dialog_act_and_slots:
                res.append({"intent": intent_info["intent"],
                            "dialog_act": dialog_act_and_slot,
                            "candidate_messages": dialog_act_and_slots[dialog_act_and_slot]})
            for dialog_act_and_slot_index, dialog_act_and_slot in enumerate(res):
                examples = dialog_act_and_slot["candidate_messages"]
                match, score, best_match_example_index = process.extractOne(bot_message, examples)
                if score not in score_to_candidates:
                    score_to_candidates[score] = []
                score_to_candidates[score].append((match, dialog_act_and_slot["dialog_act"]))
                if score >= max_score:
                    max_score = score
                    best_match_example = match
                    matched_dialog_act_and_slot = dialog_act_and_slot["dialog_act"]
        return matched_dialog_act_and_slot, best_match_example, max_score, list(score_to_candidates[max_score])
