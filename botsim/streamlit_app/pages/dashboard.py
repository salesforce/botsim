#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import streamlit as st
import pandas as pd
from botsim.modules.remediator.dashboard.dashboard_utils import (
    color_cell,
    get_bot_health_reports,
    parse_confusion_matrix)
from botsim.modules.remediator.dashboard.plot import (plot_stacked_bar_chart,
                                                      plot_confusion_matrix)


def app(database=None):
    row1_spacer1, row1_1, row1_spacer2 = st.columns((.1, 3.2, .1))
    with row1_1:
        st.markdown("One of the major applications of BotSIM is to perform end-to-end bot performance evaluation to "
                    "understand not only NLU but also  task-completion metrics of an NLU bot. "
                    "This dashboard presents a multi-granularity bot health reports together with remediation "
                    "recommendations to help users evaluate, diagnose and troubleshoot/improve their bots.")

    bot_platforms, dev_intents, eval_intents, all_intents = database.get_bot_platform()

    selected_bot_platform = st.sidebar.selectbox("Choose Bot Platform 👇", bot_platforms)
    mode = st.sidebar.selectbox("Choose Simulation Dataset 👇", ["Dev", "Eval"])

    data_records, dev_metrics, eval_metrics = database.retrieve_all_test_sessions(selected_bot_platform)

    row2_spacer1, row2_1, row2_spacer2 = st.columns((.2, 7.1, .2))
    with row2_1:
        see_data = st.expander("Performance overview over latest historical evaluations 👉")
        df_data_filtered = pd.DataFrame(data_records)
        df_data_filtered = df_data_filtered[df_data_filtered["mode"] == mode.lower()]
        df_data_filtered = df_data_filtered[df_data_filtered["status"] != "error"]
        df_data_filtered = df_data_filtered.drop(["cnt", "name", "version", "mode", "status", "turns",
                                                  "intent", "ner", "other", "success"], axis=1)
        df_data_filtered.rename(columns={"total": "total_episodes",
                                         "success_rate": "success_rate(%)",
                                         "intent_rate": "intent_error_rate(%)",
                                         "ner_rate": "NER_error_rate(%)",
                                         "other_rate": "other_error_rate(%)",
                                         "turn_avg": "average_turns",
                                         "id": "test_id"}, inplace=True)

        df_data_filtered["updated_at"] = df_data_filtered["updated_at"].astype("datetime64[s]")
        styles = [
            dict(selector="th", props=[("text-align", "center")])  # ,
        ]
        with see_data:
            st.dataframe(data=
                         df_data_filtered.
                         reset_index(drop=True).
                         style.applymap(color_cell, subset=["success_rate(%)"]).
                         set_table_styles(styles))

        if mode == "Dev":
            st.plotly_chart(plot_stacked_bar_chart(dev_metrics, set(df_data_filtered["test_id"])),
                            use_container_width=True)
        else:
            st.plotly_chart(plot_stacked_bar_chart(eval_metrics, set(df_data_filtered["test_id"])),
                            use_container_width=True)

    selected_test_id = st.sidebar.selectbox("Choose Test ID 👇", df_data_filtered["test_id"])
    options = set(st.sidebar.multiselect("What would you like to do?",
                                         ["Check Summary Reports", "Check Detailed Reports",
                                          "Investigate Dialog", "Conversational Analytics"]))

    selected_intent = ""
    if "Check Detailed Reports" in options:
        if mode == "Dev":
            selected_intent = st.sidebar.selectbox("Choose Dev Intents", dev_intents[selected_test_id])
        else:
            selected_intent = st.sidebar.selectbox("Choose Eval Intents", eval_intents[selected_test_id]).replace(
                "_eval", "")

    if mode == "Dev":
        render_page("dev", selected_test_id, selected_intent, options, all_intents, database)
    else:
        render_page("eval", selected_test_id, selected_intent, options, all_intents, database)


def render_page(mode, test, selected_intent, options, all_intents, database):
    dataset_info, overall_performance, detailed_performance = get_bot_health_reports(database, test)
    if dataset_info is not None:
        confusion_matrix, classes, recalls, precisions, F1_scores, intent_clusters, intent_supports = \
            parse_confusion_matrix(database, test, mode)
        confusion_matrix_plot = plot_confusion_matrix(confusion_matrix, classes)

        if "Check Summary Reports" in options:
            from botsim.modules.remediator.dashboard.layout import render_summary_reports
            render_summary_reports(database, mode, test, dataset_info, overall_performance)
        if "Check Detailed Reports" in options:
            from botsim.modules.remediator.dashboard.layout import render_dialog_report
            render_dialog_report(mode, selected_intent, F1_scores, overall_performance, detailed_performance)
        if "Investigate Dialog" in options:
            from botsim.modules.remediator.dashboard.layout import render_remediation
            if selected_intent == "":
                st.sidebar.error("'Check Dialog Reports' before investigation")
            else:
                render_remediation(mode, selected_intent, F1_scores, overall_performance, detailed_performance)
        if "Conversational Analytics" in options:
            from botsim.modules.remediator.dashboard.layout import render_analytics
            render_analytics(database, test, confusion_matrix_plot, recalls, precisions, F1_scores,
                             intent_clusters,
                             intent_supports,
                             all_intents)
