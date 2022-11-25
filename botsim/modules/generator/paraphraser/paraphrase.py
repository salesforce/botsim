#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json, os, random, string, torch

from transformers import (
    AutoTokenizer,
    AutoModelWithLMHead,
    PegasusForConditionalGeneration,
    PegasusTokenizer)

from botsim.botsim_utils.utils import seed_everything, download_google_drive_url
from botsim.modules.generator.paraphraser.paraphrase_ranker import ParaphraseRanker


seed_everything(42)

class Paraphraser:
    def __init__(self, batch_size=16,
                 max_length=128, num_return_sequences=[20, 20],
                 beam_size=30):
        self.batch_size = batch_size
        self.num_return_sequences = num_return_sequences
        self.beam_size = beam_size
        self.max_length = max_length
        self.ranker = ParaphraseRanker()

    def _post_process_t5_base_batch(self, sentences, outputs, model_index = 0):
        """
        Post process T5 generated paraphrases by removing duplicated paraphrases
        """
        paraphrases = []
        for i, sentence in enumerate(sentences):
            utterance_paraphrases = {"source": sentence, "cands": set()}
            uniq_paraphrases = set()
            for j in range(self.num_return_sequences[model_index]):
                para = outputs[i * self.num_return_sequences[model_index] + j]
                lower_case_no_punc_para = para.lower().translate(str.maketrans(dict.fromkeys(string.punctuation)))
                lower_case_no_punc_utt = sentence.lower().translate(str.maketrans(dict.fromkeys(string.punctuation)))
                if lower_case_no_punc_para != lower_case_no_punc_utt and lower_case_no_punc_para not in uniq_paraphrases:
                    utterance_paraphrases["cands"].add(para)
                    uniq_paraphrases.add(lower_case_no_punc_para)
            utterance_paraphrases["cands"] = list(utterance_paraphrases["cands"])
            paraphrases.append(utterance_paraphrases)
        return paraphrases

    def _paraphrase_t5_batch(self, sentences, tokenizer, model):
        batch_input_ids = []
        max_len = 0
        for sentence in sentences:
            input_ids = tokenizer.encode("paraphrase: " + sentence + " </s>",
                                         return_tensors="pt", add_special_tokens=True)
            batch_input_ids.append(input_ids)
            if input_ids.size()[1] > max_len:
                max_len = input_ids.size()[1]
        for i, batch_input_id in enumerate(batch_input_ids):
            input_ids = torch.nn.functional.pad(batch_input_id,
                                                pad=(0, max_len - batch_input_id.size()[1]),
                                                mode="constant", value=0)
            batch_input_ids[i] = input_ids
        generated_ids_beam_search = model.generate(input_ids=torch.cat(batch_input_ids, 0),
                                                   num_return_sequences=self.num_return_sequences[0],
                                                   max_length=self.max_length,
                                                   num_beams=self.beam_size,
                                                   no_repeat_ngram_size=2,
                                                   repetition_penalty=3.5, length_penalty=1.0).reshape(
            self.num_return_sequences[0] * len(sentences), -1)
        outputs = []
        outputs.extend([tokenizer.decode(g, skip_special_tokens=True,
                                         clean_up_tokenization_spaces=True) for g in generated_ids_beam_search])
        paraphrases = self._post_process_t5_base_batch(sentences, outputs, 0)
        return paraphrases

    @staticmethod
    def _curate_batches(sentences, batch_size):
        i = 0
        batched_sentences = []
        while i <= int(len(sentences) / batch_size):
            end = (i + 1) * batch_size if (i + 1) * batch_size < len(sentences) else len(sentences)
            batch_sentences = sentences[i * batch_size: end]
            if len(batch_sentences) > 0:
                batched_sentences.append(batch_sentences)
            i += 1
        return batched_sentences

    def _paraphrase_t5(self, sentences):
        i = 0
        paraphrases = []
        tokenizer = AutoTokenizer.from_pretrained("t5-base")
        if not os.path.exists("./t5_paraphraser/pytorch_model.bin") and self.num_return_sequences[0] > 0:
            # download the model check point
            url = "https://storage.googleapis.com/sfr-botsim-research/epoch_88_dev_bleu_7.09_tgt_31.81_self_29.99/pytorch_model.bin"
            download_google_drive_url(url, "t5_paraphraser", "pytorch_model.bin")
        else:
            return paraphrases
        model = AutoModelWithLMHead.from_pretrained("./t5_paraphraser")

        while i <= int(len(sentences) / self.batch_size):
            end = (i + 1) * self.batch_size if \
                (i + 1) * self.batch_size < len(sentences) else \
                len(sentences)
            batch_sentences = sentences[i * self.batch_size: end]
            if len(batch_sentences) > 0:
                paraphrases.extend(self._paraphrase_t5_batch(batch_sentences, tokenizer, model))
            i += 1
        return paraphrases

    def _remove_duplicate_para(self, sentence, outputs, batch_index):
        utterance_paraphrases = {"source": sentence, "cands": set()}
        uniq_paraphrases = set()
        for j in range(self.num_return_sequences[1]):
            para = outputs[batch_index * self.num_return_sequences[1] + j]
            lower_case_no_punc_para = para.lower().translate(str.maketrans(dict.fromkeys(string.punctuation)))
            lower_case_no_punc_utt = sentence.lower().translate(str.maketrans(dict.fromkeys(string.punctuation)))
            if lower_case_no_punc_para != lower_case_no_punc_utt and lower_case_no_punc_para not in uniq_paraphrases:
                utterance_paraphrases["cands"].add(para)
                uniq_paraphrases.add(lower_case_no_punc_para)
        utterance_paraphrases["cands"] = list(utterance_paraphrases["cands"])
        return utterance_paraphrases

    def _paraphrase_pegasus(self, sentences):
        tokenizer = PegasusTokenizer.from_pretrained("tuner007/pegasus_paraphrase")
        model = PegasusForConditionalGeneration.from_pretrained(
            "tuner007/pegasus_paraphrase").to("cuda" if torch.cuda.is_available() else "cpu")
        paraphrases = []
        # https://discuss.huggingface.co/t/out-of-index-error-when-using-pre-trained-pegasus-model/5196
        # using max_length > 60 in generate will cause the error "IndexError:
        # index out of range in self" in embedding
        for batch in self._curate_batches(sentences, self.batch_size):
            batch_tokens = tokenizer(batch, truncation=True,
                                     padding="longest", max_length=self.max_length,
                                     return_tensors="pt").to("cuda" if torch.cuda.is_available() else "cpu")
            translated = model.generate(**batch_tokens, max_length=60,
                                        num_beams=self.beam_size,
                                        num_return_sequences=self.num_return_sequences[1],
                                        temperature=1.5)
            outputs = tokenizer.batch_decode(translated, skip_special_tokens=True)
            for i, sentence in enumerate(batch):
                paraphrases.append(self._remove_duplicate_para(sentence, outputs, i))
        return paraphrases

    def paraphrase(self, intent_train_utt, intent_name, number_utterances=-1):
        """
        apply ensemble of paraphrasing models 0 for t5, 1 for pegasus
        The pooled paraphrases will be ranked by the paraphrase ranker
        :param intent_train_utt: a dict of dialog/intent name to list of original  utterances
        :param intent_name: intent/dialog to be applied
        :param number_utterances: number of intent utterances for paraphrasing
        :return:
        """
        sentences = intent_train_utt[intent_name]
        if isinstance(number_utterances, int) and number_utterances > 0:
            sentences = random.sample(sentences, min(number_utterances, len(sentences)))
        paraphrases, paraphrases_pegasus = [], []
        if self.num_return_sequences[0] > 0:
            paraphrases = self._paraphrase_t5(sentences)
            if self.num_return_sequences[1] == 0:
                return paraphrases
        if self.num_return_sequences[1] > 0:
            paraphrases_pegasus = self._paraphrase_pegasus(sentences)
            if self.num_return_sequences[0] == 0:
                return paraphrases_pegasus
        return self.rank_paraphrases(self.combine_paraphrases(paraphrases_pegasus, paraphrases))

    def rank_paraphrases(self, paraphrases):
        """ Rank the paraphrase candidates
        :param paraphrases: pooled candidate
        :return:
        """
        return self.ranker.rank(paraphrases)

    @staticmethod
    def combine_paraphrases(*args):
        """
        Pooling all paraphrases generated from the ensemble of paraphrasing models
        :param args: multiple lists of candidates to be combined
        :return:
        """
        combined_paraphrases = []
        for i, sent in enumerate(args[0]):
            source = sent["source"]
            for k in range(1, len(args)):
                if len(args[k]) > 0:
                    sent["cands"].extend(args[k][i]["cands"])
            items = {"source": source, "cands": list(set(sent["cands"]))}
            combined_paraphrases.append(items)
        return combined_paraphrases

    @staticmethod
    def post_process_paraphrases(paraphrases):
        """
        post process paraphrases to remove wrong paraphrases according to some rules
        e.g., cannot paraphrase "I" into "you", etc
        :param paraphrases: original paraphrase list
        :return:
        """
        for sent in paraphrases:
            source = sent["source"]
            wrong_pairs = {"i": "you", "you": "i", "my": "your", "your": "my"}
            items = source.lower().split()
            to_check_src = []
            for pair in items:
                if pair in wrong_pairs:
                    to_check_src.append(pair)
            if len(to_check_src) == 1:
                cands = sent["cands"]
                new_cands = []
                for cand in cands:
                    items = cand.lower().split()
                    to_check = []
                    for pair in items:
                        if pair in wrong_pairs:
                            to_check.append(pair)
                    if len(to_check) == 1:
                        if to_check[0] == wrong_pairs[to_check_src[0]]:
                            continue
                    new_cands.append(cand)
                sent["cands"] = new_cands
        return paraphrases

    def paraphrase_main(self, intent_train_utts, intent_name):
        """
        tester function
        :param intent_train_utts: original intent utterances in json file
        :param intent_name: intent/dialog name
        :return:
        """
        with open(intent_train_utts, "r") as fin:
            sentences = json.load(fin)

        paraphrases = self.post_process_paraphrases(
            self._paraphrase_t5(sentences[intent_name]))

        with open("paraphrases_t5_base_" + intent_name + ".json", "w") as json_file:
            json.dump(paraphrases, json_file, indent=2)

        paraphrases_pegasus = self.post_process_paraphrases(
            self._paraphrase_pegasus(sentences[intent_name]))

        with open("paraphrases_pegasus_" + intent_name + ".json", "w") as json_file:
            json.dump(paraphrases_pegasus, json_file, indent=2)

        combined_paraphrases = self.combine_paraphrases(paraphrases, paraphrases_pegasus)
        with open("paraphrases_pegasus_t5_base_" + intent_name + ".json", "w") as json_file:
            json.dump(combined_paraphrases, json_file, indent=2)

        ranked_paraphrases = self.rank_paraphrases(combined_paraphrases)
        with open("paraphrases_pegasus_t5_base_" + intent_name + ".ranked.json", "w") as json_file:
            json.dump(ranked_paraphrases, json_file, indent=2)
