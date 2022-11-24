#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

from botsim.modules.remediator.dashboard.dashboard import Dashboard
from botsim.streamlit_app.database import Database
import os
if os.environ.get("DATABASE_URL") and os.environ.get("DATABASE_URL").find("postgre") != -1:
    database = Database("postgres")
else:
    database = Database("sqlite3", "db/botsim_sqlite.db")
dashboard = Dashboard(database = database)
dashboard.render()