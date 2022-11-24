#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import streamlit as st
from multipage import MultiPage
from pages import setup, upload_input, simulation, dashboard, overview, visualise_flow

from botsim.streamlit_app.backend import botsim_simulation, botsim_generation, botsim_remediation, database

st.set_page_config(layout="wide")
database.check_database_table()

if not hasattr(st, "already_started_server"):
    # Hack the fact that Python modules (like st) only load once to
    # keep track of whether this file already ran.
    st.already_started_server = True

    st.write("""
        Starting Flask server...
        Refresh to start the Streamlit app.
    """)

    from flask import Flask, request
    from flask_cors import CORS

    app = Flask(__name__)
    app.config["UPLOAD_FOLDER"] = "bots/"
    CORS(app)

    @app.route("/pipeline", methods=["GET", "POST"])
    def run_pipeline():
        url = request.url
        if (url[0] == "/" and not url.find("//") == 0) or url.find("http://127.0.0.1:8887/") == 0:
            latest_bot_id, latest_stage = database.get_last_db_row()
            return botsim_pipeline(latest_bot_id)


    @app.route("/simulation", methods=["GET", "POST"])
    def run_simulation():
        url = request.url
        if (url[0] == "/" and not url.find("//") == 0) or url.find("http://127.0.0.1:8887/") == 0:
            latest_bot_id, latest_stage = database.get_last_db_row()
            return botsim_simulation(latest_bot_id)
        return None


    @app.route("/generation", methods=["GET", "POST"])
    def run_generation():
        url = request.url
        if (url[0] == "/" and not url.find("//") == 0) or url.find("http://127.0.0.1:8887/") == 0:
            latest_bot_id, latest_stage = database.get_last_db_row()
            return botsim_generation(latest_bot_id)
        return None


    if __name__ == "__main__":
        app.run(port=8887)

from PIL import Image
# Create an instance of the app
app = MultiPage()

st.title("BotSIM: An End-to-End Bot SIMulation Toolkit")
logo = Image.open("botsim/streamlit_app/LOGO.png")
st.sidebar.image(logo.resize((417, 292)))

# st.markdown(
#         "<img id='sf-logo' src='https://c1.sfdcstatic.com/content/dam/sfdc-docs/www/logos/logo-salesforce.svg' style='position: absolute;top: -70px;right: 5px;'></img>",
#         unsafe_allow_html=True,
#     )


# Add all your application here
app.add_page("BotSIM Overview", overview.app)
app.add_page("1. Simulation Setup", setup.app)
app.add_page("2. Upload Inputs", upload_input.app)
app.add_page("3. Dialog Generation and Simulation", simulation.app)
app.add_page("4. Health Reports and Analytics", dashboard.app)
app.add_page("5. Conversation Flow", visualise_flow.app)

# The main app
app.run(database)
