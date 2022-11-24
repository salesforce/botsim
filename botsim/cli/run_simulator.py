#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os

from botsim.cli.utils import load_simulation_config, set_default_simulation_intents, get_argparser


def simulate_single_intent(job_config):
    intent_name = job_config["intent_name"]
    mode = job_config["mode"]
    simulation_config = job_config["config"]
    para_setting = "{}_{}".format(simulation_config["generator"]["paraphraser_config"]["num_t5_paraphrases"],
                                  simulation_config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    goal_dir = simulation_config["generator"]["file_paths"]["goals_dir"]
    if simulation_config["generator"]["paraphraser_config"]["num_utterances"] == -1:
        simulation_config["generator"]["paraphraser_config"]["num_utterances"] = "all"
    if mode == "eval" and intent_name.find("_eval") == -1:
        intent_name = intent_name + "_eval"

    simulation_config["simulation"] = \
        {
            intent_name: {
                "continue_from": 0,
                "mode": mode,
                "para_setting": para_setting,
                "goal_dir": goal_dir,
                "bot": simulation_config["platform"]
            },
            "num_simulations": simulation_config["generator"]["paraphraser_config"]["num_simulations"],
            "num_utterances": simulation_config["generator"]["paraphraser_config"]["num_utterances"]
        }

    if simulation_config["platform"] == "DialogFlow_CX":
        from botsim.platforms.dialogflow_cx.simulation_client import DialogFlowCXClient  # simulate_conversation
        client = DialogFlowCXClient(simulation_config)
    else:
        from botsim.platforms.botbuilder.simulation_client import LiveAgentClient  # simulate_conversation
        client = LiveAgentClient(simulation_config)
    client.simulate_conversation()


def simulate_conversations_multithread(simulation_config):
    print("multiprocess simulation of Einstein Bot")
    dev_intents = simulation_config["simulator"]["dev_intents"]
    dev_jobs = []
    for intent in dev_intents:
        dev_jobs.append({"config": simulation_config, "intent_name": intent, "mode": "dev"})

    eval_intents = simulation_config["simulator"]["eval_intents"]
    eval_jobs = []
    for intent in eval_intents:
        eval_jobs.append({"config": simulation_config, "intent_name": intent, "mode": "eval"})
    processed = {}
    from multiprocessing import Pool
    num_process = 4
    try:
        pool = Pool(num_process)
        pool.map(simulate_single_intent, dev_jobs)
    finally:
        pool.close()
        pool.join()
        for intent_name in dev_intents:
            processed[intent_name] = "success"

    try:
        pool = Pool(num_process)
        pool.map(simulate_single_intent, eval_jobs)
    finally:
        pool.close()
        pool.join()
        for intent_name in eval_intents:
            processed[intent_name] = "success"


def simulate_conversations(simulation_config):
    if simulation_config["generator"]["paraphraser_config"]["num_utterances"] == -1:
        simulation_config["generator"]["paraphraser_config"]["num_utterances"] = "all"
    modes = ["dev"]
    if len(simulation_config["simulator"]["eval_intents"]) > 0:
        modes.append("eval")
    intents = simulation_config["simulator"]["dev_intents"]
    for intent_name in intents:
        for mode in modes:
            job_config = {"config": simulation_config, "intent_name": intent_name, "mode": mode}
            simulate_single_intent(job_config)


if __name__ == "__main__":

    args = get_argparser().parse_args()
    config = load_simulation_config(args.platform, args.test_name)
    config["platform"] = args.platform
    revised_dialog_map = "data/bots/{}/{}/conf/dialog_act_map.revised.json".format(config["platform"], config["id"])
    if not os.path.exists(revised_dialog_map):
        raise ValueError("Revise {} and save it to {}".format(revised_dialog_map.replace(".revised", ""),
                                                              revised_dialog_map))
    if len(config["simulator"]["dev_intents"]) == 0 and len(config["simulator"]["eval_intents"]) == 0:
        set_default_simulation_intents(config, "simulator")
    if config["platform"] == "DialogFlow_CX":
        simulate_conversations(config)
    else:
        simulate_conversations_multithread(config)
