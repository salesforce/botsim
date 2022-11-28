#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import streamlit as st
from PIL import Image

def app(database=None):
    display = Image.open("botsim/streamlit_app/BotSIM_Flow_onepager.png")
    st.image(display)
