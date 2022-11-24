#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import sacrebleu
import json, os
from string import punctuation


def bleu_corpus(golds, preds, order=4):
    return sacrebleu.corpus_bleu(
        [p.lower().strip(punctuation) for p in preds], [[g.lower().strip(punctuation) for g in golds]]).score

def ibleu_corpus(golds, preds, inputs, alpha=0.8):
    return alpha * bleu_corpus(golds, preds) - \
           (1 - alpha) * bleu_corpus(preds, inputs), bleu_corpus(golds, preds), bleu_corpus(preds, inputs)


def load_dev_jsonl(dev_jsonl_path):
    paraphrase_dataset = []
    name = os.path.basename(dev_jsonl_path)
    dir_name = os.path.dirname(dev_jsonl_path)
    dev_jsonl = '.'.join(name.split('.')[:-1])
    with open(dir_name+'/'+dev_jsonl+'.jsonl', 'r') as json_file:
        json_list = list(json_file)
    for json_str in json_list:
        qs = json.loads(json_str)
        text, paraphrase, candidates = qs['sem_input'], qs['tgt'], qs['paras']
        paraphrase_dataset.append(candidates)
    return paraphrase_dataset


def load_eval_jsonl(eval_path):
    paraphrase_dataset = []
    name = os.path.basename(eval_path)
    dir_name = os.path.dirname(eval_path)
    eval_jsonl = '.'.join(name.split('.')[:-1])
    with open(dir_name+'/'+eval_jsonl+'.jsonl', 'r') as json_file:
        json_list = list(json_file)
    for json_str in json_list:
        qs = json.loads(json_str)
        text, paraphrase, candidates = qs['sem_input'], qs['tgt'], qs['paras']
        paraphrase_dataset.append(candidates)
    return paraphrase_dataset


def get_checkpoint_name(prefix):
    file_names = os.listdir(prefix)
    for name in file_names:
        if name.startswith('epoch'):
            print(name)
            return name
