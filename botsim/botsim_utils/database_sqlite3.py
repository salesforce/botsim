#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import sqlite3, shutil
from botsim.botsim_utils.utils import (
    get_bot_platform_intents,
    load_reports,
    extract_simulation_metrics)


def db_record_to_setting(config):
    settings = {'bot_Id': config['id'], 'bot_type': config['type'], 'test_description': config['descript'],
                'status': config['status'], 'stage': config['stage'], 'test_name': config['name'],
                'dev_intents': config['dev'].split(','), 'eval_intents': config['eval'].split(','),
                'end_point': config['end_point'], 'org_Id': config['orgId'], 'deployment_Id': config['deploymentId'],
                'button_Id': config['buttonId'], 'bot_version': '1', 'num_t5_paraphrases': config['num_t5_paraphrases'],
                'num_pegasus_paraphrases': config['num_pegasus_paraphrases'],
                'num_seed_utterances': config['num_intent_utts'], 'num_simulations': config['num_simulations'],
                'max_dialog_turns': config['max_simulation_rounds']}
    if config['type'] == 'DialogFlow_CX':
        settings['location_id'] = config['end_point']
        settings['agent_id'] = config['orgId']
        settings['project_id'] = config['deploymentId']
        settings['cx_credential'] = config['buttonId']

    return settings


def get_last_db_row(conn):
    test_ids = []
    stages = []
    conn = sqlite3.connect(conn)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""   SELECT  distinct b.id, b.stage   FROM  bots b order by b.id """)
    rows = cursor.fetchall()
    for row in rows:
        record = dict(row)
        test_id = record['id']
        test_ids.append(str(test_id))
        stages.append(str(record['stage']))
    if len(test_ids) > 0:
        latest_test_id = test_ids[-1]
        latest_stage = stages[-1]
        cursor.close()
        return latest_test_id, latest_stage
    else:
        return -1, 'new'


def insert(conn, test_session):
    conn = sqlite3.connect(conn)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    with conn:
        if test_session.type == 'DialogFlow_CX':
            cursor.execute("""INSERT INTO bots 
                         (name, type, descript, status, stage, dev, eval, end_point, orgId, 
                         deploymentId, buttonId, created_at, updated_at, version, num_t5_paraphrases, 
                         num_pegasus_paraphrases, num_intent_utts, num_simulations, max_simulation_rounds, 
                         has_bot, has_ml) VALUES 
                        (:name, :type, :descript, :status, :stage, :dev, :eval, :end_point, :orgId, 
                        :deploymentId, :buttonId, :created_at, :updated_at,:version, :num_t5_paraphrases, 
                        :num_pegasus_paraphrases, :num_intent_utts, :num_simulations, :max_simulation_rounds, 0, 0
                      ) """,
                           {'name': test_session.name,
                            'type': test_session.type,
                            'descript': test_session.descript, 'status': "new",
                            'stage': "config",
                            'dev': test_session.dev, 'eval': test_session.eval,
                            'end_point': test_session.cx_credential,
                            'orgId': test_session.project_id,
                            'buttonId': test_session.agent_id, 'deploymentId': test_session.location_id,
                            'created_at': test_session.created_at, 'updated_at': test_session.updated_at,
                            'version': test_session.version, 'num_t5_paraphrases': test_session.num_t5_paraphrases,
                            'num_pegasus_paraphrases': test_session.num_pegasus_paraphrases,
                            'num_intent_utts': test_session.num_intent_utts,
                            'num_simulations': test_session.num_simulations,
                            'max_simulation_rounds': test_session.max_simulation_rounds
                            })
        else:
            cursor.execute("""INSERT INTO bots 
                        (name, type, descript, status, stage, dev, eval, end_point, orgId, 
                        deploymentId, buttonId, created_at, updated_at, version, 
                        num_t5_paraphrases, num_pegasus_paraphrases, num_intent_utts, 
                        num_simulations, max_simulation_rounds, has_bot, has_ml) VALUES 
                        (:name, :type, :descript, :status, :stage, :dev, :eval, :end_point, :orgId, 
                        :deploymentId, :buttonId, :created_at, :updated_at,:version, 
                        :num_t5_paraphrases, :num_pegasus_paraphrases, :num_intent_utts, 
                        :num_simulations, :max_simulation_rounds, 0, 0
                        ) """,
                           {'name': test_session.name, 'type': test_session.type,
                            'descript': test_session.descript, 'status': "new", 'stage': "config",
                            'dev': test_session.dev, 'eval': test_session.eval,
                            'end_point': test_session.end_point,
                            'orgId': test_session.orgId, 'buttonId': test_session.buttonId,
                            'deploymentId': test_session.deploymentId,
                            'created_at': test_session.created_at, 'updated_at': test_session.updated_at,
                            'version': test_session.version, 'num_t5_paraphrases': test_session.num_t5_paraphrases,
                            'num_pegasus_paraphrases': test_session.num_pegasus_paraphrases,
                            'num_intent_utts': test_session.num_intent_utts,
                            'num_simulations': test_session.num_simulations,
                            'max_simulation_rounds': test_session.max_simulation_rounds
                            })
        conn.commit()
    return cursor.lastrowid


def get_bot_platform(conn):
    conn = sqlite3.connect(conn)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""   SELECT  distinct b.type, b.dev, b.eval, b.id   FROM results r, bots b
                                WHERE r.bot_id = b.id
                                order by b.id """)
    rows = cursor.fetchall()
    return get_bot_platform_intents(rows)


