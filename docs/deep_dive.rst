This deep-dive section presents  major BotSIM components in more details to help better understanding of their capabilties, required inputs and expected outputs.

Configuration
###########################
A customisable configuration file is used to control the behaviours of the BotSIM pipeline. The template configuration is located at ``botsim/conf/config.json``. An example is given below. 

.. code-block:: json

    {
        "id": "4",
        "platform": "Einstein_Bot",
        "generator": {

            "paraphraser_config": {
                "num_t5_paraphrases": 20,
                "num_pegasus_paraphrases": 20,
                "num_utterances": -1,
                "num_simulations": -1
                },

            "dev_intents": [],
            "eval_intents": [],

            "parser_config": {
                "botversion": "1",
                "botversion_xml": "path-to-botversions-metadata",
                "MIUtterances_xml": "path-to-intent-uttrances-metadata",
                "beginning_dialogs": [],
                "excluded_dialogs": [],
                "failure_ending_dialogs": []
                },

            "file_paths": {
                "customer_entities": "data/bots/Einstein_Bot/4/goals_dir/entities.json",
                "response_template": "data/bots/Einstein_Bot/4/conf/template.json",
                "dialog_act_map": "data/bots/Einstein_Bot/4/conf/dialog_act_map.json",
                "ontology": "data/bots/Einstein_Bot/4/conf/ontology.json",
                "revised_dialog_act_map": "data/bots/Einstein_Bot/4/conf/dialog_act_map.revised.json",
                "revised_ontology": "data/bots/Einstein_Bot/4/conf/ontology.revised.json",
                "goals_dir": "data/bots/Einstein_Bot/4/goals_dir"
                }
            },

        "simulator": {

            "run_time": 
                {
                "max_round_num": 15,
                "intent_check_turn_index": 1
                },

            "dev_intents": [],
            "eval_intents": []
        },

        "remediator": {

            "file_paths": {
                "paraphrases": "data/bots/Einstein_Bot/4/goals_dir/<intent>_<para_setting>_<num_utterances>_utts.paraphrases.json",
                "simulated_dialogs": "data/bots/Einstein_Bot/4/remediation/<intent>/simulation_dialogs_<mode>_<para_setting>_<num_utterances>_utts_<num_simulations>_sessions.json",
                "intent_predictions": "data/bots/Einstein_Bot/4/remediation/<intent>/intent_predictions_<mode>_<para_setting>_<num_utterances>_utts_<num_simulations>_sessions.json",
                "simulation_log": "data/bots/Einstein_Bot/4/simulation/<intent>/logs_<mode>_<para_setting>_<num_utterances>_utts_paraphrases_<num_simulations>_sessions.json",
                "simulation_error_info": "data/bots/Einstein_Bot/4/simulation/<intent>/errors_<mode>_<para_setting>_<num_utterances>_utts_paraphrases_<num_simulations>_sessions.json",
                "ner_error_json": "data/bots/Einstein_Bot/4/remediation/<intent>/ner_errors_<mode>_<para_setting>_<num_utterances>_utts_<num_simulations>_sessions.json",
                "intent_remediation": "data/bots/Einstein_Bot/4/remediation/<intent>/intent_remediation_<mode>_<para_setting>_<num_utterances>_utts_<num_simulations>_sessions.json"
            },

            "dev_intents": [],
            "eval_intents": []
        },

        "api": {
            "end_point": "your-salesorce-bot-endpoint-url",
            "org_Id": "your-org-id",
            "deployment_Id": "bot-deployment-id",
            "button_Id": "bot-button-id",
            "location_id": "google-api-location-id",
            "agent_id": "dialogflow-agent-id",
            "project_id": "google-project-id",
            "cx_credential": "botsim/clients/dialogflow_cx/cx.json"
        }
    }

Generator
##################
The generator takes bot designs and intent utterances as input and produces the required configuration files to serve as BotSIM's NLU and NLG models.
The generator also applies paraphrasing models to the input intent utterances and use the paraphrases as intent queries in the simulation goals.
The following code shows how the major functionalities of the generator:

.. code-block:: python

    from botsim.platforms.botbuilder.generator_wrapper import Generator
    platform = "Einstein_Bot"
    test_id = "4"
    config_json = "data/bots/{}/{}/conf/config.json".format(platform, test_id)
    with open(config_json) as f:
        config = json.load(f)
    parser_config = config["generator"]["parser_config"]
    generator = Generator(parser_config,
                        num_t5_paraphrases=config["generator"]["paraphraser_config"]["num_t5_paraphrases"],
                        num_pegasus_paraphrases=config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"])
    generator.parse_metadata()
    goal_dir = "data/bots/{}/{}/goals_dir/".format(platform, test_id)
    conf_dir = "data/bots/{}/{}/conf/".format(platform, test_id)
    
    # dump intent training utterances to goal_dir
    generator.parser.dump_intent_training_utterances(goal_dir)
    # dump customer entity 
    generator.generate_entities(goal_dir + "/entities.json")
    # dump ontology
    generator.generate_ontology(conf_dir + "/ontology.json")
    # dump dialog act maps (NLU)
    generator.generate_dialog_act_maps(conf_dir+"/dialog_act_map.json")
    # dump template-based NLG
    generator.generate_nlg_response_templates(conf_dir+"/template.json")
    # dump conversation graph visualisation data
    generator.generate_conversation_flow(goal_dir + "/visualization.json")

    # generate intent paraphrases, the intent utterances are
    # under goal_dir in dump_intent_training_utterances
    generator.generate_paraphrases(
        config["generator"]["dev_intents"],    
        config["generator"]["file_paths"]["goals_dir"],    
        config["generator"]["paraphraser_config"]["num_utterances"])

    generator.generate_paraphrases(
        config["generator"]["eval_intents"],    
        config["generator"]["file_paths"]["goals_dir"],    
        config["generator"]["paraphraser_config"]["num_utterances"])

    revised_dialog_map = "data/bots/{}/{}/conf/dialog_act_map.revised.json".format(config["platform"], config["id"])
    if not os.path.exists(revised_dialog_map):
        raise ValueError("Revise {} and save it to {}".format(revised_dialog_map.replace(".revised", ""),
                                                                revised_dialog_map))
                                                                
    # generate simulation goals    
    generator.generate_goals(config["generator"]["file_paths"]["goals_dir"],
                            config["generator"]["file_paths"]["ontology"], 
                            config["generator"]["eval_intents"], 
                            dev_ratio=-1.0, 
                            paraphrase=True,                             
                            number_utterances=config["generator"]["paraphraser_config"]["num_utterances"])


Simulator
#########################################################
With the simulation goals and the NLU, NLG models, we can initialise a bot platform simulator client to perform agenda-based dialog user simulation:

.. code-block:: python
    
    mode = "dev" 
    goal_dir = "data/bots/{}/{}/goals_dir/".format(platform, test_id)
    num_t5_paraphrases = config["generator"]["paraphraser_config"]["num_t5_paraphrases"]
    num_pegasus_paraphrases = config["generator"]["paraphraser_config"]["num_pegasus_paraphrases"]
    para_setting = "{}_{}".format(num_t5_paraphrases, num_pegasus_paraphrases)
    intent_name = "End_Chat"
    config["simulation"] = \
            {
                intent_name: {
                    "continue_from": 0,
                    "mode": mode,
                    "para_setting": para_setting,
                    "goal_dir": goal_dir,
                    "bot": config["platform"]
                },
                "num_simulations": config["generator"]["paraphraser_config"]["num_simulations"],
                "num_utterances": config["generator"]["paraphraser_config"]["num_utterances"]
            }

    if config["platform"] == "DialogFlow_CX":
        from botsim.platforms.dialogflow_cx.simulation_client import DialogFlowCXClient  
        client = DialogFlowCXClient(config)
    else:
        from botsim.platforms.botbuilder.simulation_client import LiveAgentClient  
        client = LiveAgentClient(config)
    client.simulate_conversation()

This will start the dialog simulation for each intent/dialog and mode (dev/eval) as specified in the configuration file ``simulator["dev_intents"]`` and ``simulator["eval_intents"]``.
After simulation, the following outputs will be generated  under ``data/bots/Einstein_Bot/4/simulation/<intent>/``:

- **simulation chat logs**: ``logs_<mode>_<para_setting>_<num_utterances>_utts_paraphrases_<num_simulations>_sessions.json``
- **simulation error info**: ``errors_<mode>_<para_setting>_<num_utterances>_utts_paraphrases_<num_simulations>_sessions.json``

These two files will be used as the inputs to the remediator for further analysis.

Remediator
######################################
The Remediator analyzes the simulated conversations (chat logs and error info), visualizes the bot health reports and provides actionable 
remediation suggestions for bot troubleshooting and improvement. The code below shows how the aggregated bot reports are generated. 

.. code-block:: python

    from botsim.modules.remediator.Remediator import Remediator
    from botsim.botsim_utils.utils import dump_json_to_file
    dev_intents = config["remediator"]["dev_intents"]

    report = {
        "bot_name": config["id"], 
        "bot_id": config["id"],
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "intent_reports": {"dev": {}, "eval": {}},
        "dataset_info": {"dev": {}, "eval": {}},
        "overall_performance": {"dev": {}, "eval": {}}
    }

    remediator = Remediator(config, "dev", intent_check_turn_index=1)
    remediator.generate_health_reports(report)
    eval_intents = config["remediator"]["eval_intents"]

    if len(eval_intents) > 0:
        remediator = Remediator(config, "eval", intent_check_turn_index=intent_query_index)
        remediator.generate_health_reports(report)
        
    path = "data/bots/{}/{}/".format(config["platform"], config["id"])

    if not os.path.isdir(path):
        os.makedirs(path)
    aggregated_report_path = path + "aggregated_report.json"
    dump_json_to_file(aggregated_report_path, report)


The information of the aggregated report is used to support the bot health dashboard visualisation:

- ``dataset_info`` contains the data distribution for each intent in terms of number of simulation episodes.
- ``overall_performance`` contains the performance metrics such as NLU performance in terms of intent and NER accuracies, task-completion rates
- ``intent_reports`` contains the bot health report for each dialog intent, including the following information:

    - Simulation chat logs and associated error information for each episode
    - Detailed intent and NER errors and remediation suggestions

We have prepared a `notebook <https://github.com/salesforce/botsim/blob/main/Einstein_BotBuilder_template_bot.ipynb>`_ to demostrate how to run the BotSIM pipeline using the Template Bot from the Salesforce Einstein BotBuilder platform.
