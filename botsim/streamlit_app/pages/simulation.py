#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import requests

import streamlit as st
from botsim.botsim_utils.utils import read_s3_json, S3_BUCKET_NAME

requests.packages.urllib3.disable_warnings(
    requests.packages.urllib3.exceptions.InsecureRequestWarning)

def app(database):
    remediation_url = "http://127.0.0.1:8887/remediation"
    generation_url = "http://127.0.0.1:8887/generation"
    simulation_url = "http://127.0.0.1:8887/simulation"
    st.markdown("**Dialog Generation & Simulation**")
    latest_bot_id, latest_stage = database.get_last_db_row()
    config = dict(database.get_one_bot_test_instance(latest_bot_id))
    settings = database.db_record_to_setting(config)
    if latest_stage == "s03_human_in_the_loop_revision":
        dialog_act_map = \
            read_s3_json(S3_BUCKET_NAME, "data/bots/{}/{}/conf/dialog_act_map.revised.json".format(config["type"], config["id"]))
        if settings["status"] == "paraphrasing":
            ongoing = st.expander("Dialog generation via paraphrasing in progress")
            with ongoing:
                st.json(config)
            halt = st.checkbox("Restart (refresh page to take effect)")
            if halt:
                database.update_status(latest_bot_id, "")
        else:
            all_intents = st.multiselect(
                "Choose intents for simulation",
                list(dialog_act_map["DIALOGS"].keys())
            )
            eval = st.checkbox("Simulation on held-out evaluation set")
            dev = st.checkbox("Simulation on dev set")
            # now ask users to choose the intents to test
            if dev:
                settings["dev_intents"] = list(all_intents)
            else:
                settings["dev_intents"] = []
            if eval:
                settings["eval_intents"] = [x + "_eval" for x in all_intents]
            else:
                settings["eval_intents"] = []
            settings["bot_Id"] = latest_bot_id
            if st.button("Start Dialog Generation and Simulation"):
                latest_bot_id, latest_stage = database.get_last_db_row()
                if latest_stage == "s03_human_in_the_loop_revision":
                    database.create_test_instance(settings)
                with st.spinner("Paraphrasing in progress"):
                    generation = requests.post(url=generation_url)
                with st.spinner("Dialog simulation in progress"):
                    simulation = requests.post(url=simulation_url)
    elif latest_stage == "s04_paraphrases_generated":
        # assuming intents have been selected in the paraphrasing step
        # no options given here
        st.info("Paraphrases have been created.")
        if st.button("Start Dialog Simulation"):
            with st.spinner("Goal creation in progress"):
                generation = requests.post(url=generation_url)

    elif latest_stage == "s05_goal_created":
        latest_bot_id, latest_stage = database.get_last_db_row()
        config = dict(database.get_one_bot_test_instance(latest_bot_id))
        settings = database.db_record_to_setting(config)
        if settings["status"] == "simulating":
            ongoing = st.expander("Dialog simulation in progress")
            with ongoing:
                st.json(config)
            halt = st.checkbox("Restart (refresh page to take effect)")
            if halt:
                database.update_status(latest_bot_id, "")
        else:
            all_intents = st.multiselect(
                "Choose intents for simulation",
                list(set(config["dev"].split(",") + config["eval"].split(",")))
            )
            eval = st.checkbox("Simulation on held-out evaluation set")
            dev = st.checkbox("Simulation on dev set")
            if dev:
                settings["dev_intents"] = list(all_intents)
            else:
                settings["dev_intents"] = []
            if eval:
                settings["eval_intents"] = list(all_intents)
            else:
                settings["eval_intents"] = []
            settings["bot_Id"] = latest_bot_id
            if st.button("Start Dialog Simulation"):
                database.create_test_instance(settings)
                with st.spinner("Dialog simulation in progress"):
                    simulation = requests.post(url=simulation_url)
    elif latest_stage == "s06_simulation_completed":
        requests.post(url=remediation_url)
    elif config["status"] == "finished":
        st.balloons()
        st.success("Simulation done. Go to 'Health Report and Analytics' for results and analysis")








