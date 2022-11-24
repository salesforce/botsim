#
# Copyright (c) 2022, salesforce.com, inc.
#  All rights reserved.
#  SPDX-License-Identifier: BSD-3-Clause
#  For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause
#

# download
mkdir -p ../paraphraser/data/raw_data
target_dir=../paraphraser/data/raw_data
wget "https://storage.googleapis.com/paws/english/paws_wiki_labeled_final.tar.gz"
tar -xzf paws_wiki_labeled_final.tar.gz
rm paws_wiki_labeled_final.tar.gz
mv final $target_dir/paws_final
wget "https://storage.googleapis.com/paws/english/paws_wiki_labeled_swap.tar.gz"
tar -xzf paws_wiki_labeled_swap.tar.gz
mv swap $target_dir/paws_swap
rm paws_wiki_labeled_swap.tar.gz
wget "https://raw.githubusercontent.com/hetpandya/paraphrase-datasets-pretrained-models/main/datasets/tapaco/tapaco_paraphrases_dataset.csv"
mv tapaco_paraphrases_dataset.csv $target_dir/
# download train_mqr_paralex.tsv from https://drive.google.com/drive/folders/1VZ7BusNjbulG9xYlcbGmip5Pl-Gzo8HD
# follow the instruction in  https://github.com/google-research-datasets/paws#paws-qqp to generate PAWS-QQP dataset

wget https://tomho.sk/models/hrqvae/qqp_deduped.zip
unzip qqp_deduped.zip
mv qqp_deduped $target_dir
rm qqp_deduped.zip

wget https://tomho.sk/models/separator/data_paralex.zip
unzip data_paralex.zip
mv training-triples wikianswers* $target
rm data_paralex.zip

wget https://tomho.sk/models/hrqvae/data_mscoco.zip
mv mscoco* $target
rm data_mscoco.zip