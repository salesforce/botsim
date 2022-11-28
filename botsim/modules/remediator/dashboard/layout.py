#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import streamlit as st
import botsim.modules.remediator.dashboard.dashboard_utils as dashboard_utils
import botsim.modules.remediator.dashboard.plot as dashboard_plot
from streamlit_chat import message


def plot_dialog_performance_banner(overall_performance, F1_scores, selected_intent, mode):
    row2_spacer1, row2_1, row2_spacer2, row2_2, row2_spacer3, row2_3, \
    row2_spacer4, row2_4, row2_spacer5, row2_5, row2_spacer6, row2_6 = st.columns(
        (.8, 2.5, .4, 2.5, .4, 2.5, .4, 2.5, .4, 2.5, .4, 2.5))

    intent_performance = overall_performance[mode.lower()][selected_intent.replace("_eval", "")]
    row2_1.metric("#Sessions", str(sum(list(intent_performance["overall_performance"].values()))), "")
    if F1_scores[selected_intent] < 0.9:
        row2_2.metric("F1 score", str(F1_scores[selected_intent]), "", "inverse")
    else:
        row2_2.metric("F1 score", str(F1_scores[selected_intent]), "Good")
    if intent_performance["success_rate"] < 0.7:
        row2_3.metric("Goal-completion Rate", str(intent_performance["success_rate"]), "", "inverse")
    else:
        row2_3.metric("Goal-completion Rate", str(intent_performance["success_rate"]), "")
    if intent_performance["intent_error_rate"] > 0.5:
        row2_4.metric("Intent Error Rate", str(intent_performance["intent_error_rate"]), "", "inverse")
    else:
        row2_4.metric("Intent Error Rate", str(intent_performance["intent_error_rate"]), "")
    if intent_performance["NER_error_rate"] > 0.5:
        row2_5.metric("NER Error Rate", str(intent_performance["NER_error_rate"]), "", "inverse")
    else:
        row2_5.metric("NER Error Rate", str(intent_performance["NER_error_rate"]), "")
    row2_6.metric("Other Error Rate", str(intent_performance["other_error_rate"]), "")


def render_summary_reports(database, mode, test, dataset_info, overall_performance):
    row1_spacer1, row1_1, row1_spacer2 = st.columns((.2, 7.1, .2))
    with row1_1:
        st.header("Bot health reports 📊")
        st.markdown("The bot health reports comprises 1) a summary report of a simulation session "
                    "across all intents and 2) "
                    "intent/dialog-specific reports to show both the task-completion and NLU performance.")
    row2_spacer1, row2_1, row2_spacer2 = st.columns((.2, 7.1, .4))
    with row2_1:
        st.subheader("Performance summary for selected test (test_id={}):".format(test))

    row3_spacer1, row3_1, row3_spacer2, row3_2, row3_spacer3, row3_3, row3_spacer4, row3_4, row3_spacer5 = \
        st.columns((.8, 1.6, .2, 1.6, .2, 1.6, .2, 1.6, .2))
    with row3_1:
        str_num_intents = "🥅 ***" + str(len(dataset_info[mode.lower()])) + " Intents***"
        st.markdown(str_num_intents)
    with row3_2:
        entities = dashboard_utils.get_entities(database, str(test))
        num_entities = 0
        if "Pattern" in entities:
            num_entities = len(entities["Pattern"].keys())
        if "Value" in entities:
            num_entities += len(entities["Value"].keys())
        str_num_entities = "🏛️ ***" + str(num_entities) + " Entities***"
        st.markdown(str_num_entities)
    with row3_3:
        total_convs, success_convs, intent_to_errors = dashboard_utils.get_number_dialogs(overall_performance, mode)
        str_num_convs = "💬 ***" + str(total_convs) + " Simulated Dialogs***"
        st.markdown(str_num_convs)
    with row3_4:
        str_num_successes = "✔️ ***" + str(success_convs) + " Completed Dialogs***"
        st.markdown(str_num_successes)

    row4_spacer1, row4_1, row4_spacer2 = st.columns((.8, 6.6, .2))
    with row4_1:
        st.plotly_chart(dashboard_plot.plot_simulation_summary(intent_to_errors), use_container_width=True)
        st.plotly_chart(dashboard_plot.plot_test_performance(intent_to_errors), use_container_width=True)


def render_dialog_report(mode, selected_intent, F1_scores, overall_performance, detailed_performance):
    row1_spacer1, row1_1, row1_spacer2 = st.columns((.3, 7.1, .4))
    if not F1_scores:
        F1_scores = {selected_intent: 1.0}
    with row1_1:
        st.markdown("---")
        st.subheader("Performance report for selected dialog \"" + selected_intent + "\"")

    plot_dialog_performance_banner(overall_performance, F1_scores, selected_intent, mode)

    st.plotly_chart(
        dashboard_plot.plot_intent_performance(
            selected_intent, mode.lower(), overall_performance,
            detailed_performance),
        use_container_width=True)


