#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import random, string, yaml, json, os, io, requests
import boto3

import sacrebleu

access_key = os.environ.get("AWS_ACCESS")
secret_key = os.environ.get("AWS_SECRET")
S3_BUCKET_NAME = "botsim"


def compute_bleu_scores(inputs, predictions, references, alpha=0.6):
    ref_inputs = []
    pred_output = []
    for i, input in enumerate(inputs):
        pred_output.append(predictions[i])
        ref_inputs.append([input])

    max_num_refs = max([len(x) for x in references])
    refs_padded = [x + [x[0]] * (max_num_refs - len(x)) for x in references]

    tgt_bleu = sacrebleu.corpus_bleu(pred_output, list(zip(*refs_padded)), lowercase=True).score
    self_bleu = sacrebleu.corpus_bleu(pred_output, list(zip(*ref_inputs)), lowercase=True).score
    dev_bleu = alpha * tgt_bleu - (1 - alpha) * self_bleu

    return tgt_bleu, self_bleu, dev_bleu


def seed_everything(seed):
    import random, os
    import numpy as np
    import torch
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = True
        torch.cuda.manual_seed_all(seed)


class ConfusionInQuestionFile(Exception):
    def __init__(self, confused_dialog_acts, message):
        error_message = "bot intent/dialog success message:"" + \
                        message + "" has been mapped to multiple " \
                        "request dialog acts:[ " \
                        + str(confused_dialog_acts) + "]"
        error_message += ". Please revise the bot question file"
        super().__init__(error_message)


def cut_string(agent_response, num_words=10):
    """
    cut the long response into multiple lines with max number of num_words per line
    :param agent_response:
    :param num_words: number of words per line
    """
    items = agent_response.split(" ")
    pretty_response = ""
    for i, item in enumerate(items):
        pretty_response = pretty_response + " " + item
        if i > 0 and i % num_words == 0:
            pretty_response += "\n" + " " * 7
    return pretty_response


