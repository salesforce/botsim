#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from sys import platform

import numpy as np
import random, json
from sklearn.metrics import f1_score, precision_score, recall_score
import matplotlib as mpl
if platform == "darwin":
    mpl.use('tkagg')
else:
    mpl.use('agg')
import matplotlib.pyplot as plt


from botsim.botsim_utils.utils import seed_everything
seed_everything(42)

subset_indices = []
all_subsets = {}
intent_to_id = {}
id_to_intent = {}


def parse_data(data):
    intent_data = {}
    for i, episode in enumerate(data):
        goal = episode['goal'] + '_eval'
        if goal not in intent_data:
            intent_data[goal] = []
            subset_indices.append([])
        query = ' '.join(episode['intent_query'].split('')[2:]).strip()
        prediction = episode['intent_prediction']
        if prediction == 'No exact match':
            prediction = 'out_of_domain'
        if prediction not in intent_to_id:
            intent_to_id[prediction] = len(intent_to_id)
        intent_data[goal].append((intent_to_id[goal], intent_to_id[prediction], query, i))
    return intent_data


def bootstrap_with_replacement(all_intent_data, num_samples=1000, save_as='ci.png'):
    for intent in all_intent_data:
        create_subset(all_intent_data, intent, len(all_intent_data[intent]))

    f1 = []
    for k in range(num_samples):
        gold = []
        pred = []
        for i in range(len(all_intent_data)):
            g = [x[0] for x in all_subsets[i][0]]
            p = [x[1] for x in all_subsets[i][0]]
            sampled_g, sampled_p = [], []
            indices = []
            for j in range(len(g)):
                index = random.randint(0, len(g) - 1)
                sampled_p.append(p[index])
                sampled_g.append(g[index])
                indices.append(index)
            gold.extend(sampled_g)
            pred.extend(sampled_p)
        score = f1_score(gold, pred, average=None)
        if score.shape[0] == len(all_intent_data):
            f1.append(score)
        if k % 1000 == 0 and len(f1) > 0:
            print(k, len(indices), np.mean(f1, axis=0), np.std(f1, axis=0))

    # print(f1[:][0])
    if len(f1) == 0: return
    lower, upper = np.percentile([x[0] for x in f1], [2.5, 97.5])
    print(np.mean(f1, axis=0), np.std(f1, axis=0), upper, lower, (upper + lower) / 2, (upper - lower) / 2)

    fig, axs = plt.subplots(len(intent_to_id) // 2, 2, figsize=(15, 15), squeeze=False)

    for i in range(len(all_intent_data)):  # excluding OOD
        data = [x[i] for x in f1]
        # print(len(data))
        r, c = i // 2, i % 2
        current_plot = axs[r][c]

        current_plot.set_xlabel('F1 score', fontweight='bold')
        current_plot.set_ylabel('Frequency', fontweight='bold')
        current_plot.xaxis.label.set_size(10)
        current_plot.yaxis.label.set_size(10)
        height, bins, patches = current_plot.hist(data, density=True, bins=100)
        lower, upper = np.percentile(data, [2.5, 97.5])
        mean = round((lower + upper) / 2, 3)
        std_error = round((upper - lower) / 2, 3)
        current_plot.fill_betweenx([0, height.max()], lower, upper, color='g', alpha=0.1)
        df = 0.01
        f = np.arange(min(data), max(data), df)
        current_plot.set_title(
            list(all_intent_data.keys())[i] + ': ' + str(mean) + ' +- ' + str(std_error)
            + ', [' + str(round(lower, 3)) + ',' + str(round(upper, 3)) + ']' + ', ' + str(
                num_samples) + ' bootstrapped samples',
            fontweight="bold", size=10)  # Title
        current_plot.set_xticks(np.arange(min(data), max(data), step=0.01))
        current_plot.tick_params(axis='x', labelsize=10)
        current_plot.tick_params(axis='y', labelsize=10)

        current_plot.axvline((lower + upper) / 2, color='k', linestyle='dashed', linewidth=1)

        current_plot.axvline(lower, color='k', linestyle='dashed', linewidth=1)
        current_plot.axvline(upper, color='k', linestyle='dashed', linewidth=1)

    fig.tight_layout()
    plt.savefig(save_as)


def create_subset(all_intent_data, intent, num_elements):
    num_sets = len(all_intent_data[intent]) // num_elements
    random.shuffle(all_intent_data[intent])
    subsets = []
    indices = range(0, num_sets)

    # print(len(all_intent_data[intent]))
    for i in range(0, num_sets):
        s = all_intent_data[intent][i * num_elements:(i + 1) * num_elements]
        subsets.append([x for x in s])

    rest = []
    if len(subsets) * num_elements < len(all_intent_data[intent]):
        rest = all_intent_data[intent][len(subsets) * num_elements:]
        if len(rest) > num_elements // 2 and len(rest) > 0:
            subsets.append([x for x in rest])
            indices = range(0, num_sets + 1)
        else:
            subsets[-1].extend([x for x in rest])

    intent_index = intent_to_id[intent]
    subset_indices[intent_index] = indices
    all_subsets[intent_index] = subsets
    return subsets


def extract_episode(all_intent_data, ends, index):
    extracted_subsets = {}
    weights = []
    total = 0
    for i in range(len(all_intent_data)):
        # for j in range(frm, to):
        g = [x[0] for x in all_subsets[i][0][0:ends[i][index]]]
        p = [x[1] for x in all_subsets[i][0][0:ends[i][index]]]
        extracted_subsets[i] = {'gold': g, 'prediction': p}
        weights.append(len(g))
        total += len(g)
    weights = [x / total for x in weights]
    return extracted_subsets, weights


def bootstrap(extracted_subsets, weights, num_samples=1000000):
    f1 = []
    for k in range(num_samples):
        gold = []
        pred = []
        for i in range(len(extracted_subsets)):
            g = [x for x in extracted_subsets[i]['gold']]
            p = [x for x in extracted_subsets[i]['prediction']]
            sampled_g, sampled_p = [], []
            indices = []
            for j in range(len(g)):
                index = random.randint(0, len(g) - 1)
                sampled_p.append(p[index])
                sampled_g.append(g[index])
                indices.append(index)
            gold.extend(sampled_g)
            pred.extend(sampled_p)
        score = f1_score(gold, pred, average=None)
        if score.shape[0] == len(intent_to_id):
            f1.append(score)
        # if k % 1000 == 0:
        #     print(k, len(indices), np.mean(f1, axis=0), np.std(f1, axis=0))

    # print(f1[:][0])
    import math
    res = {}
    weighted_f1, uncertainty = 0, 0
    for i in range(len(intent_to_id) - 1):
        # data = [round(x[i],3) for x in f1]
        data = [x[i] for x in f1]
        r, c = i // 2, i % 2
        lower, upper = np.percentile(data, [2.5, 97.5])
        mean = (lower + upper) / 2
        std_error = (upper - lower) / 2
        res[id_to_intent[i]] = {}
        res[id_to_intent[i]]['mean'] = mean
        res[id_to_intent[i]]['error'] = std_error
        weighted_f1 += mean * weights[i]
        uncertainty += math.pow(std_error * weights[i], 2)
        # res.append(intent_names[i]+':'+str(mean)+'+-'+str(std_error))
    res['weighted_f1'] = weighted_f1
    res['uncertainty'] = math.sqrt(uncertainty)
    return res


def compute_confidence_interval(all_intent_data, num_splits=4, num_samples=1000):
    bootstrapped = {}
    for intent in all_intent_data:
        create_subset(all_intent_data, intent, len(all_intent_data[intent]))
    for i in range(len(all_intent_data)):
        random.shuffle(all_subsets[i])
    ends = {}

    for i in range(len(all_intent_data)):
        total = len(all_subsets[i][0])
        quarter = total // num_splits
        ends[i] = []
        for j in range(num_splits):
            ends[i].append(j * quarter + quarter)
        if num_splits * quarter < total:
            ends[i][-1] = total

    for j in range(num_splits):
        extracted_subsets, weights = extract_episode(all_intent_data, ends, j)
        res = bootstrap(extracted_subsets, weights, num_samples=num_samples)
        bootstrapped[j] = {
            'num_eval_utts': [id_to_intent[k] + ':' + str(ends[k][j]) for k in range(len(all_intent_data))]}
        bootstrapped[j]['confidence_intervals'] = res
        # print(j, res)
    return bootstrapped
    # import json
    #


def analyze_paraphrasing_performance(wrong_paraphrases, wrong_intent_utt):
    """
    Given the
    :return:
    """
    count = 0
    total = 0
    correct_utt_wrong_paraphrases = {}
    for utt in wrong_paraphrases:
        # print(utt)
        if utt not in wrong_intent_utt and utt[:-1] not in wrong_intent_utt:
            paraphrases = wrong_paraphrases[utt]['paraphrases']
            if len(paraphrases) > 0:
                count += 1
                total += len(paraphrases)
                # print(utt, paraphrases)
                correct_utt_wrong_paraphrases[utt] = paraphrases

    correct_utt_wrong_paraphrases['count'] = count
    correct_utt_wrong_paraphrases['total_wrong_utts'] = len(wrong_paraphrases)
    correct_utt_wrong_paraphrases['total_wrong_paras'] = total

    return correct_utt_wrong_paraphrases


def plot(all_intent_data, data, png):
    json_data = json.load(open(data, 'r'))

    num_splits = len(json_data)
    labels = []
    means = np.zeros((num_splits, len(all_intent_data)))
    errors = np.zeros((num_splits, len(all_intent_data)))

    width = 0.8
    fig, ax = plt.subplots(figsize=(10, 8))
    fig.tight_layout()

    for i in range(num_splits):
        labels.append(str(i + 1) + '/' + str(num_splits))
        for j in range(len(all_intent_data)):
            means[i][j] = json_data[str(i)]['confidence_intervals'][id_to_intent[j]]['mean']
            errors[i][j] = json_data[str(i)]['confidence_intervals'][id_to_intent[j]]['error']

    previous_means = None
    patch_handles = []
    for i in range(len(all_intent_data)):
        # print(means[:, i])
        if i == 0:
            bars = ax.bar(labels, means[:, i], width, yerr=errors[:, i], label=id_to_intent[i].replace('_eval', ''))
            patch_handles.append(bars)
        else:
            # print(previous_means)
            bars = ax.bar(labels, means[:, i], width, yerr=errors[:, i], bottom=previous_means,
                          label=id_to_intent[i].replace('_eval', ''))
            patch_handles.append(bars)
        if i == 0:
            previous_means = means[:, i]
        else:
            previous_means += means[:, i]

    ax.patch.set_facecolor('white')
    for i, rect in enumerate(ax.patches):
        # Find where everything is located
        height = rect.get_height()
        width = rect.get_width()

        x = rect.get_x()
        y = rect.get_y()
        r, c = i // num_splits, i % num_splits
        label_text = f'{height:.3f}'  # f'{height:.2f}' to format decimal values

        error = f'{errors[c, r]:.3f}'
        # ax.text(x, y, text)
        label_x = x + width / 2
        label_y = y + height / 2

        # plot only when height is greater than specified value
        if height > 0:
            ax.text(label_x, label_y, label_text + '\n± ' + error,
                    ha='center', va='center', fontsize=10, rotation=0,
                    weight='bold')
    # ax.set_yticks(range(0,10))
    ax.set_ylabel('F1 score mean and standard error', weight='bold')
    ax.set_xlabel('Fraction of evaluation utterances', weight='bold')
    ax.set_title('Intent F1 means and standard errors (95% confidence interval)', fontsize=14, weight='bold')
    # ax.legend()

    ax.xaxis.label.set_size(12)
    ax.yaxis.label.set_size(12)
    #

    box = ax.get_position()
    ax.set_position([box.x0, box.y0, box.width * 0.8, box.height])
    ax.set_yticks([])

    # Put a legend to the right of the current axis
    ax.legend(loc='center left', bbox_to_anchor=(1.0, 0.5), fontsize=7)
    plt.tick_params(axis='x', which='major', labelsize=12)
    plt.tick_params(axis='y', which='major', labelsize=12)
    plt.rcParams['axes.facecolor'] = 'white'

    plt.savefig(png, dpi=200)


def analyze_paraphrases(utt_test_id='50', paraphrase_test_id='52'):
    utt_data = json.load(open('bots/' + utt_test_id + '/results' + '/report.json'))
    paraphrase_data = json.load(open('bots/' + paraphrase_test_id + '/results' + '/report.json'))
    wrong_intent_utts = {}
    for intent in utt_data['intents']['eval']:
        # data = json.load(open('data/' + bot + '/' + intent + '/index_eval_20_20.json'))
        episodes = utt_data['intents']['eval'][intent][intent + '_eval']
        for e in episodes:
            if e['error'] == 'Intent Error':
                utt = ':'.join(e['dialog_history'][1].split(':')[1:]).strip()
                if intent not in wrong_intent_utts:
                    wrong_intent_utts[intent] = set()
                wrong_intent_utts[intent].add(utt)
                wrong_intent_utts[intent].add(utt[:-1])
    correct_utt_wrong_paraphrases = {}
    for intent in paraphrase_data['intents']['eval']:
        intent = intent.replace('_eval', '')
        wrong_paraphrases = paraphrase_data['intents']['eval'][intent]['intent_errors']
        # print(wrong_paraphrases, wrong_intent_utts[intent])
        correct_utt_wrong_paraphrases[intent + '_eval'] = \
            analyze_paraphrasing_performance(wrong_paraphrases, wrong_intent_utts[intent])
        print(intent, correct_utt_wrong_paraphrases[intent + '_eval']['count'],
              correct_utt_wrong_paraphrases[intent + '_eval']['total_wrong_utts'],
              correct_utt_wrong_paraphrases[intent + '_eval']['total_wrong_paras'])
    target_file = 'bots/' + paraphrase_test_id + '/results/correct_utt_wrong_paraphrases.json'
    with open(target_file, 'w') as f:
        json.dump(correct_utt_wrong_paraphrases, f, indent=2)


def confidence_analysis(utt_test_id='50', num_splits=10, num_samples=10000, ablation=False):
    # compute the confidence via bootstrap and plot the F1 scores and standard errors for each intent
    data = json.load(open('bots/' + utt_test_id + '/results' + '/report.json'))
    intent_to_id['out_of_domain'] = len(data['intents']['eval'])
    id_to_intent[len(data['intents']['eval'])] = 'out_of_domain'
    for i, intent in enumerate(data['intents']['eval']):
        intent_to_id[intent + '_eval'] = i
        id_to_intent[i] = intent + '_eval'

    all_intent_data = {}
    for intent in data['intents']['eval']:
        episodes = data['intents']['eval'][intent][intent + '_eval']
        all_intent_data.update(parse_data(episodes))
    # print('xxxx', all_intent_data)
    if ablation:
        bootstrapped = compute_confidence_interval(all_intent_data, num_splits, num_samples)
        json.dump(bootstrapped, open('bots/' + utt_test_id + '/results' + '/confidence_analysis.json', 'w'), indent=2)
        plot(all_intent_data, 'bots/' + utt_test_id + '/results' + '/confidence_analysis_ablation.json',
             'bots/' + utt_test_id + '/results' + '/confidence_analysis_ablation.png')

    bootstrap_with_replacement(all_intent_data, num_samples,
                               'bots/' + utt_test_id + '/results' + '/bootstrap_with_replacement.png')

# confidence_analysis()
