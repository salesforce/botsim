#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, shlex, subprocess, torch, random
import progressbar
import torch.nn as nn
from operator import itemgetter
from t5_model import T5Paraphraser
from transformers import T5Tokenizer
from dataloader import ParaphraseData
from botsim.botsim_utils.utils import compute_bleu_scores, seed_everything
# exp path: /export/home/pptod/data/pre-training_corpora/nlg
seed_everything(42)
class ParaphraserTrainer:
    def __init__(self, model_name, train_config, mode="train"):
        device = "cpu"
        assert model_name in set(["t5-small", "t5-base", "t5-large"])
        if torch.cuda.is_available():
            device = torch.device("cuda")
        train_data_path = ""
        dropout = 0.0
        self.number_of_gpus = train_config["number_of_gpu"]
        self.alpha = train_config["alpha"]
        if mode == "train":
            train_data_path = train_config["train_json_path"]
            test_data_path = train_config["dev_jsonl_path"]
            self.batch_size_per_gpu = train_config["batch_size_per_gpu"]
            self.optimizer_name = train_config["optimizer"]["optimizer_name"]
            self.learning_rate = train_config["optimizer"]["learning_rate"]
            self.adam_epsilon = train_config["optimizer"]["adam_epsilon"]
            self.warmup_steps = train_config["optimizer"]["warmup_steps"]
            self.max_grad_norm = train_config["optimizer"]["max_grad_norm"]
            self.weight_decay = train_config["optimizer"]["weight_decay"]
            self.gradient_accumulation_steps = train_config["optimizer"]["gradient_accumulation_steps"]
            self.num_train_epochs = train_config["num_train_epochs"]
            save_path = os.path.basename(os.path.normpath(train_config["save_path"]))
            model_size = model_name.split("-")[1]
            self.model_path = os.path.join("ckpt", model_size, save_path)
            tokenizer = T5Tokenizer.from_pretrained(train_config["pretrained_path"])
            self.paraphraser = T5Paraphraser(train_config["pretrained_path"], tokenizer,
                                             dropout=train_config["dropout"])
            dropout = train_config["dropout"]
        elif mode == "inference":
            self.model_path = train_config["model_path"]
            tokenizer = T5Tokenizer.from_pretrained(self.model_path)
            test_data_path = train_config["test_jsonl_path"]
            self.paraphraser = T5Paraphraser(self.model_path, tokenizer)
        else:
            raise ValueError("unsupported operation")

        self.data_loader = ParaphraseData(tokenizer, train_data_path, test_data_path, mode)
        self.paraphraser = T5Paraphraser(train_config["pretrained_path"], tokenizer,
                                         dropout=dropout)
        if train_config["number_of_gpu"] > 1:
            self.paraphraser = nn.DataParallel(self.paraphraser)  # multi-gpu training
        self.paraphraser = self.paraphraser.to(device)

        self.test_batch_size_per_gpu = train_config["test_batch_size_per_gpu"]
        max_test_num_batches = train_config["max_test_num_batches"]
        self.test_batch_list = self.data_loader.get_batches(self.test_batch_size_per_gpu, mode="test")
        if max_test_num_batches > 1:
            self.dev_batch_list = random.sample(self.test_batch_list, min(max_test_num_batches,
                                                                          len(self.test_batch_list)))
        self.test_batch_num_per_epoch = len(self.test_batch_list)

    def _prepare_optimizer(self, total_steps):
        self.scheduler = None
        no_decay = ["bias", "LayerNorm.weight"]
        optimizer_grouped_parameters = [
            {
                "params": [p for n, p in self.paraphraser.named_parameters() if not any(nd in n for nd in no_decay)],
                "weight_decay": self.weight_decay,
            },
            {"params": [p for n, p in self.paraphraser.named_parameters() if any(nd in n for nd in no_decay)],
             "weight_decay": 0.0},
        ]

        if self.optimizer_name == "adafactor":
            from transformers.optimization import Adafactor
            self.optimizer = Adafactor(
                optimizer_grouped_parameters,
                lr=self.learning_rate,  # ,
                eps=(1e-30, 1e-3),
                clip_threshold=1.0,
                decay_rate=-0.8,
                beta1=None,
                weight_decay=0.0,
                relative_step=False,
                scale_parameter=False,
                warmup_init=False
            )
        elif self.optimizer_name == "adam":
            print("Use AdamW Optimizer for Training.")
            from transformers.optimization import AdamW, get_linear_schedule_with_warmup
            self.optimizer = AdamW(optimizer_grouped_parameters, lr=self.learning_rate, eps=self.adam_epsilon)
            self.scheduler = get_linear_schedule_with_warmup(self.optimizer,
                                                             num_warmup_steps=self.warmup_steps,
                                                             num_training_steps=total_steps)
        else:
            raise Exception("Wrong Optimizer Name!!!")

    def _train_one_epoch(self,
                         train_batch_num_per_epoch,
                         train_iterator,
                         global_step):
        self.paraphraser.train()
        p = progressbar.ProgressBar(train_batch_num_per_epoch)
        p.start()
        p_train_idx = 0
        epoch_step, train_loss = 0, 0.
        for _, train_batch in enumerate(train_iterator):
            p.update(p_train_idx)
            p_train_idx += 1
            one_train_input_batch, one_train_output_batch = train_batch
            if len(one_train_input_batch) == 0 or len(one_train_output_batch) == 0: break
            train_batch_src_tensor, train_batch_src_mask, train_batch_input, train_batch_labels = \
                self.data_loader.parse_batch_tensor(train_batch)
            if torch.cuda.is_available():
                train_batch_src_tensor = train_batch_src_tensor.to(torch.device("cuda"))
                train_batch_src_mask = train_batch_src_mask.to(torch.device("cuda"))
                train_batch_input = train_batch_input.to(torch.device("cuda"))
                train_batch_labels = train_batch_labels.to(torch.device("cuda"))
            loss = self.paraphraser(train_batch_src_tensor, train_batch_src_mask, train_batch_input, train_batch_labels)
            loss = loss.mean()
            loss.backward()
            train_loss += loss.item()
            torch.nn.utils.clip_grad_norm_(self.paraphraser.parameters(), self.max_grad_norm)
            epoch_step += 1
            if (epoch_step + 1) % self.gradient_accumulation_steps == 0 or (
                    epoch_step + 1) == train_batch_num_per_epoch:
                self.optimizer.step()
                if self.optimizer_name == "adam":
                    self.scheduler.step()  # only update learning rate for adam optimizer
                self.optimizer.zero_grad()
                global_step += 1
        p.finish()
        train_loss = train_loss / train_batch_num_per_epoch
        return train_loss, global_step

    def _validation(self, beam_size=-1, device="cuda"):
        self.paraphraser.eval()
        top_n = 1
        with torch.no_grad():
            progress = progressbar.ProgressBar(self.test_batch_num_per_epoch)
            print("Number of evaluation batches is {}".format(self.test_batch_num_per_epoch))
            progress.start()
            test_pred_text_list, test_reference_text_list, test_input_text_list = [], [], []
            golds, preds, inputs, refs = [], [], [], []
            for p_dev_idx in range(self.test_batch_num_per_epoch):
                progress.update(p_dev_idx)
                one_test_batch = self.test_batch_list[p_dev_idx]
                for item in one_test_batch[-1]:  # one batch of sentences
                    refs.append(item)
                one_test_batch = one_test_batch[:-1]
                test_batch_src_tensor, test_batch_src_mask, test_batch_output, test_batch_labels = \
                    self.data_loader.parse_batch_tensor(one_test_batch)
                test_batch_src_tensor = test_batch_src_tensor.to(device)
                test_batch_src_mask = test_batch_src_mask.to(device)
                test_batch_output = test_batch_output.to(device)

                if self.number_of_gpus > 1:
                    top_n_test_prediction_text_list = self.paraphraser.module.batch_generate(
                        test_batch_src_tensor,
                        test_batch_src_mask,
                        top_n=top_n, beam_size=beam_size)
                else:
                    top_n_test_prediction_text_list = self.paraphraser.batch_generate(
                        test_batch_src_tensor,
                        test_batch_src_mask,
                        top_n=top_n, beam_size=beam_size)
                test_pred_text_list += [pred.split() for pred in top_n_test_prediction_text_list]
                preds += top_n_test_prediction_text_list
                if self.number_of_gpus > 1:
                    references = self.paraphraser.module.parse_batch_text(test_batch_output)
                    for ref in references:
                        for i in range(top_n):
                            test_reference_text_list += [[ref.split()]]

                    batch_inputs = self.paraphraser.module.parse_batch_text(
                        test_batch_src_tensor, start_token="<s>", end_token="</s>")
                    inputs += batch_inputs
                    for ref in batch_inputs:
                        for i in range(top_n):
                            test_input_text_list += [[ref.split()]]
                else:
                    references = self.paraphraser.parse_batch_text(test_batch_output)
                    for ref in references:
                        for i in range(top_n):
                            test_reference_text_list += [[ref.split()]]

                    batch_inputs = self.paraphraser.parse_batch_text(
                        test_batch_src_tensor, start_token="<sos_t>", end_token="<eos_t>")
                    inputs += batch_inputs
                    for ref in batch_inputs:
                        for i in range(top_n):
                            test_input_text_list += [[ref.split()]]
            progress.finish()
            assert len(test_pred_text_list) == len(test_reference_text_list)
            assert len(test_pred_text_list) == len(test_input_text_list)
            return inputs, preds, refs

    def train(self):
        overall_batch_size = self.number_of_gpus * self.batch_size_per_gpu * self.gradient_accumulation_steps
        total_steps = self.data_loader.train_num * self.num_train_epochs // overall_batch_size
        self._prepare_optimizer(total_steps)
        self.optimizer.zero_grad()

        global_step = 0
        best_dev_bleu = 0.

        for epoch in range(self.num_train_epochs):
            self.paraphraser.train()
            # --- training --- #
            print("Start training at epoch %d" % epoch)
            train_iterator = self.data_loader.build_iterator(batch_size=self.number_of_gpus * self.batch_size_per_gpu,
                                                             mode="train")
            train_batch_num_per_epoch = int(
                self.data_loader.train_num / (self.number_of_gpus * self.batch_size_per_gpu))
            train_loss, global_step = self._train_one_epoch(train_batch_num_per_epoch, train_iterator, global_step)
            train_loss = train_loss / train_batch_num_per_epoch
            print("At epoch {}, total update steps is {}, total training loss is {}".format(epoch, global_step,
                                                                                            train_loss))
            print("Start validation at global update step {}".format(global_step))
            inputs, preds, refs = self._validation()
            tgt_bleu, self_bleu, dev_bleu = compute_bleu_scores(inputs, preds, refs, alpha=self.alpha)
            model_save_path = self.model_path + "/bleus/epoch_{}_dev_bleu_{}_tgt_{}_self_{}".format(epoch,
                                                                                                    round(dev_bleu, 2),
                                                                                                    round(tgt_bleu, 2),
                                                                                                    round(self_bleu, 2))
            if not os.path.exists(model_save_path):
                subprocess.run(["mkdir", "-p", model_save_path], shell=False)

            if dev_bleu > best_dev_bleu:
                best_dev_bleu = dev_bleu
                model_save_path = self.model_path + "/epoch_{}_dev_bleu_{}_tgt_{}_self_{}".format(epoch,
                                                                                                  round(dev_bleu, 2),
                                                                                                  round(tgt_bleu, 2),
                                                                                                  round(self_bleu, 2))
                if not os.path.exists(model_save_path):
                    subprocess.run(["mkdir", "-p", model_save_path], shell=False)
                if self.number_of_gpus > 1:
                    self.paraphraser.module.save_model(model_save_path)
                else:
                    self.paraphraser.save_model(model_save_path)
                file_data = {}
                for fname in os.listdir(self.model_path):
                    if fname.startswith("epoch"):
                        file_data[fname] = os.stat(self.model_path + "/" + fname).st_mtime
                    else:
                        pass
                sorted_files = sorted(file_data.items(), key=itemgetter(1))
                max_save_num = 3
                if len(sorted_files) < max_save_num:
                    pass
                else:
                    delete = len(sorted_files) - max_save_num
                    for x in range(0, delete):
                        one_folder_name = self.model_path + "/" + sorted_files[x][0]
                        epoch_id = int(sorted_files[x][0].split("_")[1])
                        if epoch_id % 5 != 0 and epoch_id > 0:
                            folder_to_delete = shlex.quote(one_folder_name)
                            subprocess.run(["rm", "-r", folder_to_delete], shell=False)
            print(
                "current dev ibleu is {}, maximum dev ibleu is {}".format(round(dev_bleu, 4), round(best_dev_bleu, 4)))
            global_step += 1

    def inference(self, t5_model_type="base", beam_size=10, alpha=0.8):
        model_name = os.path.basename(os.path.normpath(self.model_path))
        inference_results_path = "inference_results/{}/{}/".format(t5_model_type, model_name)
        if not os.path.exists(inference_results_path):
            subprocess.run(["mkdir", "-p", inference_results_path], shell=False)
        ref_inputs, pred_output, refs = self._validation(beam_size=beam_size)
        tgt_bleu, self_bleu, dev_bleu = compute_bleu_scores(ref_inputs, pred_output, refs, alpha=alpha)
        if beam_size > 0:
            test_pred_save_path = inference_results_path + \
                                  "/predicted_labels_beam_search_" \
                                  "{}_tgt_bleu{}_self_bleu{}_ibleu_{}.txt".format(beam_size, tgt_bleu, self_bleu,
                                                                                  dev_bleu)
        else:
            test_pred_save_path = inference_results_path + \
                                  "/predicted_labels_nucleus_sampling_" \
                                  "tgt_bleu{}_self_bleu{}_ibleu_{}.txt".format(tgt_bleu, self_bleu, dev_bleu)
        with open(test_pred_save_path, "w", encoding="utf8") as prediction_file:
            for text in pred_output:
                prediction_file.writelines(text + "\n")
        test_reference_save_path = inference_results_path + "/reference_labels.txt"
        with open(test_reference_save_path, "w", encoding="utf8") as reference_file:
            for ref in refs:
                text = ";".join(ref)
                reference_file.writelines(text + "\n")
        inputs_save_path = inference_results_path + "/test_inputs.txt"
        with open(inputs_save_path, "w", encoding="utf8") as test_input_file:
            for text in ref_inputs:
                test_input_file.writelines(text[0] + "\n")
