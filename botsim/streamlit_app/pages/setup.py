#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import json, requests

import streamlit as st


requests.packages.urllib3.disable_warnings(
    requests.packages.urllib3.exceptions.InsecureRequestWarning)


def check_unfinished_simulations(database):
    latest_bot_id, latest_stage = database.get_last_db_row()
    if latest_bot_id == -1:
        return False
    if latest_stage == "s05_goal_created" or latest_stage == "s04_paraphrases_generated":
        st.warning("You have an unfinished simulation session (id=" + str(latest_bot_id) + ")")
        row0_1, row0_spacer1, row0_2 = st.columns((4.0, .05, 4.3))
        with row0_1:
            discard_simulation = st.checkbox("Discard the simulation?")
        with row0_2:
            continue_simulation = st.checkbox("Continue the simulation?")
        if discard_simulation:
            database.delete_bot_test_instance(latest_bot_id)
        if continue_simulation:
            st.warning("Navigate to simulation page to resume the simulation.")
        return True
    return False


def app(database):
    # This serve as the setup page for BotSIM
    settings = {}
    with st.sidebar:
        # st.subheader("Simulation")
        row0_1, row0_spacer1, row0_2 = st.columns((6.0, .05, 4.3))
        with row0_1:
            bot_platform = st.selectbox("Bot Platform", ["Einstein Bot", "DialogFlow CX"])
            bot_platform = bot_platform.replace(" ", "_")
        with row0_2:
            settings["test_name"] = st.text_input("Bot Name")
        settings["test_description"] = st.text_input("Test Description")
        settings["bot_type"] = bot_platform
        settings["bot_Id"] = ""
        settings["status"] = "new"
    st.markdown("**Dialog Generation & Simulation Configuration**")

    if check_unfinished_simulations(database):
        return
    # row0_1, row0_spacer2, row0_2 = st.columns((5.5, .05, 5.5))
    row0_1, row0_spacer1, row0_2, row0_spacer2, row0_3, row0_spacer3, row0_4, row0_space4 = \
        st.columns((2.0, .1, 2.0, 0.1, 2.0, 0.1, 2.0, 0.1))
    with row0_1:
        settings["num_seed_utterances"] = st.number_input("No. of seed utterances", -1)
    with row0_2:
        settings["num_t5_paraphrases"] = st.number_input("No. of paraphrases", 16)
        settings["num_pegasus_paraphrases"] = settings["num_t5_paraphrases"]
    with row0_3:
        settings["num_simulations"] = st.number_input("No. of dialog simulations (per intent)", -1)
    with row0_4:
        settings["max_dialog_turns"] = st.number_input("Maximum No. of dialog turns", 10)

    row1_1, row1_spacer1, row1_2, row1_spacer2 = st.columns((3.5, .1, 3.5, 0.1))
    with row1_1:
        st.markdown("BotSIM uses APIs to perform dialog simulation by acting as a user. Users are required to "
                    "provide the API credentials (for Salesforce Einstein BotBuilder) or API tokens (Google DialogFlow)"
                    "in JSON format. Contact your admins regarding the tokens/credentials.")
    with row1_2:
        with st.expander("Upload bot API credentials (example below 👇)"):
            if bot_platform == "Einstein_Bot":
                st.code("""
                {
                    "org_Id":"00D8cxxxxxxxxxx",
                    "button_Id": "5738cxxxxxxxxxx",
                    "deployment_Id": "5728cxxxxxxxxxx",
                    "end_point": "https://xxx.salesforceliveagent.com/chat"
                }""")
            elif bot_platform == "DialogFlow_CX":
                st.code("""
                        {
                            "location_id": "us-central1",
                            "agent_id": "xxxxx-xxxx-xxxxx-xxxx",
                            "project_id": "xxx",
                            "cx_credential": "platforms/dialogflow_cx/cx.json"
                        }""")
        api_creds = st.file_uploader("")
        latest_bot_id, latest_stage = database.get_last_db_row()
        if api_creds is not None:
            api_tokens = json.load(api_creds)
            if bot_platform == "Einstein_Bot":
                assert "org_Id" in api_tokens
                assert "end_point" in api_tokens
                assert "button_Id" in api_tokens
                assert "deployment_Id" in api_tokens
            if bot_platform == "DialogFlow_CX":
                assert "location_id" in api_tokens
                assert "agent_id" in api_tokens
                assert "cx_credential" in api_tokens

            settings.update(api_tokens)
            settings["bot_version"] = "1"
            settings["dev_intents"] = []
            settings["eval_intents"] = []

            if latest_bot_id != -1:
                config = dict(database.get_one_bot_test_instance(latest_bot_id))
                if len(config["dev"]) != 0 or len(config["eval"]) != 0:
                    settings["status"] = "new"
                    bot_id = str(database.create_test_instance(settings))
                else:
                    bot_id = latest_bot_id
            else:
                settings["status"] = "new"
                bot_id = str(database.create_test_instance(settings))
            settings["bot_Id"] = str(bot_id)
            st.success("Setup finished. Navigate to next page for BotSIM inputs.")
