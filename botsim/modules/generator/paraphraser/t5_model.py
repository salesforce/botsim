#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os
from torch import nn
from transformers import T5ForConditionalGeneration, T5Config
from botsim.botsim_utils.utils import seed_everything

seed_everything(42)

class T5Paraphraser(nn.Module):
    """ T5 paraphrasing model.
    The code is adapted from https://github.com/awslabs/pptod
    """
    def __init__(self, model_path, tokenizer, dropout=0.1):
        super().__init__()
        self.tokenizer = tokenizer
        self.pad_token_id, self.sos_token_id, self.eos_token_id = \
            self.tokenizer.convert_tokens_to_ids(["<_PAD_>", "<sos>","<eos>"])

        self.special_token_ids = set([self.pad_token_id, self.sos_token_id, self.eos_token_id])

        t5_config = T5Config.from_pretrained(model_path)
        t5_config.__dict__["dropout"] = dropout
        self.model = T5ForConditionalGeneration.from_pretrained(model_path, config=t5_config, resume_download=True)
        self.model.resize_token_embeddings(len(self.tokenizer))

        self.tgt_sos_token_id = self.tokenizer.convert_tokens_to_ids(["<s>"])[0]
        self.tgt_eos_token_id = self.tokenizer.convert_tokens_to_ids(["</s>"])[0]

    def forward(self, src_input, src_mask, tgt_input, tgt_output):
        src_mask = src_mask.type(src_input.type())
        outputs = self.model(input_ids=src_input, attention_mask=src_mask, decoder_input_ids=tgt_input,
                             labels=tgt_output)
        loss = outputs[0]
        return loss

    def parse_batch_text(self, batch_pred_ids, start_token="<s>", end_token="</s>", prefix="paraphrase:"):
        res_text_list = []
        for predicted_text in self.tokenizer.batch_decode(batch_pred_ids, skip_special_tokens=True):
            one_res_text = predicted_text.split(start_token)[-1].split(end_token)[0].replace(prefix,"").strip()
            final_res_list = []
            for token in one_res_text.split():
                if token == "<pad>":
                    continue
                else:
                    final_res_list.append(token)
            one_res_text = " ".join(final_res_list).strip()

            res_text_list.append(one_res_text)
        return res_text_list

    def batch_prediction(self, src_input, src_mask):
        outputs = self.model.generate(input_ids=src_input, attention_mask=src_mask,
                                      decoder_start_token_id=self.tgt_sos_token_id,
                                      pad_token_id=self.pad_token_id,
                                      eos_token_id=self.tgt_eos_token_id, max_length=64)
        return self.parse_batch_text(outputs)

    def batch_generate(self, src_input, src_mask, top_n=10, beam_size=10, temp=1.0):
        if beam_size > 0:
            translated = self.model.generate(input_ids=src_input, attention_mask=src_mask,
                                             decoder_start_token_id=self.tgt_sos_token_id,
                                             pad_token_id=self.pad_token_id,
                                             eos_token_id=self.tgt_eos_token_id,
                                             max_length=128, num_beams=beam_size,
                                             num_return_sequences=top_n, temperature=temp)
        else:
            translated = self.model.generate(input_ids=src_input, attention_mask=src_mask,
                                             decoder_start_token_id=self.tgt_sos_token_id,
                                             pad_token_id=self.pad_token_id,
                                             eos_token_id=self.tgt_eos_token_id,
                                             max_length=128, num_return_sequences=top_n,
                                             temperature=0.8,
                                             top_k=500, top_p=0.95, do_sample=True)

        return self.parse_batch_text(translated)

    def save_model(self, ckpt_save_path):
        if not os.path.exists(ckpt_save_path):
            os.mkdir(ckpt_save_path)
        self.model.save_pretrained(ckpt_save_path)
        self.tokenizer.save_pretrained(ckpt_save_path)
