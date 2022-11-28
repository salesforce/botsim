#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json
import os
import random
import pandas as pd
from sentence_transformers import SentenceTransformer, util
from nltk.tokenize.treebank import TreebankWordDetokenizer
from rapidfuzz import fuzz

from datasets import load_dataset
from botsim.botsim_utils.utils import seed_everything

seed_everything(42)
os.environ["WANDB_DISABLED"] = "true"

detokenizer = TreebankWordDetokenizer()
sentence_transformer = SentenceTransformer("paraphrase-MiniLM-L6-v2")


def score_paraphrase(text, paraphrase):
    """
    Compute the semantic and lexical distance between a pair of sentences
    :param text: original text (or a list )
    :param paraphrase: paraphrase (or a list )
    :return cosine_sims: cosine similarity computed from sentence transformer
    :return cosine_sims: cosine similarity computed from sentence transformer
    """
    para_embeddings = sentence_transformer.encode(text, convert_to_tensor=True)
    query_embedding = sentence_transformer.encode(paraphrase, convert_to_tensor=True)
    if isinstance(text, str):
        return util.pytorch_cos_sim(
            query_embedding, para_embeddings)[0], \
               fuzz.ratio(text.lower(), paraphrase.lower())
    cos_scores = util.pytorch_cos_sim(query_embedding, para_embeddings)
    edit_distances = []
    cosine_sims = []
    for i in range(len(text)):
        edit_distance = fuzz.ratio(text[i].lower(), paraphrase[i].lower())
        edit_distances.append(edit_distance)
        cosine_sims.append(cos_scores[i][i])
    return cosine_sims, edit_distances


def curate_batches(text, paraphrase, batch_size=16):
    """
    Batchify the text/paraphrases list
    """
    assert len(text) == len(paraphrase)
    num_batches = len(text) // batch_size
    text_batches = []
    paraphrase_batches = []
    for b in range(num_batches):
        text_batch = []
        paraphrase_batch = []
        for i in range(batch_size):
            if b * batch_size < len(text):
                text_batch.append(text[b * batch_size + i])
                paraphrase_batch.append(paraphrase[b * batch_size + i])
        if len(text_batch) > 0:
            text_batches.append(text_batch)
            paraphrase_batches.append(paraphrase_batch)
    return text_batches, paraphrase_batches


def compute_cosine_similarity_edit_distance(text, paraphrase, save_path):
    text_batches, paraphrase_batches = curate_batches(text, paraphrase, 256)
    score_file = open(save_path, "w")
    for b in range(len(text_batches)):
        cosine_sims, edit_distances = score_paraphrase(text_batches[b], paraphrase_batches[b])
        for i in range(len(cosine_sims)):
            score_file.write(text_batches[b][i] + "\t" + paraphrase_batches[b][i]
                             + "\t" + str(float(cosine_sims[i])) + "\t" + str(edit_distances[i]) + "\n")
    score_file.close()


train_texts = []
train_label = []
val_texts = []
val_label = []
test_texts = []
test_label = []


def post_process_paws(paws):
    print("post-processing PAWS")
    os.makedirs(r"../data/processed_datasets/paws/", exist_ok=True)
    save_path = r"../data/processed_datasets/paws/paws.txt"
    text_to_paraphrases = []
    if os.path.exists(save_path):
        for line in open(save_path, "r"):
            line = line.strip()
            text, paraphrase = line.split("\t")
            text_to_paraphrases.append((text, paraphrase))
        return text_to_paraphrases, save_path

    processed_paws = open(save_path, "w")
    for text, paraphrase in paws:
        if text.find(" , ") != -1 or text.find(" \"s ") != -1 or text.find(" .") != -1: continue
        processed_paws.write(text + "\t" + paraphrase + "\n")
        text_to_paraphrases.append((text, paraphrase))
    processed_paws.close()
    return text_to_paraphrases, save_path


