#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

#######################################
# ABUS Config
#######################################

botsim_actions = ["initial_action", "inform", "request", "confirm", "affirm", "deny", "success"]
# The default and required key for all simulation goals
botsim_default_key = "intent"

# Simulation error codes
FAILURE = "-1"
SUCCESS = 0
INTENT_ERROR = 1
NER_ERROR = 2
OTHER_ERROR = 3

# The intent model path (if used)
BERT_NLI_PATH = "intent/"

