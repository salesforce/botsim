#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, json
from botsim.cli.utils import get_argparser

if __name__ == "__main__":

    parser = get_argparser()
    args = parser.parse_args()

    config_template_path = "botsim/conf/config.json"
    with open(config_template_path, "r") as config_template:
        config = json.load(config_template)
    api_credential_name = os.path.basename(args.api_credential)
    api_path = "config/" + api_credential_name
    if os.path.exists(api_path):
        with open("config/" + api_credential_name, "r") as api_credential:
            api_tokens = json.load(api_credential)
    else:
        raise FileNotFoundError("not API credential json found under config/{}".format(api_credential_name))

    config["platform"] = args.platform
    config["api"].update(api_tokens)
    config["id"] = args.test_name
    for directory in ["conf", "bots", "cm_data", "goals_dir"]:
        os.makedirs("data/bots/{}/{}/{}".format(args.platform, args.test_name, directory), exist_ok=True)
    paraphraser_config = {"num_t5_paraphrases": args.num_t5_paraphrases,
                          "num_pegasus_paraphrases": args.num_pegasus_paraphrases,
                          "num_utterances": args.num_seed_utterances,
                          "num_simulations": args.max_num_simulations
                          }
    config["generator"]["paraphraser_config"] = paraphraser_config
    for module in ["generator", "remediator"]:
        for file in config[module]["file_paths"]:
            config[module]["file_paths"][file] = \
                config[module]["file_paths"][file].replace("<id>", config["id"]).replace("<platform>",
                                                                                         config["platform"])

    output_config = "data/bots/{}/{}/conf/config.json".format(args.platform, args.test_name)
    config["simulator"]["run_time"]["intent_check_turn_index"] = args.max_num_dialog_turns
    if args.platform == "DialogFlow_CX":
        config["simulator"]["run_time"]["intent_check_turn_index"] = 2

    elif args.platform == "Einstein_Bot":
        config["generator"]["parser_config"]["botversion"] = args.bot_version
        config["generator"]["parser_config"]["botversion_xml"] = args.metadata_botversions
        config["generator"]["parser_config"]["MIUtterances_xml"] = args.metadata_intent_utterances
        config["simulator"]["run_time"]["intent_check_turn_index"] = 3
    else:
        raise ValueError("{} not supported yet.".format(args.platform))
    with open(output_config, "w") as config_json:
        json.dump(config, config_json, indent=2)