def prepare_paws_train():
    paws_train_csv = pd.read_csv(r"../paraphraser/data/raw_data/paws_final/train.tsv", sep="\t")
    paws_train = paws_train_csv[paws_train_csv["label"] == 1]
    s1 = list(paws_train["sentence1"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" "))))
    s2 = list(paws_train["sentence2"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" "))))

    paws_swap_csv = pd.read_csv(r"../paraphraser/data/raw_data/paws_swap/train.tsv", sep="\t")
    paws_swap = paws_swap_csv[paws_swap_csv["label"] == 1]
    s1.extend(list(paws_swap["sentence1"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" ")))))
    s2.extend(list(paws_swap["sentence2"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" ")))))
    paws = [(a, b) for a, b in zip(s1, s2)]
    paws, path = post_process_paws(paws)
    return paws, path


def prepare_paws_dev_test():
    os.makedirs(r"../data/processed_datasets/paws_dev/", exist_ok=True)
    dev_save_path = r"../data/processed_datasets/paws_dev/paws_dev.txt"
    paws_dev = pd.read_csv(r"../paraphraser/data/raw_data/paws_final/dev.tsv", sep="\t")
    paws_dev = paws_dev[paws_dev["label"] == 1]
    s1 = list(paws_dev["sentence1"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" "))))
    s2 = list(paws_dev["sentence2"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" "))))
    processed_paws = open(dev_save_path, "w")
    for a, b in zip(s1, s2):
        processed_paws.write(a + "\t" + b + "\n")
    processed_paws.close()
    test_save_path = r"../data/processed_datasets/paws_test/paws_test.txt"
    os.makedirs(r"../data/processed_datasets/paws_test/", exist_ok=True)
    paws_test_csv = pd.read_csv(r"../paraphraser/data/raw_data/paws_final/test.tsv", sep="\t")
    paws_test = paws_test_csv[paws_test_csv["label"] == 1]
    s1 = list(paws_test["sentence1"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" "))))
    s2 = list(paws_test["sentence2"].apply(
        lambda x: detokenizer.detokenize(x.replace("``", "").replace("\"\"", "").split(" "))))
    paws_test_set = [(a, b) for a, b in zip(s1, s2)]
    processed_paws = open(test_save_path, "w")
    for a, b in zip(s1, s2):
        processed_paws.write(a + "\t" + b + "\n")
    processed_paws.close()
    return paws_dev, paws_test_set, dev_save_path, test_save_path


def prepare_paws_qqp():
    train_path, dev_path = "", ""
    for mode in ["dev_and_test", "train"]:
        os.makedirs(r"../paraphraser/data/processed_datasets/paws_qqp_{}".format(mode), exist_ok=True)
        save_path = r"../paraphraser/data/processed_datasets/paws_qqp_{}/paws_qqp_{}.txt".format(mode, mode)
        if mode == "train":
            train_path = save_path
        else:
            dev_path = save_path
        paws_qqp = pd.read_csv(r"/export/home/projects/pegasus/paws_qqp/output/{}.tsv".format(mode), sep="\t")
        paws_qqp = paws_qqp[paws_qqp["label"] == 1]
        processed_paws_qqp = open(save_path, "w")
        for a, b in zip(paws_qqp["sentence1"], paws_qqp["sentence2"]):
            processed_paws_qqp.write(a + "\t" + b + "\n")
        processed_paws_qqp.close()
    return train_path, dev_path


###### Prepare SNLI + MNLI ####
def score_nli(identifier="multi_nli"):
    dataset = load_dataset(identifier, split="train")
    dataset = dataset.filter(lambda example: example["label"] == 0)
    save_path = r"../paraphraser/data/processed_datasets/{}/{}_train_score.tsv".format(identifier, identifier)
    os.makedirs(r"../paraphraser/data/processed_datasets/{}/".format(identifier), exist_ok=True)
    score_file = open(save_path, "w")

    for entry in dataset:
        if entry["label"] != 0: continue
        text, paraphrase = entry["premise"], entry["hypothesis"]
        if "genre" in entry and entry["genre"] == "telephone": continue
        cosine_score, edit_distance = score_paraphrase(text, paraphrase)
        score_file.write(text + "\t" + paraphrase + "\t" +
                         str(float(cosine_score)) + "\t" + str(edit_distance) + "\n")
    score_file.close()


def score_snli_mnli():
    score_nli("snli")
    score_nli("multi_nli")


