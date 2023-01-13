#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import numpy as np
import pandas as pd
from sklearn.manifold import TSNE

import plotly_express as px
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import plotly.figure_factory as ff


import botsim.modules.remediator.dashboard.dashboard_utils as dashboard_utils



def plot_test_performance(intent_to_errors):
    x = [[], []]
    y = []
    for intent_name in intent_to_errors:
        x[0].extend([intent_name.replace("_", " ")] * len(intent_to_errors[intent_name]))
        x[1].extend(["Success", "Intent Error", "NER Error", "Other Error"])
        raw_errors = list(intent_to_errors[intent_name])
        rates = [round(i / sum(raw_errors), 3) for i in raw_errors]
        y.extend(rates)
    fig = go.Figure()
    fig.add_bar(x=x, y=y)
    fig.update_layout(bargap=0.2,
                      bargroupgap=0.5,
                      yaxis=dict(
                          title="Rates",
                          titlefont_size=16,
                          tickfont_size=14,
                          dividercolor="red"
                      ),
                      )
    fig.update_layout(title_text="<i><b>Detailed performance for all intents of the selected test</b></i>")
    fig.add_shape(  # add a horizontal "target" line
        type="line", line_color="salmon", line_width=3, opacity=1, line_dash="dot",
        x0=0, x1=1, xref="paper", y0=0.5, y1=0.5, yref="y"
    )
    return fig


def plot_stacked_bar_chart(metrics, successful_tests):
    entries = {}
    latest_test_id = -1
    for d in metrics:
        intent_name, error_type = d["label"].split()[0], d["label"].split()[1]
        for test_id in d["data"]:
            count = d["data"][test_id]
            key = test_id.zfill(4) + "_" + intent_name + "_" + error_type
            if key not in entries:
                entries[key] = [-1, "", 0, 0, 0, 0, error_type]
            entries[key][0] = int(test_id)
            entries[key][1] = intent_name
            entries[key][2] = float(count) / 100
            entries[key][6] = error_type
            if int(test_id) > latest_test_id and int(test_id) in successful_tests:
                latest_test_id = int(test_id)

    latest_n = latest_test_id
    sorted_entries = dict(sorted(entries.items()))
    for k in entries:
        if entries[k][0] < latest_test_id - latest_n or int(entries[k][0]) not in successful_tests:
            sorted_entries.pop(k)
    data = np.array(list(sorted_entries.values()))
    perf_data = pd.DataFrame(
        dict(
            test_id=data[:, 0],
            intent_names=data[:, 1],
            rate=data[:, 2],
            success_error_type=data[:, 6],
            tested_intents=data[:, 1]
        )
    )

    fig = px.bar(perf_data, x="tested_intents", y="rate", facet_col="test_id", color="success_error_type")
    fig.for_each_annotation(lambda a: a.update(text=a.text.replace("success_error_type=", "")))
    fig.add_shape(  # add a horizontal "target" line
        type="line", line_color="salmon", line_width=3, opacity=1, line_dash="dot",
        x0=0, x1=1, xref="paper", y0=0.5, y1=0.5, yref="y"
    )
    return fig


def plot_tSNE(intents, database, test_id):
    embedding, labels = dashboard_utils.get_embedding(intents, database, str(test_id))
    tsne = TSNE(n_components=2, random_state=0)
    projections = tsne.fit_transform(embedding)
    fig = px.scatter( projections, x=0, y=1, color=labels, labels={"color": "intent"})
    fig.update_layout(yaxis_title=None)
    fig.update_layout(xaxis_title=None)
    fig.update_layout(title_text="<i><b>tSNE cluster visualisation of intent training utterances</b></i>")
    return fig


