#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.cli.utils import (
    get_argparser,
    set_default_simulation_intents,
    load_simulation_config,
    update_paraphraser_config)

from botsim.platforms.botbuilder.generator_wrapper import Generator

if __name__ == "__main__":
    args = get_argparser().parse_args()
    config = load_simulation_config(args.platform, args.test_name)
    update_paraphraser_config(args, config)
    generator = Generator(config["generator"]["parser_config"],
                          num_t5_paraphrases=config["generator"]["paraphraser_config"]["num_t5_paraphrases"],
                          num_pegasus_paraphrases=config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    if len(config["generator"]["dev_intents"]) == 0:
        set_default_simulation_intents(config, "generator")
    for intent_set in config["generator"]:
        if intent_set.find("intent") == -1: continue
        generator.generate_paraphrases(
            config["generator"][intent_set],
            config["generator"]["file_paths"]["goals_dir"],
            config["generator"]["paraphraser_config"]["num_utterances"])