def check_database_table(db_name):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    if len(c.fetchall()) == 0:
        create_bot_test_database(db_name)


def delete_bot_test_instance(db_name, test_id):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    with conn:
        c.execute("SELECT * FROM bots WHERE id = :id", {'id': test_id})
        data = dict(c.fetchone())
        platform = data['type']

        c.execute("DELETE from bots WHERE id = :id ", {'id': test_id})
        c.execute("DELETE from results WHERE bot_id = :id ", {'id': test_id})
        conn.commit()
        shutil.rmtree('data/bots/{}/{}'.format(platform, str(test_id)))


def create_bot_test_database(db_name):
    print('creating bot database')
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    with conn:
        c.execute("""DROP TABLE IF EXISTS bots""")
        c.execute("""CREATE TABLE bots (
            id integer primary key,
            name text,
            status text,
            stage text,
            dev text,
            eval text,
            end_point text,
            orgId text,
            deploymentId text,
            buttonId text,
            version text,
            num_t5_paraphrases integer,
            num_pegasus_paraphrases integer,
            num_intent_utts integer,
            num_simulations integer,
            max_simulation_rounds integer,
            uid text,
            created_at real,
            updated_at real,
            has_bot integer,
            has_ml integer,
            has_revise integer,
            has_paraphrase integer,
            has_goals integer,
            has_simulate integer,
            has_remedy integer,
            log text,
            descript text,
            type text
            )""")

        c.execute("""DROP TABLE IF EXISTS results""")
        c.execute("""CREATE TABLE results (
            id integer primary key,
            bot_id integer,
            intent text,
            mode text,
            total integer,
            success integer,
            intent_error integer,
            ner_error integer,
            other_error integer,
            turns integer,
            json text
            ) """)


def save_result_to_database(db_name, test_id, intent, mode, total, success, intent_error, ner_error, other_error,
                            turns):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if mode == 'eval' and intent.find('_eval') == -1:
        intent = intent + '_eval'
    with conn:
        c.execute("""DELETE FROM results where bot_id = :bot_id and intent = :intent and mode = :mode """,
                  {'bot_id': str(test_id), 'intent': intent, 'mode': mode})
        c.execute("""INSERT INTO results 
        (bot_id, intent, mode, total, success, intent_error, ner_error, other_error, turns) VALUES 
        (:bot_id, :intent, :mode, :total, :success, :intent_error, :ner_error, :other_error, :turns) """,
                  {'bot_id': str(test_id), 'intent': intent, 'mode': mode, 'total': total, 'success': success,
                   'intent_error': intent_error,
                   'ner_error': ner_error, 'other_error': other_error, 'turns': turns})
        conn.commit()