def render_remediation(mode, selected_intent, F1_scores, overall_performance, detailed_performance):
    row1_spacer1, row1_1, row1_spacer2 = st.columns((.2, 7.1, .2))
    if not F1_scores:
        F1_scores = {selected_intent: 1.0}
    with row1_1:
        st.markdown("---")
        st.header("Remediation Suggestions for {} 🛠️".format(selected_intent))
        st.markdown("These suggestions are  meant to be used as guidelines rather than strictly followed. "
                    "They are provided to help bot users to focus their efforts on high-priority issues. "
                    "They can also be extended by BotSIM users to include domain expertise or bot-specific "
                    "information. ")

    plot_dialog_performance_banner(overall_performance, F1_scores, selected_intent, mode)

    row3_spacer1, row3_1, row3_spacer2 = st.columns((.2, 7.1, .2))
    with row3_1:
        st.subheader("Intent Model")

    chatlogs = detailed_performance[mode.lower()][selected_intent.replace("_eval", "")][selected_intent]  # list
    intent_errors = detailed_performance[mode.lower()][selected_intent.replace("_eval", "")]["intent_errors"]

    utt_to_wrong_intent = {}
    droplist_labels = []
    for utt in intent_errors:
        wrong_intent_to_paraphrases = {}
        wrong_intents = intent_errors[utt]["remediations"]["classified_intents"]
        confusions = intent_errors[utt]["remediations"]["num_confusions"]
        suggestion = intent_errors[utt]["remediations"]["suggestions"]
        total = 0
        for wrong_intent in wrong_intents:
            paraphrases = wrong_intents[wrong_intent]
            wrong_intent_to_paraphrases[wrong_intent] = paraphrases
            total += len(paraphrases)

        num_confusion = sum(list(confusions.values()))
        key = utt + " (" + str(num_confusion) + " out of " + str(total) + ")"
        droplist_labels.append(key)
        utt_to_wrong_intent[key] = {"intent_predictions": wrong_intent_to_paraphrases, "suggestions": suggestion}

    if len(droplist_labels) > 0:
        row4_spacer1, row4_1, row4_spacer2, row4_2, row4_spacer3 = st.columns((.4, 8.3, .4, .4, .2))
        with row4_1:
            st.markdown("For intent models, we show the wrongly predicted paraphrases intent queries "
                        "grouped by their corresponding original"
                        " training utterances (**sorted in descending order by number of errors**). "
                        "Detailed analysis can be found on the right hand side expander.")
        row5_spacer1, row5_1, row5_spacer2, row5_2, row5_spacer3 = st.columns((.4, 4.3, .4, 4.3, .2))
        with row5_1:
            utt_selected = st.selectbox("Which utterance do you want to investigate? "
                                        "(" + str(len(droplist_labels)) + " in total)",
                                        list(droplist_labels), key="utt")
        with row5_2:
            st.markdown("")
            st.markdown("")
            utt = st.expander(utt_selected)
            with utt:
                st.json(utt_to_wrong_intent[utt_selected])

        query_to_episode = dashboard_utils.get_wrong_paraphrase_episode_id(chatlogs)

        row5_spacer1, row_selector, row5_spacer3, row_log = st.columns((.35, 3.8, .4, 4.0))
        episode_list = []
        episode_to_history = {}
        for p in utt_to_wrong_intent[utt_selected]["intent_predictions"]:
            paras = utt_to_wrong_intent[utt_selected]["intent_predictions"][p]
            for para in paras:
                if para in query_to_episode:
                    episode_list.append(
                        query_to_episode[para]["episode"] + " ==> " + query_to_episode[para]["intent_prediction"])
                    episode_to_history[
                        query_to_episode[para]["episode"] + " ==> " + query_to_episode[para]["intent_prediction"]] = \
                        query_to_episode[para]["dialog_history"]
        with row_selector:
            episode = st.selectbox("Episodes with intent errors from the selected utterances/paraphrases", episode_list)
            history = episode_to_history[episode]
        with row_log:
            save_json = st.checkbox("Save paraphrases in JSON")
        row5_spacer1, row_selector, row5_spacer3 = st.columns((.3, 10.5, .2))

        with row_selector:
            for i in range(len(history)):
                line = history[i]
                if line.find("====") != -1:
                    continue
                line = ":".join(line.split(":")[1:])
                if i % 2 == 0:
                    message(line)
                else:
                    if i == 1:
                        line = line + " (Intent error)"
                    message(line, is_user=True)

        st.markdown("")
        st.markdown("")
        ner_errors = detailed_performance[mode.lower()][selected_intent.replace("_eval", "")]["ner_errors"]
        row6_spacer1, row6_1, row6_spacer2 = st.columns((.2, 7.1, .2))
        with row6_1:
            st.subheader("NER Model")
        if len(ner_errors) > 0:
            row7_spacer1, row7_1, row5_spacer2, row7_2, row7_spacer3 = st.columns((.3, 4.3, .4, 4.4, .2))
            with row7_1:
                st.markdown("NER errors for selected dialog " + selected_intent)
            with row7_2:
                ner_expander = st.expander("NER errors and remediation recommendations")
                with ner_expander:
                    st.json(ner_errors)


