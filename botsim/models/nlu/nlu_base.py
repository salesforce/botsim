#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

class IntentDetector:
    def __init__(self, *args):
        self.intents = None

    def predict(self, bot_message, *args):
        """
        Predict the intent labels given the user message
        :param bot_message: bot message/prompt for the intent query
        """
        raise NotImplementedError
