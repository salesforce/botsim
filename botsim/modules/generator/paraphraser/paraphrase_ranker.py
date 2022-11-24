#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from sentence_transformers import SentenceTransformer, util
import numpy as np


class ParaphraseRanker:
    """
    Rank and filter the paraphrases according to the semantic similarity measured by sentence transformer.
    Paraphrases with very high or very low semantic scores are discarded.
    """

    def __init__(self):
        self.sentence_transformer = SentenceTransformer("paraphrase-MiniLM-L6-v2")

    def _rank_by_sentence_transformer(self, paraphrases, lower=0.6, higher=0.95):
        """ Rank paraphrases according to sentence transformer cosine distance
        :param paraphrases: candidates
        :param lower: lower threshold on distance
        :param higher: higher threshold on distance
        :return:
        """
        cosine_ranked_paraphrases = []
        for paraphrase in paraphrases:
            para_embeddings = self.sentence_transformer.encode(
                paraphrase["cands"], convert_to_tensor=True)
            query_embedding = self.sentence_transformer.encode(
                [paraphrase["source"]], convert_to_tensor=True)
            bucket = {}
            ranked_paraphrases = {"source": paraphrase["source"], "cands": []}
            res = util.pytorch_cos_sim(query_embedding, para_embeddings)[0].sort(descending=True)
            para_list = np.array(paraphrase["cands"])[res.indices[res.values >= 0.0].cpu()].tolist()

            for item in zip(res.values.tolist(), para_list):
                score = item[0]
                if score >= higher or score <= lower:
                    continue
                key = str(score)[:4]
                if key not in bucket:
                    bucket[key] = item[1]
                else:
                    continue
                ranked_paraphrases["cands"].append(item[1])

            cosine_ranked_paraphrases.append(ranked_paraphrases)
        return cosine_ranked_paraphrases

    def rank(self, paraphrases):
        """ Rank paraphrases
        :param paraphrases: a dict mapping from original utterances ("source") to paraphrases ("cands")
        :return: ranked and filtered paraphrases
        """
        return self._rank_by_sentence_transformer(paraphrases)
