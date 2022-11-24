#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import argparse
from botsim.cli.utils import load_simulation_config, get_argparser

if __name__ == "__main__":
    args = get_argparser().parse_args()
    config = load_simulation_config(args.platform, args.test_name)

    parser_config = config["generator"]["parser_config"]

    if args.platform:
        config["platform"] = args.platform

    if config["platform"] == "DialogFlow_CX":
        from botsim.platforms.dialogflow_cx.generator_wrapper import Generator
        parser_config.update(config["api"])
    else:
        from botsim.platforms.botbuilder.generator_wrapper import Generator
    generator = Generator(parser_config,
                          num_t5_paraphrases=config["generator"]["paraphraser_config"]["num_t5_paraphrases"],
                          num_pegasus_paraphrases=config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    generator.parse_metadata()
    print("parsing metadata")
    goal_dir = "data/bots/{}/{}/goals_dir/".format(args.platform, args.test_name)
    conf_dir = "data/bots/{}/{}/conf/".format(args.platform, args.test_name)
    generator.parser.dump_intent_training_utterances(goal_dir)
    generator.generate_entities(goal_dir + "/entities.json")
    generator.generate_ontology(conf_dir + "/ontology.json")
    print("generating dialog act templates (questions)")
    generator.generate_dialog_act_maps(conf_dir+"/dialog_act_map.json")
    print("generating NLG response")
    generator.generate_nlg_response_templates(conf_dir+"/template.json")
    generator.generate_conversation_flow(goal_dir + "/visualization.json")
