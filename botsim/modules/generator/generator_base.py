#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, json, random
from botsim.botsim_utils.utils import (
    dump_s3_file,
    file_exists,
    read_s3_json,
    seed_everything,
    create_goals,
    load_goals,
    dump_json_to_file)
from botsim.modules.generator.parser import Parser
from botsim.modules.generator.paraphraser.paraphrase import Paraphraser

seed_everything(42)


class GeneratorBase:
    """ A generator class interface.
    """
    def __init__(self,
                 parser_config = {},
                 num_t5_paraphrases=0,
                 num_pegasus_paraphrases=0,
                 num_goals_per_intent=500):
        self.conversation_graph = None
        self.parser = Parser(parser_config)
        self.parser_config = parser_config
        num_return_sequences = [num_t5_paraphrases, num_pegasus_paraphrases]

        self.num_paraphrases_per_model = num_return_sequences
        if num_t5_paraphrases > 0 or num_pegasus_paraphrases > 0:
            self.paraphraser = Paraphraser(batch_size=16, max_length=128,
                                           num_return_sequences=num_return_sequences,
                                           beam_size=30)

        self.num_simulation_goals = num_goals_per_intent
        self.variable_to_entity = {}
        self.dialog_ontology = {}

    def _load_intent_to_training_utts(self, intents, intent_utterance_dir=None):
        """ load intent utterances (<intent-name>.json) under intent_utterance_dir
        :param intent_utterance_dir: the dir containing the  intent utterance json files
        :param intents: list of intent names
        :return intent_to_training_utterances: mapping from intents to training utterances
        """
        if not os.path.isdir(intent_utterance_dir):
            intent_utterance_dir = os.path.dirname(intent_utterance_dir)
        intent_to_training_utterances = {}
        for intent in intents:
            # convert the intent api names to labels
            if intent in self.parser.api_name_to_intent_label:
                intent = self.parser.api_name_to_intent_label[intent]
            intent = intent.replace(" ", "_")
            if intent_utterance_dir:
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    if not file_exists("botsim", intent_utterance_dir + "/" + intent + ".json"):
                        continue
                    sentences = read_s3_json("botsim", intent_utterance_dir + "/" + intent + ".json")
                else:
                    if not os.path.exists(intent_utterance_dir + "/" + intent + ".json"):
                        continue
                    with open(intent_utterance_dir + "/" + intent + ".json", "r") as fin:
                        sentences = json.load(fin)
            intent_to_training_utterances.update(sentences)
        return intent_to_training_utterances

    def parse_metadata(self):
        self.parser.parse()

    def generate_paraphrases(self,
                             intents,
                             intent_utterance_dir=None,
                             number_utterances=-1):
        """ Apply paraphrasing models on all intent utterances (<intent-name>.json) under intent_utterance_dir and
        dump the generated paraphrases to json.
        :param intents: intent names to be applied
        :param intent_utterance_dir: the dir containing the  intent utterance json files
        :param number_utterances: number of original intent utterances to be selected for paraphrasing
        :return:
        """
        destination = intent_utterance_dir
        if not os.path.isdir(intent_utterance_dir):
            destination = os.path.dirname(intent_utterance_dir)
        intent_to_training_utts = self._load_intent_to_training_utts(intents, destination)

        for intent in intent_to_training_utts:
            post_processed_paraphrases = self.paraphraser.post_process_paraphrases(
                self.paraphraser.paraphrase(intent_to_training_utts, intent, number_utterances))
            para_config = "_".join([str(x) for x in self.num_paraphrases_per_model])
            if isinstance(number_utterances, int) and number_utterances > 0:
                para_config = para_config + "_" + str(number_utterances)+"_utts"
                paraphrase_json = destination + "/" + intent + "_" + para_config + ".paraphrases.json"
            else:
                para_config = para_config + "_all_utts"
                paraphrase_json = destination + "/" + intent + "_" + para_config + ".paraphrases.json"
            dump_json_to_file(paraphrase_json, post_processed_paraphrases)

    def generate_entities(self, output_entity_json):
        """ Dump customer entities to local json file
        :param output_entity_json: output name
        """
        if os.environ.get("STORAGE") == "S3":
            dump_s3_file(output_entity_json,
                         bytes(json.dumps(self.parser.customer_entities, indent=2).encode("UTF-8")))
        else:
            with open(output_entity_json, "w") as json_file:
                json.dump(self.parser.customer_entities, json_file, indent=2)

    def generate_ontology(self, output_ontology):
        """
        Generate the ontology file containing a list of entities used in each intent
        The values for each entity are randomly generated.
        BotSIM users are REQUIRED to revise the generated file to include real entity values
        if they want to test the entity extraction capability as well
        :return:
        """

        self.dialog_ontology = self.parser.extract_ontology()
        if os.environ.get("STORAGE") == "S3":
            dump_s3_file(os.path.dirname(output_ontology) + "/ontology.json",
                         bytes(json.dumps(self.dialog_ontology, indent=2).encode("UTF-8")))
        else:
            with open(os.path.dirname(output_ontology) + "/ontology.json", "w") as json_file:
                json.dump(self.dialog_ontology, json_file, indent=2)

    def generate_dialog_act_maps(self, output_dialog_act_maps_json):
        """ Generate dialog act maps for mapping bot messages  to dialog acts, e.g.,
        "Can I have your email" ==> request_Email
        BotSIM users are REQUIRED  to revise this file to make sure the following
        messages are accurate, especially for the following two messages:
            1) intent_success_message
            2) dialog_success_message
        :param output_dialog_act_maps_json: output json file for dialog act maps for fuzzy matching
         (from natural language response to dialog act)
        """

        dialog_act_maps = {"DIALOGS": self.parser.dialog_act_maps}
        dialogs_with_labels = {"DIALOGS": {}}
        for dialog in dialog_act_maps["DIALOGS"]:
            if dialog in self.parser.dialog_with_intents_labels \
                    or dialog in self.parser.dialog_api_to_intent_set_api:
                dialogs_with_labels["DIALOGS"][dialog] = dialog_act_maps["DIALOGS"][dialog]
        local_dialog_act_json = os.path.dirname(output_dialog_act_maps_json) + "/local_dialog_act_map.json"
        output_dialog_act_maps_json = os.path.dirname(output_dialog_act_maps_json) + "/dialog_act_map.json"
        if os.environ.get("STORAGE") == "S3":
            dump_s3_file(output_dialog_act_maps_json,
                         bytes(json.dumps(dialogs_with_labels, indent=2).encode("UTF-8")))
            dump_s3_file(local_dialog_act_json,
                         bytes(json.dumps(self.parser.local_dialog_act, indent=2).encode("UTF-8")))
        else:
            with open(output_dialog_act_maps_json, "w") as json_file:
                json.dump(dialogs_with_labels, json_file, indent=2)
            with open(local_dialog_act_json, "w") as f:
                json.dump(self.parser.local_dialog_act, f, indent=2)

    def generate_goals(self,
                       intent_utterance_dir,
                       ontology_file,
                       intents,
                       dev_ratio=0.7,
                       paraphrase=True,
                       number_utterances=-1):
        """ Generate simulation goals. The ``intent'' slot is used to probe the intent model. The queries can be
        user provided (if paraphrase==False) or obtained via applying the paraphrasing models. The values of other
        entities are taken from the ontology_file.
        :param intent_utterance_dir: directory containing the intent queries (paraphrases or user-provided)
        :param ontology_file: automatic generated or user provided ontology file in json format
        :param intents: intents to generate goals for
        :param dev_ratio: ratio of the intent queries to be used for probing the intent model. The wrongly classified
        queries can be filtered and used to augment the original intent training utterances for model retraining.
        The rest will be used for evaluation.
        :param paraphrase: whether to use paraphrases to create goals. If False, use the original
               intent utterances for goals
        :param number_utterances: number of utterances to use for creating goals. -1 means to use all utterances
        :return:
        """

        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            ontology = read_s3_json("botsim", ontology_file)
        else:
            with open(ontology_file, "r") as fin:
                ontology = json.load(fin)

        # if paraphrase:
        para_config = "_".join([str(x) for x in self.num_paraphrases_per_model])
        if isinstance(number_utterances, int) and number_utterances > 0:
            para_config = para_config + "_" + str(number_utterances)+"_utts"
        else:
            para_config = para_config + "_all_utts"

        for intent in intents:
            if intent in self.parser.api_name_to_intent_label:
                intent = self.parser.api_name_to_intent_label[intent]
            intent = intent.replace(" ", "_")
            # print("processing", intent, "goals")
            candidates = {"eval": set(), "dev": set(), "user": set()}

            source_utterances = []
            if paraphrase:
                dev_paraphrase_json = "{}/{}_{}.paraphrases.json".format(intent_utterance_dir, intent, para_config)
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    paraphrases = read_s3_json("botsim", dev_paraphrase_json)
                else:
                    with open(dev_paraphrase_json, "r") as fin:
                        paraphrases = json.load(fin)
                for _, para in enumerate(paraphrases):
                    if random.uniform(0, 1) <= dev_ratio:
                        candidates["dev"].update(para["cands"])
                    else:
                        candidates["eval"].update(para["cands"])
                        source_utterances.append(para["source"])
            else:
                user_provided_queries_json = "{}/{}.user.json".format(intent_utterance_dir, intent)
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    assert file_exists("botsim", user_provided_queries_json)

                    # source_utterances = paraphrases[intent]
                    paraphrases = read_s3_json("botsim", user_provided_queries_json)
                    candidates["user"] = set(paraphrases[intent])
                else:
                    assert os.path.exists(user_provided_queries_json)
                    with open(user_provided_queries_json, "r") as fin:
                        paraphrases = json.load(fin)
                        candidates["user"] = set(paraphrases[intent])

            # dump simulation goals
            if paraphrase:
                if len(candidates["dev"]) > 0:
                    dev_goal_json = \
                        "{}/{}_{}.dev.paraphrases.goal.json".format(intent_utterance_dir, intent, para_config)
                    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                        dump_s3_file(dev_goal_json, bytes(json.dumps(
                            create_goals(intent, ontology, candidates["dev"]), indent=2).encode(
                            "UTF-8")))
                    else:
                        with open(dev_goal_json, "w") as json_file:
                            json.dump(create_goals(intent, ontology, candidates["dev"]),
                                      json_file, indent=2)

                if len(candidates["eval"]) > 0:
                    eval_goal_json = "{}/{}_{}.eval.paraphrases.goal.json".format(intent_utterance_dir, intent, para_config)
                    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                        dump_s3_file(eval_goal_json,
                                     bytes(json.dumps(
                                         create_goals(intent, ontology, candidates["eval"]), indent=2).encode("UTF-8")))
                        dump_s3_file(intent_utterance_dir + "/" + intent
                                     + ".eval.vanilla.goal.json",
                                     bytes(json.dumps(
                                         create_goals(intent, ontology, source_utterances), indent=2).encode("UTF-8")))
                    else:
                        with open(eval_goal_json, "w") as json_file:
                            json.dump(create_goals(intent, ontology, candidates["eval"]),
                                      json_file, indent=2)
                        with open(intent_utterance_dir + "/" + intent
                                  + ".eval.vanilla.goal.json", "w") as json_file:
                            json.dump(create_goals(intent, ontology, source_utterances), json_file, indent=2)

            else:
                eval_user_goal_json = "{}/{}.eval.user.goal.json".format(intent_utterance_dir, intent)
                if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
                    dump_s3_file(eval_user_goal_json, bytes(json.dumps(
                        create_goals(intent, ontology, candidates["user"]), indent=2).encode("UTF-8")))
                else:
                    with open(eval_user_goal_json, "w") as json_file:
                        json.dump(create_goals(intent, ontology, candidates["user"]), json_file, indent=2)

    def generate_nlg_response_templates(self, user_response_template_json):
        """ Generate user response templates to convert dialog_act + entity_slot to natural language responses
            BotSIM users can modify this template to make the generated response more diverse
        """
        assert len(self.dialog_ontology) > 0
        response_templates = {"dialog_act": {}}
        response_templates["dialog_act"]["inform"] = []
        response_templates["dialog_act"]["request"] = []
        processed = set()
        frame = {"request_slots": [], "inform_slots": ["intent"], "response": {"user": ["$intent$"]}}
        processed.add("intent")
        response_templates["dialog_act"]["inform"].append(frame)
        for dialog in self.dialog_ontology:
            for variable in self.dialog_ontology[dialog]:
                frame = {"request_slots": [], "inform_slots": [variable], "response": {}}
                frame["response"]["agent"] = []
                frame["response"]["user"] = []
                frame["response"]["user"].append("$" + variable + "$.")
                if variable not in processed:
                    response_templates["dialog_act"]["inform"].append(frame)
                    processed.add(variable)

        for variable in ["goodbye", "thanks"]:
            frame = {"request_slots": [], "inform_slots": [variable], "response": {}}
            frame["response"]["agent"] = []
            frame["response"]["agent"] = []
            frame["response"]["user"] = []
            frame["response"]["user"].append("thanks, goodbye")
            if "thanks" not in response_templates["dialog_act"]:
                response_templates["dialog_act"]["thanks"] = frame
            else:
                response_templates["dialog_act"]["thanks"].update(frame)

        user_response_template_json = os.path.dirname(user_response_template_json) + "/template.json"
        if os.environ.get("STORAGE") == "S3":
            dump_s3_file(user_response_template_json,
                         bytes(json.dumps(response_templates, indent=2).encode("UTF-8")))
        else:
            with open(user_response_template_json, "w") as fout:
                json.dump(response_templates, fout, indent=4)

    def generate_conversation_flow(self, conversation_graph_json):
        assert len(self.parser.conv_graph_visualisation_data) != 0
        if os.environ.get("STORAGE") == "S3":
            dump_s3_file(conversation_graph_json,
                         bytes(json.dumps(self.parser.conv_graph_visualisation_data, indent=2).encode("UTF-8")))
        else:
            with open(conversation_graph_json, "w") as fout:
                json.dump(self.parser.conv_graph_visualisation_data, fout, indent=4)

        from botsim.modules.remediator.remediator_utils.dialog_graph import ConvGraph
        self.conversation_graph = ConvGraph(os.path.dirname(conversation_graph_json))
        self.conversation_graph.create_conv_graph("All")

    def _generate_multi_intent_dialog_paths(self,
                                            source_dialog="",
                                            target_dialog="",
                                            must_include_dialog="",
                                            num_paths=100
                                            ):
        """ Generate multi-intent dialogs according to the conversation graph
        Simple paths mean a path with no node repetition
        :param source_dialog: source dialog
        :param target_dialog: target dialog
        :param must_include_dialog: constrain the path to contain must_included_dialog
        :param num_paths: number of paths to generate
        :return paths: list of dialog paths
        """
        i = 0
        paths = []
        if not self.conversation_graph:
            raise ValueError("Conversation graph not generated, run generate_conversation_flow")
        for path in self.conversation_graph.all_simple_path(source_dialog, target_dialog):
            valid = False
            node_set = set()
            # print(path)
            for edge in path:
                node_set.add(edge[0])
                node_set.add(edge[1])
                if edge[0] == must_include_dialog or edge[1] == must_include_dialog:
                    valid = True
            i += 1
            if i > num_paths:
                break
            if must_include_dialog == "" or valid:
                paths.append(path)
        return paths

    def generate_multi_intent_dialog_goals(self,
                                           intent_utterance_dir,
                                           must_include_dialog="",
                                           dialog_sequence=[],
                                           num_augmented_goals=100,
                                           end_dialog="End_Chat"):
        """Generate multi-intent simulation goals given a sequence of dialogs.
        :param intent_utterance_dir: target directory
        :param must_include_dialog: constrain the path to contain must_included_dialog
        :param dialog_sequence: sequence of dialogs to include in the goal
        :param num_augmented_goals: number of goals to generate
        :param end_dialog: end dialog to signal the end of the conversation, e.g., End_Chat
        :return augmented_paths: the generated multi-intend dialog paths
        """
        dialog_index = 0
        augmented_goals = {"Goal": {}}
        augmented_paths = []
        while dialog_index + 1 < len(dialog_sequence):
            new_previous_paths = []
            source_dialog = dialog_sequence[dialog_index]
            target_dialog = dialog_sequence[dialog_index + 1]
            dialog_paths = \
                self._generate_multi_intent_dialog_paths(source_dialog, target_dialog,
                                                         must_include_dialog, num_augmented_goals)
            if len(augmented_paths) == 0:
                augmented_paths.extend(dialog_paths)
            else:
                for path in augmented_paths:
                    augmented_path = []
                    for dialog_path in dialog_paths:
                        augmented_path.append(path + dialog_path)
                    new_previous_paths.extend(augmented_path)
                augmented_paths = new_previous_paths
            dialog_index += 1

        for j, path in enumerate(augmented_paths):
            transition_variables = {}
            intents = [path[0][0]]
            for src, tgt, transition in path:
                conditions = transition.split("/")
                if src in self.parser.dialog_with_intents_labels:
                    if src != intents[-1]:
                        intents.append(src)
                if tgt in self.parser.dialog_with_intents_labels:
                    intents.append(tgt)
                for condition in conditions:
                    if condition.find("== true") != -1:
                        variable = condition.split()[0]
                        if variable not in transition_variables:
                            transition_variables[variable] = []
                        transition_variables[variable].append("yes")
                    elif condition.find("== false") != -1:
                        variable = condition.split()[0]
                        if variable not in transition_variables:
                            transition_variables[variable] = []
                        transition_variables[variable].append("no")

            # merge the goals of all intents along the path, skip paths with end chat in between
            # to avoid cycles
            if end_dialog in intents and intents[-1] != end_dialog:
                continue
            augmented_goal = {"inform_slots": {}}
            intent_queries = []
            k = 0
            while k < num_augmented_goals // len(augmented_paths):
                for intent in intents:
                    para_config = "_".join([str(x) for x in self.num_paraphrases_per_model])
                    goals = load_goals(para_config, intent_utterance_dir, intent, "dev")["Goal"]
                    if not goals: break
                    selected = random.choice(list(goals.keys()))
                    intent_queries.append(goals[selected]["inform_slots"]["intent"])
                    augmented_goal["inform_slots"].update(goals[selected]["inform_slots"])
                for key in augmented_goal["inform_slots"]:
                    variable = key.split("@")[0]
                    if variable in transition_variables:
                        augmented_goal["inform_slots"][key] = transition_variables[variable]
                augmented_goal["inform_slots"]["intent"] = intent_queries
                name = "_".join(intents)
                augmented_goal["name"] = name
                augmented_goal["request_slots"] = {name: "UNK"}
                augmented_goals["Goal"][name + "_" + str(j)] = augmented_goal
                k += 1
        with open(intent_utterance_dir+"/augmented_goals.json", "w") as f:
            json.dump(augmented_goals, f, indent=2)

        return augmented_paths