def plot_simulation_summary(intent_to_errors):
    metrics_labels = ["Success Rate", "Intent Error Rate", "NER Error Rate", "Other Error Rate"]
    data_labels = []
    distributions = []
    total_success, total_intent_error, total_ner_error, total_other_error = 0, 0, 0, 0
    for key in intent_to_errors:
        success, intent, ner, other = intent_to_errors[key]
        data_labels.append(key)
        distributions.append(success + intent + ner + other)
        total_success += success
        total_intent_error += intent
        total_ner_error += ner
        total_other_error += other

    # Create subplots: use "domain" type for Pie subplot
    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]])
    fig.add_trace(go.Pie(labels=data_labels, values=distributions, name="Intent Distribution", legendgroup="1"), 1, 1)
    fig.add_trace(
        go.Pie(labels=metrics_labels, values=[total_success, total_intent_error, total_ner_error, total_other_error],
               name="Performance", legendgroup="2"), 1, 2)
    fig.update_traces(hole=.45, hoverinfo="label+percent+name")
    fig.update_layout(
        annotations=[
            dict(text="Intent Data", x=0.175, y=0.54, font_size=15, showarrow=False),
            dict(text="Distribution", x=0.175, y=0.46, font_size=15, showarrow=False),
            dict(text="Success Metrics", x=0.85, y=0.5, font_size=15, showarrow=False)])
    fig.update_layout(title_text="<i><b>Intent dataset distribution and overall performance</b></i>",
                      legend_tracegroupgap=70)
    return fig


def plot_confusion_matrix(confusion_matrix, classes):
    ground_truth = classes
    prediction = classes
    # change each element of z to type string for annotations
    z_text = [[str(y) for y in x] for x in confusion_matrix]
    # set up figure
    fig = ff.create_annotated_heatmap(confusion_matrix,
                                      x=ground_truth, y=prediction, annotation_text=z_text, colorscale="Viridis")

    fig.add_annotation(dict(font=dict(color="black", size=14),
                            x=0.5,
                            y=-0.15,
                            showarrow=False,
                            text="Predicted intent",
                            xref="paper",
                            yref="paper"))

    # add custom yaxis title
    fig.add_annotation(dict(font=dict(color="black", size=14),
                            x=-0.35,
                            y=0.5,
                            showarrow=False,
                            text="Ground Truth intent",
                            textangle=-90,
                            xref="paper",
                            yref="paper"))
    # adjust margins to make room for yaxis title
    fig.update_layout(margin=dict(t=50, l=200))
    # add color bar
    fig["data"][0]["showscale"] = True
    return fig


def plot_intent_performance(intent, mode, overall_performance, detailed_performance):
    ner_errors = detailed_performance[mode][intent.replace("_eval", "")]["ner_errors"]
    intent_predictions = overall_performance[mode][intent.replace("_eval", "")]["intent_predictions"]

    prediction_labels, prediction_counts = [], []
    for p in intent_predictions:
        prediction_labels.append(p)
        prediction_counts.append(intent_predictions[p])

    entity_labels, entity_counts = [], []
    for ent in ner_errors:
        extraction_type = ner_errors[ent]["extraction_type"]
        if "pattern" in ner_errors[ent]:
            pattern = ner_errors[ent]["pattern"]
        if extraction_type == "UNK": continue
        if extraction_type == "regex":
            entity_labels.append(ner_errors[ent]["entity_name"] + " (" + pattern + ")")
        else:
            entity_labels.append(ner_errors[ent]["entity_name"] + " extracted via " + extraction_type)
        count = 0
        if "missed" in ner_errors[ent]:
            count += len(ner_errors[ent]["missed"])
        if "wrong" in ner_errors[ent]:
            count += len(ner_errors[ent]["wrong"])
        entity_counts.append(count)

    # Create subplots: use "domain" type for Pie subplot
    fig = make_subplots(rows=1, cols=2, specs=[[{"type": "domain"}, {"type": "domain"}]])
    fig.add_trace(go.Pie(labels=prediction_labels, values=prediction_counts,
                         name="Intent performance", legendgroup="1"), 1, 1)
    fig.add_trace(
        go.Pie(labels=entity_labels, values=entity_counts,
               name="NER performance", legendgroup="2"), 1, 2)

    fig.update_traces(hole=.45, hoverinfo="label+percent+name")

    fig.update_layout(
        annotations=[dict(text="Intent Model", x=0.175, y=0.54, font_size=15, showarrow=False),
                     dict(text="Performance", x=0.175, y=0.46, font_size=15, showarrow=False),
                     dict(text="NER performance", x=0.85, y=0.5, font_size=15, showarrow=False)])
    fig.update_layout(title_text="<i><b>Intent and NER performance breakdown for {}</b></i>".format(intent),
                      legend_tracegroupgap=70)
    return fig