def update_test_session(db_name, bot):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    with conn:
        if hasattr(bot, 'cx_credential'):
            c.execute("""UPDATE bots SET status = :status, type = :type, descript = :descript, updated_at = :updated_at,  
                         dev = :dev, eval = :eval, 
                        end_point = :end_point, orgId = :orgId, deploymentId = :deploymentId, buttonId = :buttonId,
                        version = :version, num_t5_paraphrases = :num_t5_paraphrases, 
                        num_pegasus_paraphrases = :num_pegasus_paraphrases, 
                        num_intent_utts = :num_intent_utts, num_simulations = :num_simulations, 
                        max_simulation_rounds = :max_simulation_rounds
                        WHERE id = :id """,
                      {'id': bot.id, 'type': bot.type, 'descript': bot.descript, 'status': bot.status,
                       'dev': bot.dev, 'eval': bot.eval,
                       'end_point': bot.cx_credential, 'orgId': bot.project_id, 'deploymentId': bot.location_id,
                       'buttonId': bot.agent_id, 'updated_at': bot.updated_at,
                       'version': bot.version, 'num_t5_paraphrases': bot.num_t5_paraphrases,
                       'num_pegasus_paraphrases': bot.num_pegasus_paraphrases,
                       'num_intent_utts': bot.num_intent_utts, 'num_simulations': bot.num_simulations,
                       'max_simulation_rounds': bot.max_simulation_rounds
                       })
        else:
            c.execute("""UPDATE bots SET status = :status, type = :type, descript = :descript, 
                         updated_at = :updated_at,  dev = :dev, eval = :eval, 
                                    end_point = :end_point, orgId = :orgId, deploymentId = :deploymentId, 
                                    buttonId = :buttonId,
                                    version = :version, num_t5_paraphrases = :num_t5_paraphrases, 
                                    num_pegasus_paraphrases = :num_pegasus_paraphrases, 
                                    num_intent_utts = :num_intent_utts, num_simulations = :num_simulations, 
                                    max_simulation_rounds = :max_simulation_rounds
                                    WHERE id = :id """,
                      {'id': bot.id, 'type': bot.type, 'descript': bot.descript, 'status': bot.status, 'dev': bot.dev,
                       'eval': bot.eval,
                       'end_point': bot.end_point, 'orgId': bot.orgId, 'deploymentId': bot.deploymentId,
                       'buttonId': bot.buttonId, 'updated_at': bot.updated_at,
                       'version': bot.version, 'num_t5_paraphrases': bot.num_t5_paraphrases,
                       'num_pegasus_paraphrases': bot.num_pegasus_paraphrases,
                       'num_intent_utts': bot.num_intent_utts, 'num_simulations': bot.num_simulations,
                       'max_simulation_rounds': bot.max_simulation_rounds
                       })
        conn.commit()


def update_stage(db_name, stage, test_id):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    with conn:
        if stage == 's03_human_in_the_loop_revision':
            status = 'ready'
        elif stage == 's07_remediation_completed':
            status = 'finished'
        elif stage == 's01_bot_design_metadata' or stage == 's02_inputs_completed':
            status = 'upload'
        else:
            status = 'running'
        #sql = "UPDATE bots SET status = :status, stage = :stage, " + stage + " = 1 where id = :id"
        sql = "UPDATE bots SET status = :status, stage = :stage where id = :id"
        c.execute(sql, {'id': str(test_id), 'stage': stage, 'status': status})
        conn.commit()


def update_status(db_name, test_id, status):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    with conn:
        sql = "UPDATE bots SET status = :status where id = :id"
        c.execute(sql, {'id': str(test_id), 'status': status})
        conn.commit()


def get_one_bot_test_instance(db_name, test_id):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bots WHERE id=:id", {'id': str(test_id)})
    data = c.fetchone()
    return data


def get_test_ids(db_name, platform):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    ids = []
    cursor.execute("""   SELECT  distinct b.id   FROM  bots b 
                                WHERE b.type= :platform
                                order by b.id """, {'platform': platform})
    rows = cursor.fetchall()
    for row in rows:
        record = dict(row)
        test_id = record['id']
        ids.append(str(test_id))
    return ids


