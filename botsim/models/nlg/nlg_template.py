#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.botsim_utils.utils import read_s3_json
from botsim.models.nlg.nlg_base import NLG

class TemplateNLG(NLG):
    """
    Template-based natural language generation model.
    To generate a natural language response, the model queries the template by matching
    1) dialog act (inform/request)
    2) requested/informed slot
    """

    def __init__(self, nlg_template_path):
        self.nlg_template = read_s3_json("botsim", nlg_template_path)

    def generate(self, dialog_state, role):
        """ Template-based NLG with dialog state (dialog act + slot) as retrieval key
        :param dialog_state: user/agent dialog state
        :param role: user or agent
        """
        sentences = []
        sentences_slots = []
        matched = False
        assert role == "agent" or role == "user"
        act = dialog_state["action"]
        if act in self.nlg_template["dialog_act"].keys():
            for ele in self.nlg_template["dialog_act"][act]:
                # both inform_slots and request_slots must match the template
                if set(ele["inform_slots"]) == set(dialog_state["inform_slots"].keys()) \
                        and set(ele["request_slots"]) == set(dialog_state["request_slots"].keys()):
                    sentences, sentences_slots = \
                        self.dialog_state_to_response_and_slot(dialog_state, ele["response"][role])
                    matched = True
                    break
        assert matched
        return sentences, sentences_slots

    @staticmethod
    def dialog_state_to_response_and_slot(dialog_state, template_sentences):
        """ Replace the slots with its values """
        sentences = template_sentences
        sentences_slots = template_sentences
        for key in ["inform_slots", "request_slots"]:
            for slot in dialog_state[key].keys():
                slot_val = dialog_state[key][slot]

                sentences = [sentence.replace("$" + slot + "$", str(slot_val), 1)
                             for sentence in sentences]
                sentences_slots = [
                    sentence.replace("$" + slot + "$", "@" + slot + ":" + """ + str(slot_val) + """, 1)
                    for sentence in sentences_slots]
        return sentences, sentences_slots