def filter_nli(cosine_low, cosine_high, edit_high, diff_ratio=0.5, identifier="multi_nli", verbose=False):
    """
    Filter SNLI + MNLI pairs to discard pairs with very high and very low semantic scores.
    Also discard pairs with high lexical similarity
    """
    texts = []
    labels = []
    scores = r"../paraphraser/data/processed_datasets/{}/{}_train_score.tsv".format(identifier, identifier)
    with open(scores) as f:
        for line in f:
            line = line.rstrip("\n")
            text, paraphrase, cosine_score, edit_distance = line.split("\t")
            if text.find(" uh ") != -1 or text.find(" uh-huh ") != -1 \
                    or text.find(" oh ") != -1 or text.find(" um-hum ") != -1:
                continue
            word_count_diff = abs(len(text.split()) - len(paraphrase.split()))
            ratio = word_count_diff / (max(len(text.split()), len(paraphrase.split())))
            if cosine_low <= float(cosine_score) <= cosine_high \
                    and ratio < diff_ratio and int(edit_distance) <= edit_high:
                texts.append(text)
                labels.append(paraphrase)
                if verbose:
                    print(text, paraphrase, cosine_score, ratio)
    filtered_set = r"../paraphraser/data/processed_datasets/{}/{}.txt".format(identifier, identifier)
    with open(filtered_set, "w") as f:
        for a, b in zip(texts, labels):
            f.write(a + "\t" + b + "\n")
    return [(a, b) for a, b in zip(texts, labels)], filtered_set


## Tapaco dataset

def score_tapaco():
    tapaco = pd.read_csv(r"../paraphraser/data/raw_data/tapaco_paraphrases_dataset.csv", sep="\t")
    os.makedirs(r"../data/processed_datasets/tapaco/", exist_ok=True)
    save_path = r"../data/processed_datasets/tapaco/tapaco_train_score.tsv"
    compute_cosine_similarity_edit_distance(list(tapaco["Text"]), list(tapaco["Paraphrase"]), save_path)


def filter_tapaco(cosine_low=0.0, cosine_high=0.8, edit_high=70, diff_ratio=1.0, min_len=5):
    texts = []
    labels = []
    with open(r"../data/processed_datasets/tapaco/tapaco_train_score.tsv") as f:
        for line in f:
            line = line.rstrip("\n")
            text, paraphrase, cosine_score, edit_distance = line.split("\t")
            diff = abs(len(text.split()) - len(paraphrase.split()))
            ratio = diff / (max(len(text.split()), len(paraphrase.split())))
            if cosine_low <= float(cosine_score) <= cosine_high \
                    and ratio < diff_ratio \
                    and max(len(text.split()), len(paraphrase.split())) > min_len \
                    and int(edit_distance) < edit_high:
                texts.append(text)
                labels.append(paraphrase)
    filtered = r"../paraphraser/data/processed_datasets/tapaco/tapaco.txt"
    with open(filtered, "w") as f:
        for a, b in zip(texts, labels):
            f.write(a + "\t" + b + "\n")
    return [(a, b) for a, b in zip(texts, labels)], filtered


def process_mrpc(save_path):
    import csv
    mrpc = csv.reader(open(r"../paraphraser/data/raw_data/mrpc.tsv", "r"), delimiter="\t", quoting=csv.QUOTE_NONE)
    f = open(save_path, "w")
    texts, labels = [], []
    for line in mrpc:
        if str(line[0]) == "1":
            f.write(line[3] + "\t" + line[4] + "\n")
            texts.append(line[3])
            labels.append(line[4])

    return [(a, b) for a, b in zip(texts, labels)]


## paralex
#
def score_paralex():
    paralex = pd.read_csv(r"../paraphraser/data/raw_data/paralex_paraphrases_dataset.csv", sep="\t")
    os.makedirs(r"../paraphraser/data/processed_datasets/paralex/", exist_ok=True)
    save_path = r"../paraphraser/data/processed_datasets/paralex/paralex_train_score.tsv"
    compute_cosine_similarity_edit_distance(
        list(paralex["ill formed"]), list(paralex["well formed"]), save_path)


