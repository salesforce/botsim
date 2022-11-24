#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json
import torch
import random
from torch.nn.utils import rnn
from botsim.botsim_utils.utils import seed_everything
seed_everything(42)

class ParaphraseData:
    def __init__(self, tokenizer, train_path, test_path, mode="train"):
        self.tokenizer = tokenizer
        prefix_text = "paraphrase:"

        self.tgt_sos_token_id = self.tokenizer.convert_tokens_to_ids(["<s>"])[0]
        self.tgt_eos_token_id = self.tokenizer.convert_tokens_to_ids(["</s>"])[0]

        self.src_sos_token_id = self.tokenizer.convert_tokens_to_ids(["<s>"])[0]
        self.src_eos_token_id = self.tokenizer.convert_tokens_to_ids(["</s>"])[0]

        self.prefix_id = self.tokenizer.convert_tokens_to_ids(self.tokenizer.tokenize(prefix_text))

        self.pad_token_id = self.tokenizer.convert_tokens_to_ids(["<pad>"])[0]

        print ("Loading training data...")

        self.train_data_id_list, self.train_data_text_list = [], []
        if mode == "train":
            self.train_data_id_list, self.train_data_text_list = self.load_json_data(train_path)
            print ("Training data size is {}".format(len(self.train_data_id_list)))
        print ("Loading test data...")
        self.test_data_id_list,  self.test_data_text_list, self.paraphrase_references = self.load_jsonl_data(test_path)

        print ("Test data size is {}".format(len(self.test_data_id_list)))
        self.train_num, self.test_num = len(self.train_data_id_list), len(self.test_data_id_list)

    def load_jsonl_data(self, eval_path):
        data_id_list = []
        data_text_list = []
        references = []
        with open(eval_path, "r") as json_file:
            json_list = list(json_file)
        for json_str in json_list:
            qs = json.loads(json_str)
            text, paraphrase, candidates = qs["sem_input"], qs["tgt"], qs["paras"]
            data_text_list.append((text, paraphrase))
            one_text_id_list = self.tokenize_text(text.strip())
            one_paraphrase_id_list = self.tokenize_label_text(paraphrase.strip())
            data_id_list.append((one_text_id_list, one_paraphrase_id_list))
            references.append(candidates)
        return data_id_list, data_text_list, references

    def load_json_data(self, data_path):
        #paraphrase_eval_json = {}
        data_id_list = []
        data_text_list = []
        if data_path.endswith(".json"):
            with open(data_path,"r") as f:
                data = json.load(f)
                for pair in data:
                    text = pair["text"].replace("<sos_s>","").replace("<eos_s>","")
                    paraphrase = pair["paraphrase"].replace("<sos_t>","").replace("<eos_t>","")
                    data_text_list.append((text, paraphrase))
                    one_text_id_list = self.tokenize_text(text.strip())
                    one_paraphrase_id_list = self.tokenize_label_text(paraphrase.strip())
                    data_id_list.append((one_text_id_list, one_paraphrase_id_list))
            return data_id_list, data_text_list


    def tokenize_text_vanilla(self, text):
        text = "paraphrase: "+text
        token_id_list = self.tokenizer(text)
        return token_id_list["input_ids"]

    def tokenize_label_vanilla(self, text):
        token_id_list = self.tokenizer(text)
        return token_id_list["input_ids"]

    def tokenize_text(self, text):
        token_id_list = self.tokenizer.convert_tokens_to_ids(self.tokenizer.tokenize(text))
        token_id_list = [self.src_sos_token_id] + token_id_list + [self.src_eos_token_id]  # pretraining format
        token_id_list = self.prefix_id + token_id_list
        return token_id_list

    def tokenize_label_text(self, text):
        token_id_list = self.tokenizer.convert_tokens_to_ids(self.tokenizer.tokenize(text))
        token_id_list = [self.tgt_sos_token_id] + token_id_list + [self.tgt_eos_token_id]
        return token_id_list

    def get_text_batches(self, batch_size, mode):
        #batch_size = self.cfg.batch_size
        batch_list = []
        if mode == "train":
            random.shuffle(self.train_data_text_list)
            all_data_list = self.train_data_text_list
        elif mode == "test":
            all_data_list = self.test_data_text_list
        else:
            raise Exception("Wrong Mode!!!")

        all_input_data_list, all_output_data_list = [], []
        for item in all_data_list:
            all_input_data_list.append( item[0])
            all_output_data_list.append(item[1])

        data_num = len(all_input_data_list)
        batch_num = int(data_num/batch_size) + 1

        for i in range(batch_num):
            start_idx, end_idx = i*batch_size, (i+1)*batch_size
            if start_idx > data_num - 1:
                break
            end_idx = min(end_idx, data_num - 1)
            one_input_batch_list, one_output_batch_list = [], []
            for idx in range(start_idx, end_idx):
                one_input_batch_list.append(all_input_data_list[idx])
                one_output_batch_list.append(all_output_data_list[idx])
            one_batch = [one_input_batch_list, one_output_batch_list]
            if len(one_batch[0]) == 0:
                pass
            else:
                batch_list.append(one_batch)
        print ("Number of {} batches is {}".format(mode, len(batch_list)))
        return batch_list

    def get_batches(self, batch_size, mode):
        batch_list = []
        if mode == "train":
            random.shuffle(self.train_data_id_list)
            all_data_list = self.train_data_id_list
        elif mode == "test":
            all_data_list = self.test_data_id_list
        else:
            raise Exception("Wrong Mode!!!")

        all_input_data_list, all_output_data_list = [], []

        for item in all_data_list:
            all_input_data_list.append( item[0])
            all_output_data_list.append(item[1])

        data_num = len(all_input_data_list)
        batch_num = int(data_num/batch_size) + 1

        for i in range(batch_num):
            start_idx, end_idx = i*batch_size, (i+1)*batch_size
            if start_idx > data_num - 1:
                break
            end_idx = min(end_idx, data_num - 1)
            one_input_batch_list, one_output_batch_list = [], []
            one_reference_batch_list = []
            for idx in range(start_idx, end_idx):
                one_input_batch_list.append(all_input_data_list[idx])
                one_output_batch_list.append(all_output_data_list[idx])
                if mode == "test":
                    one_reference_batch_list.append(self.paraphrase_references[idx])
            one_batch = [one_input_batch_list, one_output_batch_list]
            if mode == "test":
                one_batch.append(one_reference_batch_list)
            if len(one_batch[0]) == 0:
                pass
            else:
                batch_list.append(one_batch)
        print ("Number of {} batches is {}".format(mode, len(batch_list)))
        return batch_list

    def build_iterator(self, batch_size, mode):
        batch_list = self.get_batches(batch_size, mode)
        for i, batch in enumerate(batch_list):
            yield batch

    def pad_batch(self, batch_id_list):
        batch_id_list = [torch.LongTensor(item) for item in batch_id_list]
        batch_tensor = rnn.pad_sequence(batch_id_list, batch_first=True, padding_value=self.pad_token_id)
        batch_mask = torch.ones_like(batch_tensor)
        batch_mask = batch_mask.masked_fill(batch_tensor.eq(self.pad_token_id), 0.0).type(torch.FloatTensor)
        return batch_tensor, batch_mask

    def process_output(self, batch_tgt_id_list):
        batch_tgt_id_list = [torch.LongTensor(item) for item in batch_tgt_id_list]
        batch_tgt_tensor, _ = self.pad_batch(batch_tgt_id_list)
        # do the output target shift (one-off)
        batch_tgt_input_tensor = batch_tgt_tensor[:, :-1].clone()
        batch_tgt_output_tensor = batch_tgt_tensor[:, 1:].clone()
        return batch_tgt_input_tensor, batch_tgt_output_tensor

    def parse_batch_tensor(self, batch):
        batch_input_id_list, batch_output_id_list = batch
        batch_src_tensor, batch_src_mask = self.pad_batch(batch_input_id_list)
        batch_input, batch_labels = self.process_output(batch_output_id_list)
        batch_labels[batch_labels[:, :] == self.pad_token_id] = -100
        return batch_src_tensor, batch_src_mask, batch_input, batch_labels

    def parse_text_batch_tensor(self, batch):
        batch_input_text_list, batch_output_text_list = batch
        batch_tokens = self.tokenizer(batch_input_text_list, truncation=True, padding="longest", return_tensors="pt")
        return batch_tokens, batch_input_text_list, batch_output_text_list


