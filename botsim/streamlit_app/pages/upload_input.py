#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import os, json
import streamlit as st

from botsim.streamlit_app.backend import parse_metadata
from botsim.botsim_utils.utils import dump_s3_file, file_exists, S3_BUCKET_NAME



def app(database=None):
    st.markdown("")
    settings = {}
    with st.sidebar:
        row0_1, row0_spacer1, row0_2 = st.columns((6.0, .05, 4.3))
        with row0_1:
            bot_platform = st.selectbox("Bot Platform", ["Einstein Bot", "DialogFlow CX"])
        with row0_2:
            settings["test_name"] = st.text_input("Bot Name")
        settings["test_description"] = st.text_input("Test Description")
        settings["bot_type"] = bot_platform
        settings["bot_Id"] = ""
        settings["status"] = "new"
        # st.sidebar.info(
        #     "Due to security and privacy reasons, the demo does not accept any uploads, thus users cannot "
        #     "try the demo on their own bots yet. We will open-source the fully functional app after "
        #     " these issues are cleared. For this demo, users can try the dashboard and dialog path generation"
        #     " with the provided simulation data.")

    latest_bot_id, latest_stage = database.get_last_db_row()
    config = dict(database.get_one_bot_test_instance(latest_bot_id))
    settings = database.db_record_to_setting(config)

    st.subheader("BotSIM inputs")

    latest_bot_id, latest_stage = database.get_last_db_row()
    bot = dict(database.get_one_bot_test_instance(latest_bot_id))
    dialog_act_maps = "data/bots/{}/{}/conf/dialog_act_map.json".format(bot["type"], latest_bot_id)
    dialog_act_maps_revised = "data/bots/{}/{}/conf/dialog_act_map.revised.json".format(bot["type"], latest_bot_id)
    ontology_revised = "data/bots/{}/{}/conf/ontology.revised.json".format(bot["type"], latest_bot_id)

    if config["type"] == "Einstein_Bot":
        latest_bot_id, latest_stage = database.get_last_db_row()
        if latest_stage != "s02_inputs_completed":
            st.markdown("**Dialog Simulation with Einstein BotBuilder**")
            st.markdown(
                "As inputs, please retrieve the following metadata from Salesforce workbench and "
                "upload them to BotSIM:")
            row0_spacer2, row0_2 = st.columns((0.1, 8.5))
            with row0_2:
                with st.expander("- botversions consisting of conversation flow, action, message definition"):
                    st.code("""
                       <?xml version="1.0" encoding="UTF-8"?>
                   <Package xmlns="http://soap.sforce.com/2006/04/metadata">
                       <types>
                           <members>TemplateBotSIM150</members>
                           <name>Bot</name>
                       </types>
                       <version>51.0</version>
                   </Package>
                       """)
            row0_spacer2, row0_2 = st.columns((0.1, 8.5))
            with row0_2:
                with st.expander("- MIUtterances consisting of intent training utterances"):
                    st.code("""
                   <?xml version="1.0" encoding="UTF-8"?>
            <Package xmlns="http://soap.sforce.com/2006/04/metadata">
                <types>
                    <members>TemplateBotSIM_intent_sets</members>
                    <name>MlDomain</name>
                </types>
                <version>51.0</version>
            </Package>""")
            row0_1, row0_spacer2, row0_2 = st.columns((10.5, 0.1, 10.5))
            with row0_1:
                if not file_exists(S3_BUCKET_NAME, "data/bots/{}/{}/bots/metadata.bot".format(bot["type"], bot["id"])):
                    metadata = st.file_uploader("Please upload bot design metadata (botversions)")
                    if metadata:
                        str_rep = metadata.getvalue().decode("utf-8")
                        if "<botVersions>" not in str_rep:
                            st.error("No <botVersions> found. Please upload a valid botversions metadata")
                            return
                    latest_bot_id, latest_stage = database.get_last_db_row()

                    if metadata is not None and latest_stage == "config" and "<botVersions>" in str_rep:
                        target = "data/bots/{}/{}/bots/metadata.bot".format(bot["type"], bot["id"])
                        if os.environ.get("STORAGE") == "S3":
                            dump_s3_file(target, metadata.getvalue())
                        else:
                            open(target, "wb").write(metadata.getvalue())
                        database.update_stage("s01_bot_design_metadata", latest_bot_id)
                else:
                    st.success("botversion metadata has already been uploaded.")
                    database.update_stage("s01_bot_design_metadata", latest_bot_id)
            latest_bot_id, latest_stage = database.get_last_db_row()
            with row0_2:
                if file_exists(S3_BUCKET_NAME, "data/bots/{}/{}/bots/metadata.bot".format(bot["type"], bot["id"])) and \
                        latest_stage == "s01_bot_design_metadata":
                    intent_training_utterances = st.file_uploader("Please upload MIUtterance metadata")
                    if intent_training_utterances:
                        str_rep = intent_training_utterances.getvalue().decode("utf-8")
                        if "<mlIntents>" not in str_rep:
                            st.error("No <mlIntents> found. Please upload a valid MIUtterance metadata")
                            return
                    latest_bot_id, latest_stage = database.get_last_db_row()
                    if intent_training_utterances is not None and latest_stage == "s01_bot_design_metadata" \
                            and "<mlIntents>" in str_rep:
                        target = "data/bots/{}/{}".format(bot["type"], str(latest_bot_id)) + "/goals_dir/"
                        if os.environ.get("STORAGE") == "S3":
                            dump_s3_file(target + intent_training_utterances.name.split("/")[-1],
                                         intent_training_utterances.getvalue())
                        else:
                            open(target + intent_training_utterances.name.split("/")[-1], "wb").write(
                                intent_training_utterances.getvalue())
                        database.update_stage("s02_inputs_completed", latest_bot_id)
                elif latest_stage == "s02_inputs_completed":
                    st.success("mlDomain metadata (intent utterances) has already been uploaded.")

        settings["bot_versions"] = "1"  # st.

        # if intent_training_utterances is not None and metadata is not None:
        latest_bot_id, latest_stage = database.get_last_db_row()

        if latest_stage == "s03_human_in_the_loop_revision":
            row0_1, row0_spacer2, row0_2 = st.columns((10.5, 0.1, 10.5))
            with row0_1:
                st.success("Dialog act map and ontology revised, navigate to dialog generation & simulation")
        elif latest_stage == "s02_inputs_completed":
            if not file_exists(S3_BUCKET_NAME, dialog_act_maps):
                parse_metadata(bot)
            st.markdown("**BotSIM has inferred a set of dialog acts from your bot and "
                        "organized them into the following configuration files"
                        "  for conducting automatic dialog user simulation**")
            st.markdown(
                " - **'Dialog act maps'** to serve as the natural language "
                "understanding (NLU) module for BotSIM by mapping "
                "bot messages to dialog acts")
            st.markdown(" - **'Ontology'** to store the entities and their values")
            st.markdown(
                "Please revise the NLU to ensure the following dialog act maps are "
                "correct:**dialog_success_message, intent_success_message** as they "
                "are the golden labels  indicating a successful dialog and a "
                "correct intent classification")
            revised_dialog_act_maps = st.file_uploader("Please upload the revised dialog act map")
            if revised_dialog_act_maps is not None:
                #dump_s3_file(dialog_act_maps_revised, )
                if os.environ.get("STORAGE") == "S3":
                    dump_s3_file(dialog_act_maps_revised, revised_dialog_act_maps)
                else:
                    dialog_act_map = json.load(revised_dialog_act_maps)
                    with open(dialog_act_maps_revised, "w") as target:
                        json.dump(dialog_act_map, target, indent=2)

            if file_exists(S3_BUCKET_NAME, dialog_act_maps_revised) and not file_exists(S3_BUCKET_NAME, ontology_revised):
                st.markdown("Please revise the Ontology to include real values of the entities.")
                revised_ontology = st.file_uploader("Please upload revised ontology")
                if revised_ontology is not None:
                    if os.environ.get("STORAGE") == "S3":
                        dump_s3_file(ontology_revised, revised_ontology)
                    else:
                        ontology = json.load(revised_ontology)
                        with open(ontology_revised, "w") as target:
                            json.dump(ontology, target, indent=2)
                    database.update_stage("s03_human_in_the_loop_revision", latest_bot_id)
            if file_exists(S3_BUCKET_NAME, ontology_revised):
                database.update_stage("s03_human_in_the_loop_revision", latest_bot_id)
    elif config["type"] == "DialogFlow_CX":
        latest_bot_id, latest_stage = database.get_last_db_row()
        if file_exists(S3_BUCKET_NAME, dialog_act_maps_revised) and file_exists(S3_BUCKET_NAME, ontology_revised):
            if latest_stage == "s02_inputs_completed":
                database.update_stage("s03_human_in_the_loop_revision", latest_bot_id)
            row0_1, row0_spacer2, row0_2 = st.columns((10.5, 0.1, 10.5))
            with row0_1:
                st.success("Dialog act map and ontology revised, navigate to dialog generation & simulation")
        elif not file_exists(S3_BUCKET_NAME, dialog_act_maps_revised):
            if not file_exists(S3_BUCKET_NAME, dialog_act_maps):
                parse_metadata(bot)
            st.markdown("**BotSIM has inferred a set of dialog acts from your bot and organized them "
                        "into the following"
                        " configuration files for conducting automatic dialog user simulation**")
            st.markdown(
                " - **'Dialog act maps'** to serve as the natural language understanding (NLU) "
                "module for BotSIM by mapping bot messages to dialog acts")
            st.markdown(" - **'Ontology'** to store the entities and their values")
            st.markdown(
                "Please revise the NLU to ensure the following dialog act maps are correct:"
                "**dialog_success_message, intent_success_message** as they are the golden "
                "labels  indicating a successful dialog and a correct intent classification")
            revised_dialog_act_map = st.file_uploader("Please upload the revised dialog act map")
            if revised_dialog_act_map is not None:

                # print(type(dialog_act_map))
                if os.environ.get("STORAGE") == "S3":
                    dump_s3_file(dialog_act_maps_revised, revised_dialog_act_map)
                else:
                    dialog_act_map = json.load(revised_dialog_act_map)
                    with open(dialog_act_maps_revised, "w") as target:
                        json.dump(dialog_act_map, target, indent=2)

            if os.environ.get("STORAGE") == "S3":
                if file_exists(S3_BUCKET_NAME, dialog_act_maps_revised) and not file_exists(S3_BUCKET_NAME, ontology_revised):
                    st.markdown("Please revise the ontology to include real values of the entities.")
                    revised_ontology = st.file_uploader("Please upload revised ontology")
                    if revised_ontology is not None:
                        dump_s3_file(ontology_revised, revised_ontology)
                    database.update_stage("s03_human_in_the_loop_revision", latest_bot_id)
                if file_exists(S3_BUCKET_NAME, ontology_revised):
                    database.update_stage("s03_human_in_the_loop_revision", latest_bot_id)
            else:
                if os.path.exists(dialog_act_maps_revised) and not os.path.exists(ontology_revised):
                    st.markdown("Please revise the ontology to include real values of the entities.")
                    revised_ontology = st.file_uploader("Please upload revised ontology")
                    if revised_ontology is not None:
                        dump_s3_file(ontology_revised, revised_ontology)
                        ontology = json.load(revised_ontology)
                        with open(ontology_revised, "w") as target:
                            json.dump(ontology, target, indent=2)
                    database.update_stage("s03_human_in_the_loop_revision", latest_bot_id)
                if os.path.exists(ontology_revised):
                    database.update_stage("s03_human_in_the_loop_revision", latest_bot_id)