def filter_paralex(cosine_low=0.0, cosine_high=0.8, edit_high=70, diff_ratio=1.0):
    texts = []
    labels = []
    with open(r"../paraphraser/data/processed_datasets/paralex/paralex_train_score.tsv") as f:
        for line in f:
            line = line.rstrip("\n")
            text, paraphrase, cosine_score, edit_distance = line.split("\t")
            if paraphrase.find("&quot") != -1 \
                    or paraphrase.find("\\") != -1 \
                    or paraphrase.find("^") != -1:
                continue
            import re
            garbage = re.compile("[\d$\[/{}\/&_`\+\-\*()“”]")
            if garbage.search(text) != None \
                    or garbage.search(paraphrase) != None: continue

            diff = abs(len(text.split()) - len(paraphrase.split()))
            ratio = diff / (max(len(text.split()), len(paraphrase.split())))
            if cosine_low <= float(cosine_score) <= cosine_high \
                    and ratio < diff_ratio \
                    and int(edit_distance) < edit_high:
                prob = random.uniform(0, 1)
                if prob > 0.5:
                    texts.append(text)
                    labels.append(paraphrase)
                else:
                    texts.append(paraphrase)
                    labels.append(text)
    filtered = r"../paraphraser/data/processed_datasets/paralex/paralex.txt"
    with open(filtered, "w") as f:
        for a, b in zip(texts, labels):
            f.write(a + "\t" + b + "\n")
    return [(a, b) for a, b in zip(texts, labels)], filtered


# prepare additional training data from https://github.com/tomhosking/hrq-vae
# 1) MSCOCO 2) Paralex 3) QQP

def process_mscoco_paralex_qqp_hrq_vae_jsonl(path):
    """
    Process HRQ-VAE dataset: https://github.com/tomhosking/hrq-vae
    """
    paraphrase_dataset = {}
    for dataset in ["train", "dev", "test"]:
        paraphrase_dataset[s] = list()
        entries = set()
        with open(path + "/{}.jsonl".format(dataset), "r") as json_file:
            json_list = list(json_file)
        for json_str in json_list:
            qs = json.loads(json_str)
            text, paraphrase = qs["sem_input"], qs["tgt"]
            src_tgt = text.lower().strip() + "+" + paraphrase.lower().strip()
            if src_tgt not in entries:
                paraphrase_dataset[s].append((text, paraphrase))
                entries.add(src_tgt)
    return paraphrase_dataset


def get_hrq_vae_test_set(eval_path):
    test_set = set()
    with open(eval_path, "r") as json_file:
        json_list = list(json_file)
    for json_str in json_list:
        qs = json.loads(json_str)
        text, paraphrase, candidates = qs["sem_input"], qs["tgt"], qs["paras"]
        test_set.add(text.lower())
        test_set.add(paraphrase.lower())
        test_set.update(candidates)
    return test_set


