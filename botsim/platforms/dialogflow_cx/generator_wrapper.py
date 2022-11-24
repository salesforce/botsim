#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random, json, os, copy

from botsim.botsim_utils.utils import (
    read_s3_json,
    file_exists,
    dump_s3_file,
    seed_everything,
    S3_BUCKET_NAME,
    dump_json_to_file )
from botsim.modules.generator.generator_base import GeneratorBase
from botsim.platforms.dialogflow_cx.parser import DialogFlowCXParser

seed_everything(42)


def _generate_compound_goals(intent, ontology, intent_queries, compound_goal, all_intents):
    goals = {"Goal": {}}
    for index, cand in enumerate(intent_queries[intent]):
        if intent.find("_eval") != -1:
            intent = intent.replace("_eval", "")
        if intent.find("_augmented") != -1:
            intent = intent.replace("_augmented", "")
        goal_name = intent + "_" + str(index)
        second_intent = intent
        if compound_goal:
            assert all_intents is not None
            while second_intent == intent:
                second_intent = random.choice(list(all_intents)).replace("_eval", "")

        if second_intent != intent:
            goal_name = intent + "_" + str(index) + "_" + second_intent

        goals["Goal"][goal_name] = {}
        goals["Goal"][goal_name]["inform_slots"] = {}
        goals["Goal"][goal_name]["request_slots"] = {}

        goals["Goal"][goal_name]["name"] = intent
        goals["Goal"][goal_name]["request_slots"][intent] = "UNK"

        variables = copy.deepcopy(ontology[intent])
        if second_intent != intent:
            second_ontology = copy.deepcopy(ontology[second_intent])
            second_ontology.pop("intent", None)
            variables.update(second_ontology)
            goals["Goal"][goal_name]["request_slots"][second_intent] = "UNK"
            if second_intent not in intent_queries:
                second_intent = second_intent + "_eval"
            second_intent_utt = random.choice(list(intent_queries[second_intent]))
            goals["Goal"][goal_name]["inform_slots"]["subsequent_intent"] = second_intent_utt
            goals["Goal"][goal_name]["name"] = goals["Goal"][goal_name]["name"] + "+" + second_intent
        for variable in variables:
            if variable.find("Anything_Else") != -1:
                goals["Goal"][goal_name]["inform_slots"][variable] = "no"
            elif len(variables[variable]) > 0:
                goals["Goal"][goal_name]["inform_slots"][variable] = \
                    random.choice(variables[variable])
        goals["Goal"][goal_name]["inform_slots"]["intent"] = cand

    return goals


