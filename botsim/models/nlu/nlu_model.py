#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.models.nlu.nlu_base import IntentDetector


class ModelIntentPredictor(IntentDetector):
    def __init__(self, model_path, *args):
        self.model_path = model_path
        self.intents = None
        self.model = None

    def predict(self, user_message, *args):
        if self.model:
            return self.model(user_message)
