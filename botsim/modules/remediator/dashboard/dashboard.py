#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os

import botsim.modules.remediator.dashboard.dashboard_utils as dashboard_utils
import botsim.modules.remediator.dashboard.plot as dashboard_plot
import botsim.modules.remediator.dashboard.layout as dashboard_layout

import streamlit as st

st.set_page_config(layout="wide")

class Dashboard:

    def __init__(self, database=None, test_id="169"):
        self.entities = dashboard_utils.get_entities(test_id)
        self.test_id = test_id
        self.dataset_info, self.overall_performance, self.detailed_performance = \
            dashboard_utils.get_report_performance(test_id)
        self.test_ids = []
        self.database = database
        for dir in os.listdir("data/bots/"):
            if os.path.exists("data/bots/" + dir + "/results/report.json"):
                self.test_ids.append(dir)
        self.test_ids = database.get_test_ids()
        if len(self.test_ids) == 0:
            raise Exception("No simulation results available.")

    def render(self):
        self.test_ids = []
        for dir in os.listdir("data/bots/"):
            if os.path.exists("data/bots/" + dir + "/results/report.json"):
                self.test_ids.append(dir)
        if len(self.test_ids) == 0:
            raise Exception("No simulation results available.")

        row1_spacer1, row1_1, row1_spacer2 = st.columns((.1, 3.2, .1))
        test_id = st.sidebar.selectbox("Choose Test ID 👇", self.test_ids)
        self.entities = dashboard_utils.get_entities(test_id)
        self.test_id = test_id
        self.dataset_info, self.overall_performance, self.detailed_performance = \
            dashboard_utils.get_report_performance(test_id)

        with row1_1:
            st.markdown(
                "One of the major applications of BotSIM is to perform end-to-end bot performance evaluation to "
                "understand not only NLU but also  task-completion metrics of an NLU bot. "
                "This dashboard presents a multi-granularity bot health reports together with remediation "
                "recommendations to help users evaluate, diagnose and troubleshoot/improve their bots.")

        mode = st.sidebar.selectbox("Choose Simulation Dataset 👇", ["Dev", "Eval"])
        options = set(
            st.sidebar.multiselect(
                "What would you like to do?",
                ["Check Summary Reports", "Check Detailed Reports",
                 "Investigate Dialog", "Conversational Analytics"])
        )
        selected_intent = ""
        if "Check Detailed Reports" in options:
            if mode == "Dev":
                selected_intent = st.sidebar.selectbox("Choose Dev Intents", list(self.dataset_info["dev"].keys()))
            else:
                selected_intent = \
                    st.sidebar.selectbox("Choose Eval Intents", list(self.dataset_info["eval"].keys()))

        if self.dataset_info is not None:
            mode = mode.lower()
            confusion_matrix, classes, recalls, precisions, F1_scores, intent_clusters, intent_supports = \
                dashboard_utils.parse_confusion_matrix(self.database, test_id, mode.lower())
            confusion_matrix_plot = dashboard_plot.plot_confusion_matrix(confusion_matrix, classes)

            if "Check Summary Reports" in options:
                dashboard_layout.render_summary_reports(self.database,
                                                        mode, test_id, self.dataset_info, self.overall_performance)
            if "Check Detailed Reports" in options and selected_intent != "":
                dashboard_layout.render_dialog_report(
                    mode, selected_intent,
                    F1_scores,
                    self.overall_performance,
                    self.detailed_performance)
            if "Investigate Dialog" in options and selected_intent != "":
                dashboard_layout.render_remediation(mode,
                                                    selected_intent,
                                                    F1_scores,
                                                    self.overall_performance,
                                                    self.detailed_performance)
            if "Conversational Analytics" in options:
                dashboard_layout.render_analytics(self.database, test_id,
                                                  confusion_matrix_plot,
                                                  recalls,
                                                  precisions,
                                                  F1_scores,
                                                  intent_clusters,
                                                  intent_supports,
                                                  list(self.dataset_info[mode.lower()].keys()))
