#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json, os

from botsim.modules.remediator.Remediator import Remediator
from botsim.botsim_utils.utils import read_s3_json, file_exists, dump_json_to_file, S3_BUCKET_NAME
from botsim.streamlit_app import postgres_path
from botsim.streamlit_app.database import Database

if not os.environ.get("DATABASE_URL"):
    raise ValueError("DATABASE_URL environment variable not set")

if os.environ.get("DATABASE_URL") and os.environ.get("DATABASE_URL").find("postgre") != -1:
    if postgres_path is None:
        raise EnvironmentError("setting postgres_path in streamlit_app.__init__ with your db url")
    database = Database("postgres", sqlite_db_path="", postgres_path=postgres_path)
elif os.environ.get("DATABASE_URL"):
    database = Database("sqlite3", os.environ.get("DATABASE_URL"), postgres_path="")

if os.environ.get("STORAGE"):
    assert os.environ.get("AWS_ACCESS")
    assert os.environ.get("AWS_SECRET")


def analyze_and_remediate(test_instance):
    """
    Remediator module to analyze simulated conversations and generate bot health reports
    :param test_instance: a bot test instance from the database
    :return: status
    """
    test_id = str(test_instance["id"])
    bot_platform = str(test_instance["type"])
    dev_intents = test_instance["dev"].split(",")
    if test_instance["stage"] < "s06_simulation_completed":
        return json.dumps({"status": "error", "requirements": "finish simulation first"})
    if test_instance["stage"] >= "s07_remediation_completed":
        return json.dumps({"status": "ok", "requirements": "remedy is done"})

    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        config = read_s3_json(S3_BUCKET_NAME, "data/bots/{}/{}/conf/config.json".format(bot_platform, test_id))
    else:
        with open("data/bots/{}/{}/conf/config.json".format(bot_platform, test_id)) as f:
            config = json.load(f)

    if len(dev_intents) > 0:
        config["intents"] = dev_intents
        config["remediator"]["dev_intents"] = dev_intents
    if len(test_instance["eval"]) > 0:
        eval_intents = test_instance["eval"].split(",")
        config["remediator"]["eval_intents"] = eval_intents

    config["id"] = test_id
    config["platform"] = test_instance["type"]

    report = Remediator.analyze_and_remediate(config)
    database.update_stage("s07_remediation_completed", test_id)
    path = "data/bots/{}/{}/".format(config["platform"], config["id"])
    if not os.path.isdir(path):
        os.makedirs(path)
    aggregated_report_path = path + "aggregated_report.json"
    dump_json_to_file(aggregated_report_path, report)

    ret = {"report": "bots/{}/{}/aggregated_report.json".format(bot_platform, test_id), "status": "ok"}
    ret["messages"] = "Analyse and remediation finished, see report in " + ret["report"]
    return json.dumps(ret)


def parse_metadata(test_instance):
    """
    Generator parser service to
    1) parse bot metadata into dialog act maps, NLG templates, ontology.
    2) conversational modeling
    :param test_instance: test_instance: a bot test instance from the database

    """
    generator, config = _init_generator(test_instance)
    if not config:
        raise FileNotFoundError("No config.json found. Setup simulation first.")
    generator.parse_metadata()
    print("parsing metadata")
    goal_dir = config["generator"]["file_paths"]["goals_dir"]
    generator.parser.dump_intent_training_utterances(goal_dir)
    generator.generate_entities(goal_dir + "/entities.json")

    generator.generate_ontology(config["generator"]["file_paths"]["ontology"])

    print("generating dialog act templates (questions)")
    generator.generate_dialog_act_maps(config["generator"]["file_paths"]["dialog_act_map"])
    print("generating NLG response")
    generator.generate_nlg_response_templates(config["generator"]["file_paths"]["response_template"])
    generator.generate_conversation_flow(goal_dir + "/visualization.json")

    requirement = "Please revise " + config["generator"]["file_paths"]["dialog_act_map"] + " and " + \
                  config["generator"]["file_paths"]["ontology"] \
                  + " before moving to the next stage"
    print("Refer to the guidelines for revision")
    ret = {"status": "ok", "dialog_act_templates": config["generator"]["file_paths"]["dialog_act_map"],
           "ontology": config["generator"]["file_paths"]["ontology"],
           "user_response_template": config["generator"]["file_paths"]["response_template"],
           "requirements": requirement}
    return json.dumps(ret)