def retrieve_all_test_sessions(db_name, project):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    ids = []
    cursor.execute("""   SELECT  distinct b.id   FROM results r, bots b 
                           WHERE r.bot_id = b.id and b.type= :project
                           order by b.id """, {'project': project})
    rows = cursor.fetchall()
    for row in rows:
        record = dict(row)
        test_id = record['id']
        ids.append(str(test_id))

    in_ids = '(' + ",".join(ids) + ')'

    sql = """ select mode, intent, 
                group_concat(bot_id) bot_id,   
                group_concat(COALESCE(total, 0)) total,
                group_concat(COALESCE(success, 0)) success,
                group_concat(COALESCE(intent_error, 0)) intent_error,
                group_concat(COALESCE(ner_error, 0)) ner_error,
                group_concat(COALESCE(other_error, 0)) other_error,
                group_concat(COALESCE(turns, 0)) turns,
                group_concat(COALESCE(success_rate, 0)) success_rate,
                group_concat(COALESCE(intent_rate, 0)) intent_rate,
                group_concat(COALESCE(ner_rate, 0)) ner_rate,
                group_concat(COALESCE(other_rate, 0)) other_rate,
                group_concat(COALESCE(turns_avg, 0)) turns_avg
                from (
                select x.*, y.* from
                (
                select distinct *, CASE WHEN substr(intent, -4, 4) = 'eval' THEN 'eval' ELSE 'dev' END mode 
                from (select bot_id from results where bot_id in {in_ids} order by bot_id) a, 
                (select distinct intent from results where bot_id in {in_ids} ) b
                ) x left join (
                select *, 
                100 * success / total as success_rate,
                100 * intent_error / total as intent_rate,
                100 * ner_error / total as ner_rate,
                100 * other_error / total as other_rate,
                turns / total as turns_avg
                from ( SELECT r.* 
                FROM results r
                where r.bot_id in {in_ids} 
                ) t
                ) y
                on x.bot_id = y.bot_id and x.intent = y.intent) tt
                group by  intent, mode """.format(in_ids=in_ids)

    # print(sql)
    cursor.execute(sql)
    rows = cursor.fetchall()
    dev_metrics, eval_metrics = extract_simulation_metrics(ids, rows)

    cursor.execute(""" select *, 
                        100 * success / total as success_rate,
                        100 * intent / total as intent_rate,
                        100 * ner / total as ner_rate,
                        100 * other / total as other_rate,
                        turns / total as turns_avg
                        from (SELECT b.name, b.version, b.id, b.status, b.updated_at, mode, count(*) cnt,
                        sum(r.total) total,
                        sum(r.success) success,
                        sum(r.intent_error) intent,
                        sum(r.ner_error) ner,
                        sum(r.other_error) other,
                        sum(r.turns) turns
                        FROM "bots" b, results r
                        where b.id = r.bot_id
                        and b.type = :name
                        group by b.id, mode ) t """, {'name': project})

    data = []
    rows = cursor.fetchall()
    for row in rows:
        record = dict(row)
        data.append(record)
    return data, dev_metrics, eval_metrics


def query_test_instance(db_name, test_id):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    with conn:
        c.execute("""SELECT b.id, mode, b.name, b.version, b.status, b.updated_at, b.created_at, 
                    sum(total) total,
                    sum(success) success,
                    sum(intent_error) intent_error,
                    sum(ner_error) ner_error,
                    sum(other_error) other_error,
                    sum(turns) turns
                    FROM bots b, results r
                    where b.id = r.bot_id
                    and b.id = :id
                    group by b.id, mode """, {'id': str(test_id)})
    rows = c.fetchall()
    return load_reports(test_id, rows)


def retrieve_all(db_name):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bots order by created_at")
    data = []
    rows = c.fetchall()
    for row in rows:
        data.append(list(row))
    return data