def random_text_generator(size=6, chars=string.ascii_uppercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


########## I/O utilities ##########

def download_google_drive_url(url, output_path, output_file_name):
    """
    Download a file from google drive
    Downloading an URL from google drive requires confirmation when
    the file of the size is too big (google drive notifies that
    anti-viral checks cannot be performed on such files)
    """

    with requests.Session() as session:

        # First get the confirmation token and append it to the URL
        with session.get(url, stream=True, allow_redirects=True) as response:
            for k, v in response.cookies.items():
                if k.startswith("download_warning"):
                    url = url + "&confirm=" + v

        # Then download the content of the file
        with session.get(url, stream=True, verify=True) as response:

            path = os.path.join(output_path, output_file_name)
            total_size = int(response.headers.get("Content-length", 0))
            with open(path, "wb") as file:
                from tqdm import tqdm

                with tqdm(total=total_size) as progress_bar:
                    for block in response.iter_content(
                            chunk_size=io.DEFAULT_BUFFER_SIZE
                    ):
                        file.write(block)
                        progress_bar.update(len(block))


def serialize_sets(obj):
    if isinstance(obj, set):
        return list(obj)
    return obj


def file_exists(bucket, name):
    if os.environ.get("STORAGE") == "S3":
        res = list_s3_objects(bucket, name)
        return "Contents" in res
    else:
        return os.path.exists(name)


def list_s3_objects(bucket, name):
    s3_client = boto3.client("s3", aws_access_key_id=access_key,
                             aws_secret_access_key=secret_key)
    res = s3_client.list_objects(Bucket=bucket, Prefix=name, MaxKeys=1)
    return res


def dump_s3_file(name, object_data):
    s3_client = boto3.client(service_name="s3", aws_access_key_id=access_key,
                             aws_secret_access_key=secret_key)
    s3_client.put_object(Body=object_data, Bucket=S3_BUCKET_NAME, Key=name)


def read_s3_json(bucket, name):
    if os.environ.get("STORAGE") == "S3":
        s3_client = boto3.client(service_name="s3", aws_access_key_id=access_key,
                                 aws_secret_access_key=secret_key)

        obj = s3_client.get_object(Bucket=bucket, Key=name)
        data = json.loads(obj["Body"].read())
        return data
    else:
        with open(name, "r") as file:
            return json.load(file)


def read_s3_data(bucket, name):
    s3_client = boto3.client(service_name="s3", aws_access_key_id=access_key,
                             aws_secret_access_key=secret_key)

    obj = s3_client.get_object(Bucket=bucket, Key=name)
    return obj["Body"].read()


def read_s3_yaml(bucket, name):
    s3_client = boto3.client(service_name="s3", aws_access_key_id=access_key,
                             aws_secret_access_key=secret_key)

    response = s3_client.get_object(Bucket=bucket, Key=name)

    return yaml.safe_load(response["Body"])


def dump_json_to_file(file_path, json_data):
    if os.environ.get("STORAGE") == "S3":
        dump_s3_file(file_path, bytes(json.dumps(json_data, indent=2, default=serialize_sets).encode("UTF-8")))
    else:
        with open(file_path, "w") as file:
            json.dump(json_data, file, indent=2, default=serialize_sets)


########## GeneratorBase utilities ##########
def create_goals(intent, ontology, intent_utt_paraphrases):
    """
    Create simulation goals  from ontology and intent utterance paraphrases
    :param intent: the intent/dialog name
    :param ontology: the ontology with the entity values
    :param intent_utt_paraphrases: paraphrases of the intent training utterances to be used as the intent queries
    :return: simulation goals/agendas for intent
    """
    goals = {"Goal": {}}
    for index, para in enumerate(intent_utt_paraphrases):
        intent = intent.replace("_dev", "").replace("_eval", "").replace("_augmented", "")
        goal_name = intent + "_" + str(index)
        goals["Goal"][goal_name] = {"inform_slots": {}, "request_slots": {}}
        goals["Goal"][goal_name]["name"] = intent
        goals["Goal"][goal_name]["request_slots"][intent] = "UNK"
        for variable in ontology[intent]:
            if len(ontology[intent][variable]) > 0:
                goals["Goal"][goal_name]["inform_slots"][variable] = \
                    random.choice(ontology[intent][variable])
        goals["Goal"][goal_name]["inform_slots"]["intent"] = para
    return goals


def load_goals(para_config, intent_utterance_dir, intent_name, mode, number_utterances=-1):
    if number_utterances > 0:
        para_config = para_config + "_utt_" + str(number_utterances)
    else:
        para_config = para_config + "_utt_all"
    goal_path = intent_utterance_dir + "/" + intent_name + "_" + para_config + ".{}.paraphrases.goal.json".format(mode)
    if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
        return read_s3_json(S3_BUCKET_NAME, goal_path, "r")
    elif os.path.exists(goal_path):
        with open(goal_path, "r") as json_file:
            return json.load(json_file)
    return None


def load_user_goal(filename):
    data = read_s3_json(S3_BUCKET_NAME, filename)
    key = list(data.keys())[0]
    return data[key]


def load_intent_examples(filename):
    data = read_s3_json(S3_BUCKET_NAME, filename)
    key = list(data.keys())[0]
    return data[key]


########## Database utilities ###########
def get_bot_platform_intents(database_records):
    bot_platforms = set()
    dev_intents = {}
    eval_intents = {}
    for row in database_records:
        record = dict(row)
        platform = record["type"]
        test_id = record["id"]
        dev_intents[test_id] = record["dev"].split(",")
        eval_intents[test_id] = record["eval"].split(",")
        bot_platforms.add(str(platform))
        all_intents = dev_intents[test_id]
    return list(bot_platforms), dev_intents, eval_intents, all_intents


def convert_list_to_dict(lst):
    ret = {}
    for x in lst:
        ret[x[0]] = round(x[1], 3)
    return ret


def load_reports(test_id, database_records):
    test_session = {}
    for row in database_records:
        record = dict(row)
        test_session[record["mode"]] = record
    aggregated_report = []
    aggregated_report_json = "data/bots/" + str(test_id) + "/results/report.json"
    if file_exists(S3_BUCKET_NAME, aggregated_report_json):
        aggregated_report = read_s3_json(S3_BUCKET_NAME, aggregated_report_json)
    dev_confusion_matrix = []
    cm_path = "data/bots/" + str(test_id) + "/cm_data/cm_dev_report.json"
    if file_exists(S3_BUCKET_NAME, cm_path):
        dev_confusion_matrix = read_s3_json(S3_BUCKET_NAME, cm_path)

    eval_confusion_matrix = []
    cm_path = "data/bots/" + str(test_id) + "/cm_data/cm_eval_report.json"
    if os.path.exists(cm_path):
        eval_confusion_matrix = read_s3_json(S3_BUCKET_NAME, cm_path)

    return test_session, aggregated_report, dev_confusion_matrix, eval_confusion_matrix


def extract_simulation_metrics(test_ids, database_rows):
    dev_metrics = []
    eval_metrics = []
    for row in database_rows:
        record = dict(row)
        intent = record["intent"]
        if not intent:
            continue
        if record["mode"] == "dev":
            dev_metrics.append(
                {"label": intent + " Success Dev",
                 "data": dict(zip(test_ids, record["success_rate"].split(",")))})
            dev_metrics.append(
                {"label": intent + " Intent Dev",
                 "data": dict(zip(test_ids, record["intent_rate"].split(",")))})
            dev_metrics.append(
                {"label": intent + " NER Dev",
                 "data": dict(zip(test_ids, record["ner_rate"].split(",")))})
            dev_metrics.append(
                {"label": intent + " Other Dev",
                 "data": dict(zip(test_ids, record["other_rate"].split(",")))})
        else:
            eval_metrics.append(
                {"label": intent + " Success Eval",
                 "data": dict(zip(test_ids, record["success_rate"].split(",")))})
            eval_metrics.append(
                {"label": intent + " Intent Eval",
                 "data": dict(zip(test_ids, record["intent_rate"].split(",")))})
            eval_metrics.append({"label": intent + " NER Eval",
                                 "data": dict(zip(test_ids, record["ner_rate"].split(",")))})
            eval_metrics.append({"label": intent + " Other Eval",
                                 "data": dict(zip(test_ids, record["other_rate"].split(",")))})
    return dev_metrics, eval_metrics


class BotTestInstanceBase:
    def __init__(self, test_id, bot_platform, descript, status, name, dev, eval, created_at, updated_at, version,
                 num_t5_paraphrases, num_pegasus_paraphrases, num_intent_utts, num_simulations,
                 max_simulation_rounds):
        self.id = test_id
        self.status = status
        self.type = bot_platform
        self.descript = descript
        self.name = name
        self.dev = dev
        self.eval = eval
        self.version = version
        self.max_simulation_rounds = max_simulation_rounds
        self.num_simulations = num_simulations
        self.num_intent_utts = num_intent_utts
        self.num_pegasus_paraphrases = num_pegasus_paraphrases
        self.num_t5_paraphrases = num_t5_paraphrases
        self.created_at = created_at
        self.updated_at = updated_at

    def generate_config(self):
        """
        Generate the simulation configuration files
        """
        config = {"id": self.id, "platform": self.type, "generator": {}, "simulator": {},
                  "remediator": {}, "api": {},
                  "generator": {"paraphraser_config": {}, "dev_intents": self.dev.split(","),
                                "eval_intents": self.eval.split(",")}}
        config["generator"]["paraphraser_config"] = {
            "num_t5_paraphrases": self.num_t5_paraphrases,
            "num_pegasus_paraphrases": self.num_pegasus_paraphrases,
            "num_utterances": self.num_intent_utts,
            "num_simulations": self.num_simulations
        }

        config["generator"]["parser_config"] = {}
        if self.type == "Einstein_Bot":
            config["generator"]["parser_config"] = {
                "botversion": self.version,
                "botversion_xml": "data/bots/{}/{}/bots/metadata.bot".format(self.type, self.id)
            }
        config["generator"]["parser_config"]["beginning_dialogs"] = []
        config["generator"]["parser_config"]["excluded_dialogs"] = []
        config["generator"]["parser_config"]["failure_ending_dialogs"] = []

        config["generator"]["file_paths"] = {
            "customer_entities": "data/bots/{}/{}/goals_dir/entities.json".format(self.type, self.id),
            "response_template": "data/bots/{}/{}/conf/template.json".format(self.type, self.id),
            "dialog_act_map": "data/bots/{}/{}/conf/dialog_act_map.json".format(self.type, self.id),
            "ontology": "data/bots/{}/{}/conf/ontology.json".format(self.type, self.id),
            "revised_dialog_act_map": "data/bots/{}/{}/conf/dialog_act_map.revised.json".format(self.type, self.id),
            "revised_ontology": "data/bots/{}/{}/conf/ontology.revised.json".format(self.type, self.id),
            "goals_dir": "data/bots/{}/{}/goals_dir".format(self.type, self.id)
        }
        config["simulator"] = {"run_time": {}, "dev_intents": self.dev.split(","), "eval_intents": self.eval.split(",")}
        config["simulator"]["run_time"] = {
            "max_round_num": self.max_simulation_rounds
        }
        if self.type == "Einstein_Bot":
            config["simulator"]["run_time"]["intent_check_turn_index"] = 3
        elif self.type == "DialogFlow_CX":
            config["simulator"]["run_time"]["intent_check_turn_index"] = 2

        config["remediator"] = {"file_paths": {}, "dev_intents": self.dev.split(","),
                                "eval_intents": self.eval.split(",")}
        config["remediator"]["file_paths"] = {
            "paraphrases": "data/bots/{}/{}/goals_dir/<intent>_<para_setting>_utt_"
                           "<num_utterances>.paraphrases.json".format(self.type, self.id),
            "simulated_dialogs": "data/bots/{}/{}/remediation/<intent>/simulated_dialogs_<mode>_"
                                 "<para_setting>_<num_utterances>_utts_<num_simulations>_sessions.json".format(
                self.type, self.id),
            "intent_predictions": "data/bots/{}/{}/remediation/<intent>/intent_predictions_<mode>_"
                                  "<para_setting>_<num_utterances>_utts_<num_simulations>_sessions.json".format(
                self.type, self.id),
            "simulation_log": "data/bots/{}/{}/simulation/<intent>/logs_<mode>_<para_setting>_"
                              "<num_utterances>_utts_paraphrases_<num_simulations>_sessions.json".format(
                self.type, self.id),
            "simulation_error_info": "data/bots/{}/{}/simulation/<intent>/errors_<mode>_<para_setting>_"
                                     "<num_utterances>_utts_paraphrases_<num_simulations>_sessions.json".format(
                self.type, self.id),
            "ner_error_json": "data/bots/{}/{}/remediation/<intent>/ner_errors_<mode>_<para_setting>_"
                              "<num_utterances>_utts_<num_simulations>_sessions.json".format(self.type, self.id),
            "intent_remediation": "data/bots/{}/{}/remediation/<intent>/intent_remediation_<mode>_<para_setting>_"
                                  "<num_utterances>_utts_<num_simulations>_sessions.json".format(self.type, self.id)
        }
        config["api"] = {
            "end_point": "https://d.la5-c2-ia5.salesforceliveagent.com/chat",
            "org_Id": "00D8c00000xxxxx",
            "deployment_Id": "xxxxx000000xxxx",
            "button_Id": "xxxxx00000xxxxx",
            "location_id": "us-central1",
            "agent_id": "xxxxxxx-xxxx-xxxx-xxxx-xxxxxx80badd",
            "project_id": "xxxxxx-xxxxx-xxxxx",
            "cx_credential": "platforms/dialogflow_cx/cx.json"
        }

        return config

    def update_config(self, config):
        self.config.update(config)


class BotTestInstance(BotTestInstanceBase):
    def __init__(self, test_id, bot_platform, descript, status, name, dev, eval, end_point, orgId, deploymentId,
                 buttonId,
                 created_at, updated_at, version,
                 num_t5_paraphrases, num_pegasus_paraphrases, num_intent_utts, num_simulations,
                 max_simulation_rounds):
        super().__init__(test_id, bot_platform, descript, status, name, dev, eval, created_at, updated_at, version,
                         num_t5_paraphrases, num_pegasus_paraphrases, num_intent_utts, num_simulations,
                         max_simulation_rounds)
        self.end_point = end_point
        self.orgId = orgId
        self.deploymentId = deploymentId
        self.buttonId = buttonId
        self.cx_credential = end_point
        self.project_id = orgId
        self.location_id = deploymentId
        self.agent_id = buttonId
