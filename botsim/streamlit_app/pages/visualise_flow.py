#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import streamlit as st
import pandas as pd
from streamlit_agraph import agraph, TripleStore, Config, Node, Edge

from botsim.modules.remediator.remediator_utils.dialog_graph import ConvGraph


def app(database=None):
    st.title("Conversation Flow")

    bot_platforms, dev_intents, eval_intents, all_intents = database.get_bot_platform()

    selected_bot_platform = st.sidebar.selectbox("Choose Bot Platform 👇", bot_platforms)
    if selected_bot_platform:
        data_records, dev_metrics, eval_metrics = database.retrieve_all_test_sessions(selected_bot_platform)

        test_id = st.sidebar.selectbox("Select Test ID 👇", list(database.get_test_ids(selected_bot_platform)))
        if not test_id:
            df_data_filtered = pd.DataFrame(data_records)
            test_id = list(df_data_filtered["id"])[0]
        config = dict(database.get_one_bot_test_instance(test_id))
        conv_graph = ConvGraph("data/bots/{}/{}/goals_dir/".format(config["type"], config["id"]))
        if len(conv_graph.flow_data) == 0 and len(conv_graph.page_data) == 0:
            return

        query_type = st.sidebar.selectbox("Query Type: ", conv_graph.query_types)
        config = Config(height=600, width=800,
                        nodeHighlightBehavior=True,
                        highlightColor="#F7A7A6", directed=True,
                        collapsible=True,
                        node={"labelProperty": "label"},
                        link={"labelProperty": "label", "renderLabel": True, },
                        maxZoom=10
                        )

        conv_graph.create_conv_graph(query_type)

        initial_dialog = st.sidebar.selectbox("Initial Dialog:",
                                              list(conv_graph.all_flows) + list(conv_graph.all_pages)).split(" ")[-1]
        initial_dialog = initial_dialog[initial_dialog.find("]") + 1:]

        source = st.sidebar.selectbox("Source:",
                                      list(conv_graph.all_flows) + list(conv_graph.all_pages)).split(" ")[-1]
        target = st.sidebar.selectbox("Target:",
                                      list(conv_graph.all_flows) + list(conv_graph.all_pages)).split(" ")[-1]
        via = st.sidebar.multiselect("Via",
                                     list(conv_graph.all_flows) + list(conv_graph.all_pages))

        show = st.sidebar.button("Show Filtered Flows")
        max_num_paths = st.sidebar.selectbox("Number of paths to show:",
                                             range(10, 50, 10))

        cycles = []

        for path in conv_graph.simple_cycles():
            cycles.append(path)

        if show:
            selected = TripleStore()
            selected_nodes = set()
            selected_edges = set()
            i = 0
            paths = []
            for path in conv_graph.all_simple_path(source, target):
                valid = False
                is_loop = False
                if len(via) == 0:
                    valid = True
                node_set = set()
                for edge in path:
                    node_set.add(edge[0])
                    node_set.add(edge[1])
                    if initial_dialog == edge[1]:
                        is_loop = True
                if (initial_dialog in node_set and initial_dialog != source) or is_loop:
                    if i > max_num_paths:
                        st.sidebar.warning(
                            "loop detected from {} to {}, {} paths produced".format(source, target, max_num_paths))
                        break
                i += 1
                for s in via:
                    if s.split(" ")[-1] in node_set or s.split(" ")[-1] in node_set:
                        valid = True
                if valid:
                    paths.append(path)
                    for edge in path:
                        selected.add_triple(edge[0], edge[2], edge[1])
                        shape = "circle"
                        if edge[0] == source:
                            shape = "star"
                        if "[Flow] " + edge[0] in conv_graph.all_flows:
                            selected_nodes.add(Node(edge[0], size=800, color="blue", symbolType=shape))
                        elif "[Page] " + edge[0] in conv_graph.all_pages:
                            selected_nodes.add(Node(edge[0], size=400, symbolType=shape))
                        else:
                            selected_nodes.add(Node(edge[0], size=200, symbolType="triangle", color="red"))

                        shape = "circle"
                        if edge[1] == target:
                            shape = "star"
                        if "[Flow] " + edge[1] in conv_graph.all_flows:
                            selected_nodes.add(Node(edge[1], size=800, color="blue", symbolType=shape))
                        elif "[Page] " + edge[1] in conv_graph.all_pages:
                            selected_nodes.add(Node(edge[1], size=400, symbolType=shape))
                        else:
                            selected_nodes.add(Node(edge[1], size=200, symbolType="triangle", color="red"))

                        edge_label = edge[2].replace("/flow", "").replace("/page", "").replace("page", "").replace(
                            "flow", "")
                        selected_edges.add(Edge(source=edge[0], target=edge[1], label=edge_label.strip("/")))

            row4_spacer1, row4_1, row4_spacer2, row4_2 = st.columns((.2, 20.1, .4, 10.1))
            path_json = {}
            for j, p in enumerate(paths):
                path = [p[0][0]]
                for e in p:
                    path.append(e[1])
                path_json[j + 1] = " > ".join(path)

            with row4_1:
                agraph(list(selected_nodes), list(selected_edges), config)
            with row4_2:
                st.info("Conversation paths (in JSON)")
                st.json(path_json)
        else:
            agraph(list(conv_graph.graph_nodes), list(conv_graph.graph_edges), config)