class Generator(GeneratorBase):
    """ Generator implementation for DialogFlow CX
    """

    def __init__(self, parser_config, num_t5_paraphrases=0,
                 num_pegasus_paraphrases=0,
                 num_goals_per_intent=500):

        super(Generator, self).__init__(parser_config, num_t5_paraphrases, num_pegasus_paraphrases, num_goals_per_intent)
        self.parser = DialogFlowCXParser(parser_config)
        self.parser_config = parser_config

    def generate_goals(self,
                       intent_utterance_dir,
                       ontology_file,
                       intents,
                       dev_ratio=0.7,
                       paraphrase=True,
                       number_utterances=-1,
                       compound_goal=False,
                       all_intents=None):
        """
        generate simulation goal from either paraphrases or customer provided intent
        evaluation utterances (user)
        :param intent_utterance_dir: directory containing the intent queries (paraphrases or user-provided)
        :param ontology_file: automatic generated or user provided ontology file in json format
        :param intents: intents to generate goals for
        :param dev_ratio: ratio of the intent queries to be used for probing the intent model. The wrongly classified
        queries can be filtered and used to augment the original intent training utterances for model retraining.
        The rest will be used for evaluation.
        :param paraphrase: whether to use paraphrases to create goals. If False, use the original
               intent utterances for goals
        :param number_utterances: number of utterances to use for creating goals. -1 means to use all utterances
        """

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            ontology = read_s3_json(S3_BUCKET_NAME, ontology_file)
        else:
            with open(ontology_file, "r") as fin:
                ontology = json.load(fin)

        if compound_goal:
            all_intents = intents

        # if paraphrase:
        para_config = "_".join([str(x) for x in self.num_paraphrases_per_model])

        if number_utterances > 0:
            para_config = para_config + "_" + str(number_utterances)+"_utts"
        else:
            para_config = para_config + "_all_utts"

        candidates = {"eval": {}, "dev": {}}
        paraphrases_split = {"eval": {}, "dev": {}}
        for intent in intents:
            intent = intent.replace(" ", "_")
            print("processing", intent, "goals")
            if paraphrase:
                paraphrase_file = intent_utterance_dir + "/" + intent + "_" + para_config + ".paraphrases.json"
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    if not file_exists(S3_BUCKET_NAME, paraphrase_file):
                        continue
                    paraphrases = read_s3_json(S3_BUCKET_NAME, paraphrase_file)
                else:
                    if not os.path.exists(paraphrase_file):
                        continue
                    with open(intent_utterance_dir + "/" + intent + "_" + para_config
                              + ".paraphrases.json", "r") as fin:
                        paraphrases = json.load(fin)

                candidates["dev"][intent] = set()
                candidates["eval"][intent] = set()
                for _, para in enumerate(paraphrases):
                    if random.uniform(0, 1) <= dev_ratio:
                        candidates["dev"][intent].update(para["cands"])
                        paraphrases_split["dev"][para["source"]] = list(para["cands"])
                    else:
                        candidates["eval"][intent].update(para["cands"])
                        paraphrases_split["eval"][para["source"]] = list(para["cands"])

                paraphrase_eval_file = intent_utterance_dir + "/" + intent + "_eval_" + para_config + ".paraphrases.json"

                eval_paraphrases = {}
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    if file_exists(S3_BUCKET_NAME, paraphrase_eval_file):
                        eval_paraphrases = read_s3_json(S3_BUCKET_NAME, paraphrase_eval_file)
                else:
                    if os.path.exists(paraphrase_eval_file):
                        with open(paraphrase_eval_file, "r") as fin:
                            eval_paraphrases = json.load(fin)

                for _, para in enumerate(eval_paraphrases):
                    candidates["eval"][intent].update(para["cands"])
                    paraphrases_split["eval"][para["source"]] = list(para["cands"])

                if dev_ratio > 0 and dev_ratio < 1:
                    for split in paraphrases_split:
                        paraphrase_json_data = []
                        for source in paraphrases_split[split]:
                            paraphrase_json_data.append({"source": source, "cands": paraphrases_split[split][source]})
                        paraphrase_json_file = "{}/{}_{}.{}.paraphrases.json".format(
                            intent_utterance_dir, intent, para_config, split)
                        dump_json_to_file(paraphrase_json_file, paraphrase_json_data)

            else:
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    utterances = read_s3_json(S3_BUCKET_NAME, intent_utterance_dir + "/" + intent + ".user.json")
                else:
                    with open(intent_utterance_dir + "/" + intent + ".user.json", "r") as fin:
                        utterances = json.load(fin)

                candidates["dev"][intent] = set(utterances[intent])

        if compound_goal:
            para_config += "_compound"
        for intent in intents:
            if paraphrase:
                if dev_ratio >= 0:
                    goal_file = intent_utterance_dir + "/" + intent + "_" + para_config + ".dev.paraphrases.goal.json"
                    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                        dump_s3_file(goal_file, bytes(json.dumps(
                            _generate_compound_goals(intent, ontology, candidates["dev"],
                                                     compound_goal, all_intents), indent=2).encode("UTF-8")))
                    else:
                        with open(goal_file, "w") as json_file:
                            json.dump(_generate_compound_goals(intent, ontology, candidates["dev"],
                                                               compound_goal, all_intents), json_file, indent=2)

                if dev_ratio <= 1:
                    goal_file = intent_utterance_dir + "/" + intent + "_" + para_config + ".eval.paraphrases.goal.json"

                    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                        dump_s3_file(goal_file, bytes(json.dumps(
                            _generate_compound_goals(intent, ontology, candidates["eval"],
                                                     compound_goal, all_intents), indent=2).encode("UTF-8")))
                    else:
                        with open(goal_file, "w") as json_file:
                            json.dump(_generate_compound_goals(intent, ontology, candidates["eval"],
                                                               compound_goal, all_intents),
                                      json_file, indent=2)

            else:
                file_name = intent_utterance_dir + "/" + intent + ".user.goal.json"
                if compound_goal:
                    file_name = intent_utterance_dir + "/" + intent + ".compound.user.goal.json"
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    dump_s3_file(file_name, bytes(json.dumps(
                        _generate_compound_goals(intent, ontology, candidates["dev"], compound_goal),
                        indent=2).encode("UTF-8")))
                else:
                    with open(file_name, "w") as json_file:
                        json.dump(_generate_compound_goals(intent, ontology, candidates["dev"], compound_goal),
                                  json_file, indent=2)
