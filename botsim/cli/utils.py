#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause
import argparse, os, json, warnings

def get_argparser():
    parser = argparse.ArgumentParser(description="Generate a configuration file for BotSIM")
    parser.add_argument("--platform", help="bot platform [DialogFlow_CX, Einstein_Bot]", type=str,
                        default="Einstein_Bot", required=True)
    parser.add_argument("--test_name", help="name of the test", type=str, required=True)
    parser.add_argument("--metadata_botversions", help="bot design metadata from Salesforce workbench",
                        type=str )
                        #type=str, required=True)
    parser.add_argument("--metadata_intent_utterances", help="intent utterance metadata from Salesforce workbench",
                        type=str)
                        #type=str, required=True)
    parser.add_argument("--bot_version", help="bot version", type=str, default="1")
    parser.add_argument("--num_t5_paraphrases", help="number of t5 paraphrases per "
                                                     "intent utterance", type=int, default=16)
    parser.add_argument("--num_pegasus_paraphrases", help="number of pegasus paraphrases per "
                                                          "intent utterance", type=int, default=16)
    parser.add_argument("--num_seed_utterances", help="number of intent utterances to be  paraphrased", type=int,
                        default=-1)
    parser.add_argument("--max_num_simulations", help="number of simulation episodes per intent", type=int, default=-1)
    parser.add_argument("--max_num_dialog_turns", help="number of dialog turns per episode", type=int, default=15)
    #parser.add_argument("--api_credential", help="bot API credential path", type=str, required=True)
    parser.add_argument("--api_credential", help="bot API credential path", type=str)
    return parser

def set_default_simulation_intents(config, module="generator"):
    revised_dialog_map = "data/bots/{}/{}/conf/dialog_act_map.revised.json".format(config["platform"], config["id"])
    if not os.path.exists(revised_dialog_map):
        raise ValueError("Revise {} and save it to {}".format(revised_dialog_map.replace(".revised", ""),
                                                              revised_dialog_map))
    with open(revised_dialog_map, "r") as nlu:
        dialog_act_map = json.load(nlu)
        intents = list(dialog_act_map["DIALOGS"].keys())
        config[module]["dev_intents"] = intents
        config["intents"] = intents
        config[module]["eval_intents"] = \
            config[module]["eval_intents"] = [intent + "_eval" for intent in intents]
        config["remediator"]["eval_intents"] = config[module]["eval_intents"]
        warnings.warn("Empty dev_intents. Default applied to include all intents/dialogs.")

def load_simulation_config(platform, test_name):
    config_json = "data/bots/{}/{}/conf/config.json".format(platform, test_name)
    if not os.path.exists(config_json):
        raise FileNotFoundError("config file {} not exists".format(config_json))
    with open(config_json) as f:
        config = json.load(f)
    return config

def update_paraphraser_config(args, config):
    if args.num_t5_paraphrases:
        config["generator"]["paraphraser_config"]["num_t5_paraphrases"] = args.num_t5_paraphrases
    if args.num_pegasus_paraphrases:
        config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"] = args.num_pegasus_paraphrases
    if args.num_seed_utterances:
        config["generator"]["paraphraser_config"]["num_utterances"] = args.num_seed_utterances
    if args.max_num_simulations:
        config["generator"]["paraphraser_config"]["num_simulations"] = args.max_num_simulations

    para_config = "{}_{}".format(config["generator"]["paraphraser_config"]["num_t5_paraphrases"],
                                 config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    if "num_utterances" in config["generator"]["paraphraser_config"]:
        if config["generator"]["paraphraser_config"]["num_utterances"] == -1:
            para_config += "_all_utts"
        else:
            para_config += "_" + str(config["generator"]["paraphraser_config"]["num_utterances"])+"_utts"
    return para_config
