#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.models.nlu.nlu_base import IntentDetector


class APIIntentPredictor(IntentDetector):
    def __init__(self, dialog_act_map, api_end_point, *args):
        super().__init__(dialog_act_map)
        self.api_end_point = api_end_point

    def predict(self, bot_message, dialog_name, *args):
        raise NotImplementedError
