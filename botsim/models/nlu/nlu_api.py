#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.models.nlu.nlu_base import IntentDetector


class APIIntentPredictor(IntentDetector):
    def __init__(self, api_end_point, *args):
        self.api_end_point = api_end_point
        self.intents = None

    def predict(self, user_message, *args):
        pass
