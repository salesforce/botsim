#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json, random


def parse_one_instance(text):
    item_list = text.strip('\n').split('\t')
    if len(item_list) != 2:
        return None, None
    text, label = item_list
    text = sos_u_token + ' ' + text + ' ' + eos_u_token
    label = sos_d_token + ' ' + label + ' ' + eos_d_token
    return text, label


def process_file(in_f, out_f):
    with open(in_f, 'r', encoding='utf8') as i:
        lines = i.readlines()
    res_list = []
    for line in lines:
        one_text, one_label = parse_one_instance(line)
        if one_text == None: continue
        one_dict = {"text": one_text,
                    "paraphrase": one_label}
        res_list.append(one_dict)
    with open(out_f, 'w') as outfile:
        json.dump(res_list, outfile, indent=4)


if __name__ == '__main__':
    sos_u_token, eos_u_token = '<sos_s>', '<eos_s>'
    sos_d_token, eos_d_token = '<sos_t>', '<eos_t>'

    import os

    save_path = r'../paraphraser/json_dataset/'
    os.makedirs(save_path, exist_ok=True)

    in_f = r'../paraphraser/processed_datasets/mscoco_paralex_qqp_tomhosking/' \
           r'qqp_deduped_from_triplets/train.tsv'
    out_f = save_path + r'/qqp_deduped_train_from_triplets_remove_duplicates.json'
    process_file(in_f, out_f)

    train_paraphrase_json = []
    train_paraphrase_json_mscoco_paralex_qqp = []
    dev_paraphrase_json = []
    test_paraphrase_json = []
    dataset_to_size = {}

    for dataset in ['paralex', 'qqp_deduped', 'mscoco']:
        for mode in ['train', 'dev', 'test']:
            in_f = r'../paraphraser/processed_datasets/mscoco_paralex_qqp_tomhosking/' \
                   r'{}_from_triplets/{}.tsv'.format(dataset, mode)
            out_f = save_path + r'/{}_{}_from_triplets_remove_duplicates.json'.format(dataset, mode)
            process_file(in_f, out_f)
            print(dataset, mode, 'processed')
            if mode == 'train':
                with open(out_f, 'r') as f:
                    data = json.load(f)
                    dataset_to_size[dataset] = len(data)
                    if dataset == 'mscoco':
                        # WE CONSTRAIN MSCOCO DATA TO BE LESS OR EQUAL TO THE MINIMUM OF PARALEX AND QQP
                        size = min(dataset_to_size['paralex'], dataset_to_size['qqp_deduped'])
                        data = random.sample(data, min(len(data), size))
                    train_paraphrase_json.extend(data)
                    train_paraphrase_json_mscoco_paralex_qqp.extend(data)
            elif mode == 'dev':
                with open(out_f, 'r') as f:
                    dev_paraphrase_json.extend(json.load(f))
            elif dataset == 'qqp_deduped':
                with open(out_f, 'r') as f:
                    test_paraphrase_json.extend(json.load(f))

    out_f = save_path + r'/train_mscoco_paralex_qqp_v4_paraphrase.json'
    with open(out_f, 'w') as outfile:
        json.dump(train_paraphrase_json_mscoco_paralex_qqp, outfile, indent=4)
        print('training size:', len(train_paraphrase_json_mscoco_paralex_qqp))

    train_set = set(['paws', 'multi_nli', 'snli', 'tapaco', 'paws_qqp_train'])
    dev_set = set()
    test_set = set(['paws_qqp_dev_and_test', 'paws_test', 'mrpc'])

    for dataset in ['paws', 'multi_nli', 'snli', 'tapaco', 'paralex', 'paws_dev', 'paws_test', 'paws_qqp_train',
                    'paws_qqp_dev_and_test']:
        in_f = r'../paraphraser/processed_datasets/{}/{}.txt'.format(dataset, dataset)
        out_f = save_path + r'/{}.json'.format(dataset)
        process_file(in_f, out_f)
        if dataset in train_set:
            with open(out_f, 'r') as f:
                train_paraphrase_json.extend(json.load(f))
        elif dataset in dev_set:
            with open(out_f, 'r') as f:
                dev_paraphrase_json.extend(json.load(f))
        elif dataset in test_set:
            with open(out_f, 'r') as f:
                test_paraphrase_json.extend(json.load(f))

    out_f = save_path + r'/train_mscoco_paralex_qqp_{}_paraphrase.json'.format('_'.join(list(train_set)))
    with open(out_f, 'w') as outfile:
        json.dump(train_paraphrase_json, outfile, indent=4)
        print('training size:', len(train_paraphrase_json))