def retrieve_performance(db_name):
    conn = sqlite3.connect(db_name)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(""" select *, 
                        100 * success / total as success_rate,
                        100 * intent / total as intent_rate,
                        100 * ner / total as ner_rate,
                        100 * other / total as other_rate,
                        turns / total as turns_avg
                        from ( SELECT b.name, mode, 
                        sum(total) total, sum(success) success, sum(intent_error) intent, sum(ner_error) ner, 
                        sum(other_error) other, sum(turns) turns, bot_id
                        FROM results r, bots b
                        where r.bot_id = b.id
                        group by bot_id, mode) t """)
    success_dev = []
    intent_dev = []
    ner_dev = []
    other_dev = []
    turns_dev = []
    success_rate_dev = []
    intent_rate_dev = []
    ner_rate_dev = []
    other_rate_dev = []
    avg_turns_dev = []
    success_eval = []
    intent_eval = []
    ner_eval = []
    other_eval = []
    turns_eval = []
    success_rate_eval = []
    intent_rate_eval = []
    ner_rate_eval = []
    other_rate_eval = []
    avg_turns_eval = []

    labels = []
    rows = c.fetchall()
    for row in rows:
        l = list(row)
        if l[1] == 'dev':
            labels.append(l[8])
            success_dev.append(l[3])
            intent_dev.append(l[4])
            ner_dev.append(l[5])
            other_dev.append(l[6])
            turns_dev.append(l[7])
            success_rate_dev.append(l[9])
            intent_rate_dev.append(l[10])
            ner_rate_dev.append(l[11])
            other_rate_dev.append(l[12])
            avg_turns_dev.append(l[13])
        else:
            success_eval.append(l[3])
            intent_eval.append(l[4])
            ner_eval.append(l[5])
            other_eval.append(l[6])
            turns_eval.append(l[7])
            success_rate_eval.append(l[9])
            intent_rate_eval.append(l[10])
            ner_rate_eval.append(l[11])
            other_rate_eval.append(l[12])
            avg_turns_eval.append(l[13])

    total = [
        {'label': 'Success Dev', 'data': success_dev, 'backgroundColor': 'rgb(75, 192, 5)', 'stack': 'Stack 0'},
        {'label': 'Intent Dev', 'data': intent_dev, 'backgroundColor': 'rgb(75, 192, 192)', 'stack': 'Stack 0'},
        {'label': 'NER Dev', 'data': ner_dev, 'backgroundColor': 'rgb(75, 12, 192)', 'stack': 'Stack 0'},
        {'label': 'Other Dev', 'data': other_dev, 'backgroundColor': 'rgb(175, 42, 50)', 'stack': 'Stack 0'},
        {'label': 'Success Eval', 'data': success_eval, 'backgroundColor': 'rgb(75, 192, 5)', 'stack': 'Stack 1'},
        {'label': 'Intent Eval', 'data': intent_eval, 'backgroundColor': 'rgb(75, 192, 192)', 'stack': 'Stack 1'},
        {'label': 'NER Eval', 'data': ner_eval, 'backgroundColor': 'rgb(75, 12, 192)', 'stack': 'Stack 1'},
        {'label': 'Other Eval', 'data': other_eval, 'backgroundColor': 'rgb(175, 42, 50)', 'stack': 'Stack 1'},
    ]

    rate = [
        {'label': 'Success Dev', 'data': success_rate_dev, 'backgroundColor': 'rgb(75, 192, 5)', 'stack': 'Stack 0'},
        {'label': 'Intent Dev', 'data': intent_rate_dev, 'backgroundColor': 'rgb(75, 192, 192)', 'stack': 'Stack 0'},
        {'label': 'NER Dev', 'data': ner_rate_dev, 'backgroundColor': 'rgb(75, 12, 192)', 'stack': 'Stack 0'},
        {'label': 'Other Dev', 'data': other_rate_dev, 'backgroundColor': 'rgb(175, 42, 50)', 'stack': 'Stack 0'},
        {'label': 'Success Eval', 'data': success_rate_eval, 'backgroundColor': 'rgb(75, 192, 5)', 'stack': 'Stack 1'},
        {'label': 'Intent Eval', 'data': intent_rate_eval, 'backgroundColor': 'rgb(75, 192, 192)', 'stack': 'Stack 1'},
        {'label': 'NER Eval', 'data': ner_rate_eval, 'backgroundColor': 'rgb(75, 12, 192)', 'stack': 'Stack 1'},
        {'label': 'Other Eval', 'data': other_rate_eval, 'backgroundColor': 'rgb(175, 42, 50)', 'stack': 'Stack 1'},
    ]
    return total, rate, labels