if __name__ == "__main__":
    data_path = {}
    paws_dev, paws_test, dev_path, test_path = prepare_paws_dev_test()
    data_path = {"test": [test_path], "dev": [dev_path]}
    num_dev_utt = len(paws_dev)
    paws_train, path = prepare_paws_train()
    data_path["train"] = [path]
    num_train_utt = len(paws_train)
    print("paws_train", num_train_utt)

    nli_score_path = r"../data/processed_datasets/multi_nli/multi_nli_train_score.tsv"
    if not os.path.exists(nli_score_path):
        print("scoring NLI")
        score_snli_mnli()

    tapaco_score_path = r"../data/processed_datasets/tapaco/tapaco_train_score.tsv"
    if not os.path.exists(tapaco_score_path):
        print("scoring tapaco")
        score_tapaco()

    paralex_score_path = r"../paraphraser/data/processed_datasets/paralex/paralex_train_score.tsv"
    if not os.path.exists(paralex_score_path):
        print("scoring paralex")
        score_paralex()

    # discard pairs in nli datasets with large differences in length
    snli_trn, path = filter_nli(0.8, 0.99, 70, diff_ratio=0.4, identifier="snli")
    data_path["train"].append(path)

    mnli_trn, path = filter_nli(0.7, 0.99, 70, diff_ratio=0.5, identifier="multi_nli")
    data_path["train"].append(path)

    snli_train = snli_trn[:-num_dev_utt // 2]
    mnli_train = mnli_trn[:-num_dev_utt // 2]
    print("snli_train", len(snli_train))
    print("mnli_train", len(mnli_train))

    # tapaco
    tapaco, path = filter_tapaco(0.5, 0.8, 70, 1.0, 5)
    data_path["train"].append(path)
    print("tapaco", len(tapaco))
    # paralex is the most noisy dataset, apply stricter threshold
    paralex, path = filter_paralex(0.85, 0.99, 70, 1.0)
    data_path["train"].append(path)
    print("paralex", len(paralex))

    train_path, dev_path = prepare_paws_qqp()
    data_path["train"].append(train_path)
    data_path["dev"].append(dev_path)

    qqp = process_mscoco_paralex_qqp_hrq_vae_jsonl(
        "../paraphraser/data/raw_data/qqp-deduped/qqp-clusters-chunk-extendstop-realexemplars-exhaustive-drop30-N26-R100-deduped")
    qqp_test = "../paraphraser/data/raw_data/qqp-deduped/qqp-splitforgeneval/test.jsonl"
    qqp_dev = "../paraphraser/data/raw_data/qqp-deduped/qqp-splitforgeneval/dev.jsonl"
    utterances = get_hrq_vae_test_set(qqp_test)
    utterances.update(get_hrq_vae_test_set(qqp_dev))

    for dataset in ["train", "dev", "test"]:
        paraphrases = qqp[dataset]
        print("qqp-" + dataset + ":", len(paraphrases))
        tgt_dir = "../paraphraser/data/processed_datasets/mscoco_paralex_qqp_tomhosking/qqp_deduped_from_triplets/"
        os.makedirs(tgt_dir, exist_ok=True)
        with open(tgt_dir + "/" + dataset + ".tsv", "w") as f:
            for text, para in paraphrases:
                if s == "train" and (text.lower() in utterances or para in utterances):
                    continue
                f.write(text + "\t" + para + "\n")
            data_path[s].append(tgt_dir + "/" + dataset + ".tsv")

    paralex = process_mscoco_paralex_qqp_hrq_vae_jsonl(
        "../paraphraser/data/raw_data/training-triples/wikianswers-triples-chunk-extendstop-realexemplars-resample-drop30-N5-R100")
    paralex_test = "../paraphraser/data/raw_data/wikianswers-para-splitforgeneval/test.jsonl"
    paralex_dev = "../paraphraser/data/raw_data/wikianswers-para-splitforgeneval/dev.jsonl"
    utterances = get_hrq_vae_test_set(paralex_test)
    utterances.update(get_hrq_vae_test_set(paralex_dev))

    for dataset in ["train", "dev", "test"]:
        paraphrases = paralex[s]
        tgt_dir = "../paraphraser/data/processed_datasets/mscoco_paralex_qqp_tomhosking/paralex_from_triplets/"
        os.makedirs(tgt_dir, exist_ok=True)
        with open(tgt_dir + "/" + s + ".tsv", "w") as f:
            for text, para in paraphrases:
                if dataset == "train" and (text.lower() in utterances or para in utterances):
                    continue
                f.write(text + "\t" + para + "\n")
            data_path[dataset].append(tgt_dir + "/" + dataset + ".tsv")


    mscoco = process_mscoco_paralex_qqp_hrq_vae_jsonl(
        "../paraphraser/data/raw_data/mscoco-clusters-chunk-nostop-extendstop-realexemplars-resample-drop30-N5-R100")

    mscoco_test = "../paraphraser/data/raw_data/mscoco-eval/test.jsonl"
    mscoco_dev = "../paraphraser/data/raw_data/mscoco-eval/dev.jsonl"
    utterances = get_hrq_vae_test_set(mscoco_test)
    utterances.update(get_hrq_vae_test_set(mscoco_dev))
    for s in ["train", "dev", "test"]:
        paraphrases = mscoco[s]
        tgt_dir = "../paraphraser/data/processed_datasets/mscoco_paralex_qqp_tomhosking/mscoco_from_triplets/"
        os.makedirs(tgt_dir, exist_ok=True)
        with open(tgt_dir + "/" + s + ".tsv", "w") as f:
            for text, para in paraphrases:
                if s == "train" and (text.lower() in utterances or para in utterances):
                    continue
                f.write(text + "\t" + para + "\n")
            data_path[s].append(tgt_dir + "/" + s + ".tsv")

    with open("data_config.json", "w") as f:
        json.dump(data_path, f, indent=2)
