#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import psycopg2, os, sqlite3, time, json
from botsim.botsim_utils.utils import (
    BotTestInstance,
    dump_s3_file,
    file_exists)


class Database:
    """
    Database class to keep track of simulation sessions for Web App
    Two types of databases are supported:
    1) sqlite3 for docker/local deployment 2) postgres for Heroku deployment
    """

    def __init__(self, database_type,
                 sqlite_db_path="db/botsim_sqlite3.db",
                 postgres_path=""):
        self.type = database_type.lower()
        assert database_type.lower() == "postgres" or database_type.lower() == "sqlite3"
        if self.type == "postgres":
            from urllib.parse import urlparse
            database_url = postgres_path
            # whitelist postgresql connection and verify url to avid SSRF risk
            if database_url.find("postgresql") != -1:
                result = urlparse(database_url)
                username = result.username
                password = result.password
                database = result.path[1:]
                hostname = result.hostname
                port = result.port
                self.conn = psycopg2.connect(
                    database=database,
                    user=username,
                    password=password,
                    host=hostname,
                    port=port
                )
        elif self.type == "sqlite3":
            os.makedirs(os.path.dirname(sqlite_db_path), exist_ok=True)
            self.conn = sqlite_db_path

    def get_connection(self):
        """Get a reference of the connection to the database"""
        return self.conn

    def check_database_table(self):
        """
        Check whether database tables exist. Create a table if none exists.
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import check_database_table
        else:
            from botsim.botsim_utils.database_sqlite3 import check_database_table
        check_database_table(self.conn)

    def update_stage(self, stage, test_id):
        """Update the simulation stage.
        The stages include
        1) new 2) upload 3) s01_bot_design_metadata (whether metadata has been uploaded)
        4) s02_inputs_completed (whether intent utterance metadata is provided)
        5) s03_human_in_the_loop_revision
        5) s04_paraphrases_generated (whether paraphrasing has finished)
        6) s05_goal_created (whether dialog goals have been generated)
        7) s06_simulation_completed (whether dialog simulation has finished)
        8) s07_remediation_completed (whether remediation results are obtained)
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import update_stage
        else:
            from botsim.botsim_utils.database_sqlite3 import update_stage
        update_stage(self.conn, stage, test_id)

    def update_status(self, test_id, status):
        """ Update simulation status for "simulation" page.
        The two most time-consuming stages are "paraphrasing", "simulating".
        App users can run these stages in the background and check the status later. The app page queries database
        for the latest status including  "paraphrasing", "simulating" or "finished".
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import update_status
        else:
            from botsim.botsim_utils.database_sqlite3 import update_status
        update_status(self.conn, test_id, status)

    def get_one_bot_test_instance(self, test_id):
        """ Retrieve a test instance (database record) given a test_id.
        """
        last_id = self.get_last_db_row()
        session_id = str(test_id)
        if not session_id.isdigit() or int(session_id) < 0 or int(session_id) > int(last_id[0]):
            return {}
        if self.type == "postgres":
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("SELECT * FROM bots WHERE id=%s", [session_id])
            data = cursor.fetchone()
            cursor.close()
            return dict(data)
        else:
            conn = sqlite3.connect(self.conn)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT * FROM bots WHERE id=:id", {"id": test_id})
            data = c.fetchone()
            return data

    def db_record_to_setting(self, record):
        """
        Convert a database record to a configuration setting
        :param record: a database record/row
        :return: simulation setting dict
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import db_record_to_setting
        else:
            from botsim.botsim_utils.database_sqlite3 import db_record_to_setting
        return db_record_to_setting(record)

    def retrieve_all_test_sessions(self, platform):
        """
        Retrieve all simulation results of the given platform from "results" table
        :param platform: platform name, e.g., Einstein_Bot, DialogFlow_CX
        :return: a tuple of the following
            data:
            dev_total_counts: dev intent prediction counts
            dev_rates: dev_total_counts converted to rates
            eval_total_counts: eval intent prediction counts
            eval_rates: eval_total_counts converted to rates
            test_ids: test ids belonging to the project
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import retrieve_all_test_sessions
        else:
            from botsim.botsim_utils.database_sqlite3 import retrieve_all_test_sessions
        return retrieve_all_test_sessions(self.conn, platform)

    def get_test_ids(self, platform):
        """
        Get all test ids of the given platform
        :param platform: platform name, e.g., Einstein_Bot, DialogFlow_CX
        :return: a list of test ids
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import get_test_ids
        else:
            from botsim.botsim_utils.database_sqlite3 import get_test_ids
        return get_test_ids(self.conn, platform)

    def get_bot_platform(self):
        """
        Retrieve all project/platform names and their dialog/intent names
        Returns: a tuple of
            projects: a list of projects/platforms
            dev_intents: a dict mapping from test ids to dev intent names
            eval_intents: a dict mapping from test ids to eval intent names
            all_intents: list of dev intents from the most recently finished testing sessions
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import get_bot_platform
        else:
            from botsim.botsim_utils.database_sqlite3 import get_bot_platform
        return get_bot_platform(self.conn)

    def get_last_db_row(self):
        """
        Get the latest db record id
        Returns: a tuple of (latest, latest_stage)
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import get_last_db_row
        else:
            from botsim.botsim_utils.database_sqlite3 import get_last_db_row
        return get_last_db_row(self.conn)

    def update_test_session(self, test_instance):
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import update_test_session
        else:
            from botsim.botsim_utils.database_sqlite3 import update_test_session
        update_test_session(self.conn, test_instance)

    def create_test_instance(self, settings):
        """
        Create a new BotTestInstance object and prepare the data directories. Insert or update the data record
        with the newly created instance
        :param settings: bot test settings
        """
        time_stamp = time.time()
        api_token = {}
        if settings["bot_type"] == "Einstein_Bot":
            bot_test_instance = BotTestInstance(
                settings["bot_Id"],
                settings["bot_type"],
                settings["test_description"],
                settings["status"],
                settings["test_name"],
                ",".join(settings["dev_intents"]),
                ",".join(settings["eval_intents"]),
                settings["end_point"],
                settings["org_Id"],
                settings["deployment_Id"],
                settings["button_Id"],
                time_stamp, time_stamp,
                settings["bot_version"],
                settings["num_t5_paraphrases"],
                settings["num_pegasus_paraphrases"],
                settings["num_seed_utterances"],
                settings["num_simulations"],
                settings["max_dialog_turns"]
            )
            api_token = {"end_point": settings["end_point"],
                         "org_Id": settings["org_Id"],
                         "deployment_Id": settings["deployment_Id"],
                         "button_Id": settings["button_Id"]}
        elif settings["bot_type"] == "DialogFlow_CX":
            bot_test_instance = BotTestInstance(
                settings["bot_Id"],
                settings["bot_type"],
                settings["test_description"],
                settings["status"],
                settings["test_name"],
                ",".join(settings["dev_intents"]),
                ",".join(settings["eval_intents"]),
                settings["location_id"],
                settings["agent_id"],
                settings["project_id"],
                settings["cx_credential"],
                time_stamp, time_stamp,
                settings["bot_version"],
                settings["num_t5_paraphrases"],
                settings["num_pegasus_paraphrases"],
                settings["num_seed_utterances"],
                settings["num_simulations"],
                settings["max_dialog_turns"]
            )
            api_token = {"location_id": settings["location_id"],
                         "agent_id": settings["agent_id"],
                         "project_id": settings["project_id"],
                         "cx_credential": settings["cx_credential"]}

        if bot_test_instance.id == "":
            print("create new test session")
            bot_test_instance.id = self.insert(bot_test_instance)
            if settings["bot_type"] == "DialogFlow_CX":
                self.update_stage("s02_inputs_completed", bot_test_instance.id)
            if os.environ.get("STORAGE") != "S3":
                os.makedirs("data/bots/{}/{}".format(str(bot_test_instance.type), str(bot_test_instance.id)),
                            exist_ok=True)
                os.makedirs("data/bots/{}/{}".format(str(bot_test_instance.type), str(bot_test_instance.id)) + "/conf",
                            exist_ok=True)
                os.makedirs("data/bots/{}/{}".format(str(bot_test_instance.type), str(bot_test_instance.id)) + "/bots",
                            exist_ok=True)
                os.makedirs(
                    "data/bots/{}/{}".format(str(bot_test_instance.type), str(bot_test_instance.id)) + "/cm_data",
                    exist_ok=True)
                os.makedirs(
                    "data/bots/{}/{}".format(str(bot_test_instance.type), str(bot_test_instance.id)) + "/goals_dir",
                    exist_ok=True)
        else:
            print("update  test session")
            self.update_test_session(bot_test_instance)

        name = "data/bots/{}/{}/conf/config.json".format(str(bot_test_instance.type), str(bot_test_instance.id))
        if "STORAGE" in os.environ and os.environ["STORAGE"] == "S3":
            if not file_exists("botsim", name):
                config = bot_test_instance.generate_config()
                config.update({"api": api_token})
                dump_s3_file(name, bytes(json.dumps(config, indent=2).encode("UTF-8")))
        else:
            if not os.path.exists(
                    "data/bots/{}/{}/conf/config.json".format(str(bot_test_instance.type), str(bot_test_instance.id))):
                with open("data/bots/{}/{}/conf/config.json".format(str(bot_test_instance.type),
                                                                    str(bot_test_instance.id)), "w") as f:
                    config = bot_test_instance.generate_config()
                    config.update({"api": api_token})
                    json.dump(config, f, indent=2)
        return bot_test_instance.id

    def insert(self, test_instance):
        """
        Insert a BotTestInstance into database
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import insert
        else:
            from botsim.botsim_utils.database_sqlite3 import insert
        return insert(self.conn, test_instance)

    def save_result_to_database(self,
                                test_id, intent, mode, total, success, intent_error, ner_error, other_error, turns):
        """
        Save simulation results to results table
        :param test_id: test id
        :param intent: intent name
        :param mode: simulation mode, dev or eval
        :param total: total number of episodes
        :param success: number of successfully finished episodes
        :param intent_error: number of episodes with intent errors
        :param ner_error: number of episodes with NER errors
        :param other_error: number of episodes with other errors
        :param turns: tota number of dialog turns
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import save_result_to_database
        else:
            from botsim.botsim_utils.database_sqlite3 import save_result_to_database
        save_result_to_database(self.conn, test_id, intent, mode, total, success, intent_error, ner_error, other_error,
                                turns)

    def delete_bot_test_instance(self, test_id):
        """
        Delete one database record
        :param test_id: test id to be deleted
        """
        if self.type == "postgres":
            from botsim.botsim_utils.database_postgres import delete_bot_test_instance
        else:
            from botsim.botsim_utils.database_sqlite3 import delete_bot_test_instance
        delete_bot_test_instance(self.conn, test_id)