def _init_generator(test_instance):
    """
    Initialise a generator from the user configurations
    :param test_instance: a bot test instance from the database
    :return: a generator object and an updated config including dev and eval intents
    """
    test_id = str(test_instance["id"])
    bot_type = str(test_instance["type"])
    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        config = read_s3_json(S3_BUCKET_NAME, "data/bots/{}/{}/conf/config.json".format(bot_type, test_id))
    else:
        config_json = "data/bots/{}/{}/conf/config.json".format(bot_type, test_id)
        if not os.path.exists(config_json): return None, None
        with open(config_json) as f:
            config = json.load(f)

    parser_config = config["generator"]["parser_config"]
    if config["platform"] == "DialogFlow_CX":
        from botsim.platforms.dialogflow_cx.generator_wrapper import Generator
        parser_config.update(config["api"])
    else:
        from botsim.platforms.botbuilder.generator_wrapper import Generator

    assert "num_t5_paraphrases" in config["generator"]["paraphraser_config"] and \
           "num_pegasus_paraphrases" in config["generator"]["paraphraser_config"]

    config["generator"]["dev_intents"] = test_instance["dev"].split(",")
    config["generator"]["eval_intents"] = test_instance["eval"].split(",")

    generator = Generator(parser_config,
                          num_t5_paraphrases=config["generator"]["paraphraser_config"]["num_t5_paraphrases"],
                          num_pegasus_paraphrases=config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    return generator, config


def apply_paraphrasing(test_instance):
    """
    Apply paraphrasing models
    :param test_instance: a bot test instance from the database
    """
    print("Applying paraphrasing")
    #if test_instance["s04_paraphrases_generated"] == 1:
    if test_instance["stage"] >= "s04_paraphrases_generated":
        return json.dumps({"status": "ok", "requirements": "paraphrase id done"})
    generator, config = _init_generator(test_instance)
    if not config:
        raise FileNotFoundError("No config.json found. Setup simulation first.")
    ret = {"paraphrases": {}}
    if len(test_instance["dev"]) > 0:
        config["generator"]["dev_intents"] = test_instance["dev"].split(",")
    if len(test_instance["eval"]) > 0:
        config["generator"]["eval_intents"] = test_instance["eval"].split(",")

    for intent_set in config["generator"]:
        if intent_set.find("intent") == -1: continue
        ret["paraphrases"][intent_set] = {}
        generator.generate_paraphrases(
            config["generator"][intent_set],
            config["generator"]["file_paths"]["goals_dir"],
            config["generator"]["paraphraser_config"]["num_utterances"])
    database.update_stage("s04_paraphrases_generated", test_instance["id"])

    ret["messages"] = "You are advised (not required) to review the paraphrases and" \
                      " remove the ones deemed not accurate to get more reliable simulation metrics.\n" \
                      "If paraphrases have been changed, call generate_goals to regenerate goals with the revised" \
                      "paraphrases"
    ret["status"] = "ok"
    return json.dumps(ret)


def generate_goals_from_paraphrases(test_instance):
    """
    Generate simulation goals from paraphrases
    :param test_instance: a bot test instance from the database
    """
    print("generate goals from paraphrases")
    generator, config = _init_generator(test_instance)
    if not config:
        raise FileNotFoundError("No config.json found. Setup simulation first.")

    # simulation_stage = test_instance["stage"]
    # if test_instance["s05_goal_created"] == 1:
    if test_instance["stage"] >= "s05_goal_created":
        return json.dumps({"status": "ok", "requirements": "goals done"})
    if test_instance["type"] == "DialogFlow_CX":
        from botsim.platforms.dialogflow_cx.generator_wrapper import Generator
    else:
        from botsim.platforms.botbuilder.generator_wrapper import Generator
    num_t5_paraphrases = config["generator"]["paraphraser_config"]["num_t5_paraphrases"]
    num_pegasus_paraphrases = config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"]
    ret = {"goals": {}}
    para_config = str(num_t5_paraphrases) + "_" + str(num_pegasus_paraphrases)
    if "num_utterances" in config["generator"]["paraphraser_config"]:
        if config["generator"]["paraphraser_config"]["num_utterances"] == -1:
            para_config += "_utt_all"
        else:
            para_config += "_utt_" + str(config["generator"]["paraphraser_config"]["num_utterances"])

    if "eval_intents" in config["generator"] and "dev_intents" in config["generator"]:
        generator.generate_goals(config["generator"]["file_paths"]["goals_dir"],
                                 config["generator"]["file_paths"]["ontology"],
                                 config["generator"]["eval_intents"], -1.0, True,
                                 config["generator"]["paraphraser_config"]["num_utterances"])
        generator.generate_goals(config["generator"]["file_paths"]["goals_dir"],
                                 config["generator"]["file_paths"]["ontology"],
                                 config["generator"]["dev_intents"], 1.0, True,
                                 config["generator"]["paraphraser_config"]["num_utterances"])

    elif "dev_intents" in config["paraphraser_config"]:
        generator.generate_goals(config["generator"]["file_paths"]["goals_dir"],
                                 config["generator"]["file_paths"]["ontology"],
                                 config["generator"]["dev_intents"], 0.6, True,
                                 config["generator"]["paraphraser_config"]["num_utterances"])
    elif "eval_intents" in config["paraphraser_config"]:
        generator.generate_goals(config["generator"]["file_paths"]["goals_dir"],
                                 config["generator"]["file_paths"]["ontology"],
                                 config["generator"]["eval_intents"], -1.0, True,
                                 config["generator"]["paraphraser_config"]["num_utterances"])
    database.update_stage("s05_goal_created", test_instance["id"])
    ret["messages"] = "goals successfully generated"
    ret["status"] = "ok"
    return json.dumps(ret)


def botsim_generation(test_id):
    """
    BotSIM generator service including paraphrasing and goal generation
    :param test_id: session id as in the database
    """
    test_instance = dict(database.get_one_bot_test_instance(test_id))
    database.update_status(test_id, "running")
    config = dict(database.get_one_bot_test_instance(test_id))
    settings = database.db_record_to_setting(config)
    if settings["stage"] == "s03_human_in_the_loop_revision":
        database.update_status(test_id, "paraphrasing")
        result = json.loads(apply_paraphrasing(test_instance))
        if result:
            database.update_stage("s04_paraphrases_generated", test_id)
            generate_goals_from_paraphrases(test_instance)
            database.update_stage("s05_goal_created", test_id)
            database.update_status(test_id, "paraphrasing_finished")
            return json.dumps({"status": "ok"})
        else:
            database.update_status(test_id, "running")
            return json.dumps({"status": "error"})


def botsim_simulation(test_id):
    """
        BotSIM simulation service
        :param test_id: session id as in the database
    """
    test_instance = dict(database.get_one_bot_test_instance(test_id))
    config = dict(database.get_one_bot_test_instance(test_id))
    settings = database.db_record_to_setting(config)
    if settings["stage"] == "s05_goal_created":
        database.update_status(test_id, "simulating")
        result = None
        if test_instance["type"] == "DialogFlow_CX":
            result = simulate_conversations(test_instance)
        elif test_instance["type"] == "Einstein_Bot":
            result = simulate_conversations_multiprocess(test_instance)

        if result:
            database.update_stage("s06_simulation_completed", test_id)
        else:
            database.update_status(test_id, "running")
    botsim_remediation(test_id)
    # result = json.loads(analyze_and_remediate(test_instance))
    # if result and result["status"] == "ok":
    #     database.update_stage("s07_remediation_completed", test_id)
    #     database.update_status(test_id, "finished")
    #     return json.dumps({"status": "ok"})
    # else:
    #     return json.dumps({"status": "error"})

def botsim_remediation(test_id):
    """
    BotSIM's remediation service
    :param test_id: session id as in the database
    """
    test_instance = dict(database.get_one_bot_test_instance(test_id))
    database.update_status(test_id, "running")
    config = dict(database.get_one_bot_test_instance(test_id))
    settings = database.db_record_to_setting(config)
    # if settings["stage"] == "s03_human_in_the_loop_revision":
    #     database.update_status(test_id, "paraphrasing")
    #     result = json.loads(apply_paraphrasing(test_instance))
    #     if result:
    #         database.update_stage("s04_paraphrases_generated", test_id)
    #         generate_goals_from_paraphrases(test_instance)
    #         database.update_stage("s05_goal_created", test_id)
    #     else:
    #         database.update_status(test_id, "running")
    #         return json.dumps({"status": "error"})
    # if settings["stage"] == "s05_goal_created":
    #     database.update_status(test_id, "simulating")
    #     result = None
    #     if test_instance["type"] == "DialogFlow_CX":
    #         result = simulate_conversations(test_instance)
    #     elif test_instance["type"] == "Einstein_Bot":
    #         result = simulate_conversations_multiprocess(test_instance)
    #     if result:
    #         database.update_stage("s06_simulation_completed", test_id)
    #     else:
    #         database.update_status(test_id, "running")
    assert settings["stage"] >= "s06_simulation_completed"
    result = json.loads(analyze_and_remediate(test_instance))
    if result and result["status"] == "ok":
        database.update_stage("s07_remediation_completed", test_id)
        database.update_status(test_id, "finished")
        return json.dumps({"status": "ok"})
    else:
        return json.dumps({"status": "error"})

def simulate_single_intent(job):
    """
    simulation sub-process for multi-process Einstein Bot simulation
    :param job: a dictionary of simulation configurations including 1) test_instance 2) intent name 3) simulation mode
    """
    test_instance = job["test_instance"]
    intent_name = job["intent_name"]
    mode = job["mode"]
    test_id = str(test_instance["id"])
    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        meta_config = read_s3_json(S3_BUCKET_NAME, "data/bots/Einstein_Bot/{}/conf/config.json".format(test_id))
    else:
        with open("data/bots/Einstein_Bot/" + test_id + "/conf/config.json") as f:
            meta_config = json.load(f)

    para_setting = str(meta_config["generator"]["paraphraser_config"]["num_t5_paraphrases"]) + \
                   "_" + str(meta_config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    goal_dir = meta_config["generator"]["file_paths"]["goals_dir"]
    # for cases when only simulating the eval dialogs
    if mode == "eval" and intent_name.find("_eval") == -1:
        intent_name = intent_name + "_eval"

    if meta_config["generator"]["paraphraser_config"]["num_utterances"] == -1:
        meta_config["generator"]["paraphraser_config"]["num_utterances"] = "all"

    meta_config["simulation"] = \
        {
            intent_name: {
                "continue_from": 0,
                "mode": mode,
                "para_setting": para_setting,
                "goal_dir": goal_dir,
                "version": test_instance["version"],
                "bot": test_instance["name"]
            },
            "num_simulations": meta_config["generator"]["paraphraser_config"]["num_simulations"],
            "num_utterances": meta_config["generator"]["paraphraser_config"]["num_utterances"]
        }
    # goal = meta_config["simulation"][intent_name]["goal_dir"] + \
    #        "/" + intent_name + "_" + para_setting + "_utt_" + \
    #        str(meta_config["generator"]["paraphraser_config"]["num_utterances"]) + "." + mode+".paraphrases.goal.json"
    # print(goal)
    # assert file_exists(S3_BUCKET_NAME, goal)
    assert test_instance["type"] == "Einstein_Bot"
    from botsim.platforms.botbuilder.simulation_client import LiveAgentClient  # simulate_conversation
    client = LiveAgentClient(meta_config)
    client.simulate_conversation(database)


def simulate_conversations_multiprocess(test_instance):
    """
    Multi-process simulation for Einstein bots. Each sub-process is responsible in simulating only one intent
    :param test_instance: a bot test instance from the database
    """
    print("multiprocess simulation of Einstein Bot")
    if test_instance["stage"] >= "s06_simulation_completed":
        return {"status": "ok", "requirements": "simulate is done"}

    dev_intents, eval_intents = [], []
    if len(test_instance["dev"]) > 0:
        dev_intents = test_instance["dev"].split(",")
    dev_jobs = []
    for intent in dev_intents:
        dev_jobs.append({"test_instance": test_instance, "intent_name": intent, "mode": "dev"})

    # need a new entry for eval intent sets selected by the user
    if len(test_instance["eval"]) > 0:
        eval_intents = test_instance["eval"].split(",")
    eval_jobs = []
    for intent in eval_intents:
        eval_jobs.append({"test_instance": test_instance, "intent_name": intent.replace("_eval", ""), "mode": "eval"})

    modes = []
    if len(dev_intents) > 0:
        modes.append("dev")
    if len(eval_intents) > 0:
        modes.append("eval")

    intents = set(dev_intents + eval_intents)

    processed = {}
    from multiprocessing import Pool
    num_process = 4
    if len(dev_jobs) > 0:
        try:
            pool = Pool(num_process)
            pool.map(simulate_single_intent, dev_jobs)
        finally:
            pool.close()
            pool.join()
            for intent_name in intents:
                processed[intent_name] = "success"
    if len(eval_jobs) > 0:
        try:
            pool = Pool(num_process)
            pool.map(simulate_single_intent, eval_jobs)
        finally:
            pool.close()
            pool.join()
            for intent_name in eval_intents:
                processed[intent_name] = "success"

    database.update_stage("s06_simulation_completed", id)
    return json.dumps(processed)


def simulate_conversations(test_instance):
    """
    Normal (single-process) simulation
    :param test_instance: a bot test instance from the database
    """
    test_id = str(test_instance["id"])
    bot_type = test_instance["type"]
    dev_intents, eval_intents = [], []
    if len(test_instance["dev"]) > 0:
        dev_intents = test_instance["dev"].split(",")
    if len(test_instance["eval"]) > 0:
        eval_intents = test_instance["eval"].split(",")

    if test_instance["stage"] >= "s06_simulation_completed":
    #if test_instance["s06_simulation_completed"] == 1:
        return {"status": "ok", "requirements": "simulate is done"}

    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        meta_config = read_s3_json(S3_BUCKET_NAME, "data/bots/{}/{}/conf/config.json".format(bot_type, test_id))
    else:
        with open("data/bots/{}/{}/conf/config.json".format(bot_type, test_id)) as f:
            meta_config = json.load(f)

    para_setting = str(meta_config["generator"]["paraphraser_config"]["num_t5_paraphrases"]) + \
                   "_" + str(meta_config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    goal_dir = meta_config["generator"]["file_paths"]["goals_dir"]

    if meta_config["generator"]["paraphraser_config"]["num_utterances"] == -1:
        meta_config["generator"]["paraphraser_config"]["num_utterances"] = "all"
    processed = {}
    modes = []
    if len(dev_intents) > 0:
        modes.append("dev")
    if len(eval_intents) > 0:
        modes.append("eval")
    intents = set(dev_intents+eval_intents)
    for intent_name in intents:
        meta_config["id"] = test_instance["id"]
        for mode in modes:
            meta_config["simulation"] = \
                {
                    intent_name: {
                        "continue_from": 0,
                        "mode": mode,
                        "para_setting": para_setting,
                        "goal_dir": goal_dir,
                        "version": test_instance["version"],
                        "bot": test_instance["name"]
                    },
                    "num_simulations": meta_config["generator"]["paraphraser_config"]["num_simulations"],
                    "num_utterances": meta_config["generator"]["paraphraser_config"]["num_utterances"]
                }
            goal = meta_config["simulation"][intent_name]["goal_dir"] + \
                   "/" + intent_name + "_" + para_setting + "_" + \
                   str(meta_config["generator"]["paraphraser_config"][
                           "num_utterances"]) + "_utts." + mode+".paraphrases.goal.json"
            if not file_exists(S3_BUCKET_NAME, goal):
                continue
            if test_instance["type"] == "DialogFlow_CX":
                from botsim.platforms.dialogflow_cx.simulation_client import DialogFlowCXClient  # simulate_conversation
                client = DialogFlowCXClient(meta_config)
            else:
                from botsim.platforms.botbuilder.simulation_client import LiveAgentClient  # simulate_conversation
                client = LiveAgentClient(meta_config)
            client.simulate_conversation(database)
            processed[intent_name] = "success"

    database.update_stage("s06_simulation_completed", test_id)
    return json.dumps(processed)
