#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.models.nlg.nlg_base import NLG
class ModelNLG(NLG):
    def __init__(self, model, *args):
        self.model = model

    def generate(self, dialog_state, *args):
        """ generate a natural language message given a semantic-level dialog state
        """
        raise NotImplementedError
