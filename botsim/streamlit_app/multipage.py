#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import streamlit as st


class MultiPage:
    def __init__(self):
        self.pages = []

    def add_page(self, title, function):
        self.pages.append(
            {
                "title": title,
                "function": function
            }
        )

    def run(self, database):
        page = st.sidebar.selectbox(
            "App Navigation",
            self.pages,
            format_func=lambda page: page["title"]
        )

        # run the app function 
        page["function"](database)
