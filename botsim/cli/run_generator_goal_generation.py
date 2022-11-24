#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.platforms.botbuilder.generator_wrapper import Generator
from botsim.cli.utils import (
    get_argparser,
    set_default_simulation_intents,
    load_simulation_config,
    update_paraphraser_config)

if __name__ == "__main__":
    args = get_argparser().parse_args()
    config = load_simulation_config(args.platform, args.test_name)
    para_config = update_paraphraser_config(args, config)
    generator = Generator(config["generator"]["parser_config"],
                          num_t5_paraphrases=config["generator"]["paraphraser_config"]["num_t5_paraphrases"],
                          num_pegasus_paraphrases=config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    if len(config["generator"]["dev_intents"]) == 0:
        set_default_simulation_intents(config)
    generator.generate_goals(config["generator"]["file_paths"]["goals_dir"],
                             config["generator"]["file_paths"]["ontology"],
                             config["generator"]["eval_intents"], -1.0, True,
                             config["generator"]["paraphraser_config"]["num_utterances"])
    generator.generate_goals(config["generator"]["file_paths"]["goals_dir"],
                             config["generator"]["file_paths"]["ontology"],
                             config["generator"]["dev_intents"], 1.0, True,
                             config["generator"]["paraphraser_config"]["num_utterances"])