def render_analytics(database, test, cm_plot, recalls, precisions, F1_scores, intent_to_clusters, intent_to_supports,
                     all_intents):
    row1_spacer1, row1_1, row1_spacer2 = st.columns((.2, 7.1, .2))
    with row1_1:
        st.markdown("---")
        st.header("Conversation Analytics ⚙️")
        st.markdown("Analytical tools for helping users gain insights into their bots for "
                    "troubleshooting and improvement. "
                    "These tools include confusion matrix analysis, intent utterance tSNE clustering and "
                    "many more can be added in the layout.")

    row2_spacer1, row2_1, row2_spacer2 = st.columns((.4, 7.1, .4))
    with row2_1:
        if cm_plot:
            st.subheader("Intent model confusion matrix analysis")
            st.plotly_chart(cm_plot, use_container_width=True)
        else:
            st.success("No intent confusions found")
    row_cm_spacer1, row_cm_1, row_cm_spacer2, row_cm_2, row_cm_spacer3, row_cm_3, row_cm_spacer4 = st.columns(
        (.2, 1.8, .2, 0.8, .2, 0.8, .2))
    detailed_intent_performance = None
    with row_cm_1:
        if cm_plot:
            detailed_intent_performance = st.checkbox("See detailed intent model performance")
    if detailed_intent_performance:
        row_cm_spacer1, row_cm_1, row_cm_spacer2, row_cm_2, row_cm_spacer3, row_cm_3, row_cm_spacer4 = st.columns(
            (.2, 0.8, .2, 0.8, .2, 0.8, .2))
        with row_cm_1:
            sorted_by = st.selectbox("", ["Sorted by Recall", "Sorted by Precision", "Sorted by F1"], key="hi_lo")

            sorted_recall = dict(sorted(recalls.items(), key=lambda item: -item[1]))
            sorted_precision = dict(sorted(precisions.items(), key=lambda item: -item[1]))
            sorted_F1 = dict(sorted(F1_scores.items(), key=lambda item: -item[1]))
            table = []

            if sorted_by == "Sorted by Recall":
                for intent in sorted_recall:
                    precision, recall, F1_score = sorted_precision[intent], recalls[intent], F1_scores[intent]
                    table.append(
                        [intent, precision, recall, F1_score, intent_to_supports[intent], intent_to_clusters[intent]])
            elif sorted_by == "Sorted by Precision":
                for intent in sorted_precision:
                    precision, recall, F1_score = sorted_precision[intent], recalls[intent], F1_scores[intent]
                    table.append(
                        [intent, precision, recall, F1_score, intent_to_supports[intent], intent_to_clusters[intent]])
            else:
                for intent in sorted_F1:
                    precision, recall, F1_score = sorted_precision[intent], recalls[intent], F1_scores[intent]
                    table.append(
                        [intent, precision, recall, F1_score, intent_to_supports[intent], intent_to_clusters[intent]])

        row4_spacer1, row4_1, row4_2, row4_3, row4_4, row4_5, row4_6, row4_spacer2 = st.columns(
            (2.3, 1.5, 1.5, 1.5, 1.5, 1.5, 1.5, 0.5))
        with row4_1:
            st.markdown(" ‎")
        with row4_5:
            st.markdown("Number of simulation")
        with row4_2:
            st.markdown("Recall")
        with row4_3:
            st.markdown("Precision")
        with row4_4:
            st.markdown("F1")
        with row4_6:
            st.markdown("Cluster")

        for row in table:
            columns = st.columns((0.7, 1.7, 1.5, 1.5, 1.5, 1.6, 1.5, 1.5, 0.5))
            with columns[1]:
                st.markdown(row[0])
            for i in range(1, len(row)):
                with columns[i + 2]:
                    st.markdown(row[i])

    row5_spacer1, row5_1, row5_spacer2 = st.columns((.4, 7.1, .4))
    with row5_1:
        st.markdown("---")
        st.subheader("tSNE visualisation of intent training utterances")
        st.markdown("To gauge the intent training data quality,  "
                    "tSNE clustering is performed on the sentence transformer embeddings of the intent training "
                    "utterances. "
                    "Not only can  the clustering identify intents with significant overlap in training "
                    "data semantic space, "
                    "it can also potentially discover novel intents from production logs to aid dialog re-design.")
        st.plotly_chart(dashboard_plot.plot_tSNE(all_intents, database, test), use_container_width=True)
