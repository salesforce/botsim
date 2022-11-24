#  Copyright (c) 2022, salesforce.com, inc.
#   All rights reserved.
#   SPDX-License-Identifier: BSD-3-Clause
#   For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

import shutil, psycopg2
import psycopg2.extras
from botsim.botsim_utils.utils import (
    get_bot_platform_intents,
    load_reports,
    extract_simulation_metrics)


def db_record_to_setting(config):
    settings = {'bot_Id': config['id'],
                'bot_type': config['type'],
                'test_description': config['descript'],
                'status': config['status'],
                'stage': config['stage'],
                'test_name': config['name'],
                'dev_intents': config['dev'].split(','),
                'eval_intents': config['eval'].split(','),
                'end_point': config['end_point'],
                'org_Id': config['orgid'],
                'deployment_Id': config['deploymentid'],
                'button_Id': config['buttonid'],
                'bot_version': '1',
                'num_t5_paraphrases': config['num_t5_paraphrases'],
                'num_pegasus_paraphrases': config['num_pegasus_paraphrases'],
                'num_seed_utterances': config['num_intent_utts'],
                'num_simulations': config['num_simulations'],
                'max_dialog_turns': config['max_simulation_rounds']}
    if config['type'] == 'DialogFlow_CX':
        settings['location_id'] = config['end_point']
        settings['agent_id'] = config['orgid']
        settings['project_id'] = config['deploymentid']
        settings['cx_credential'] = config['buttonid']

    return settings


def check_database_table(conn):
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM pg_catalog.pg_tables "
                   "WHERE schemaname != 'pg_catalog' AND  schemaname != 'information_schema'")
    if len(cursor.fetchall()) == 0:
        create_bot_test_database()
    cursor.close()


def delete_bot_test_instance(conn, bot_id):
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("""SELECT  distinct b.type  FROM  bots b WHERE b.id= %s """, [bot_id])
        platform = dict(cursor.fetchone())[0]
        cursor.execute("DELETE from bots WHERE id = %s ", [bot_id])
        cursor.execute("DELETE from results WHERE bot_id = %s ", [bot_id])
        cursor.close()
        conn.commit()
        shutil.rmtree('data/bots/{}/{}'.format(platform, str(bot_id)))


def create_bot_test_database(conn):
    print('creating bot database')
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("""DROP TABLE IF EXISTS bots""")
        cursor.execute("""CREATE TABLE bots (
            id serial primary key,
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

        cursor.execute("""DROP TABLE IF EXISTS results""")
        cursor.execute("""CREATE TABLE results (
            id serial primary key,
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
        cursor.close()


def save_result_to_database(conn, bot_id, intent, mode, total, success, intent_error, ner_error, other_error, turns):
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("""DELETE FROM results where bot_id = %s and intent = %s and mode = %s """,
                       (bot_id, intent, mode))
        cursor.execute("""INSERT INTO results (bot_id, intent, mode, total, success, intent_error, 
                          ner_error, other_error, turns) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) """,
                       (bot_id, intent, mode, total, success, intent_error, ner_error, other_error, turns))
        cursor.close()
        conn.commit()


def insert(conn, bot):
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if hasattr(bot, 'cx_credential'):
            cursor.execute("""INSERT INTO bots 
                            (name, type, descript, status, stage, dev, eval, end_point, orgId, 
                             deploymentId, buttonId, created_at, updated_at, version, 
                             num_t5_paraphrases, num_pegasus_paraphrases, num_intent_utts, 
                             num_simulations, max_simulation_rounds, has_bot, has_ml) 
                             VALUES  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 
                             %s, %s, %s, %s, %s, %s, 0, 0 )  RETURNING id """,
                           (bot.name, bot.type, bot.descript, "new", "config",
                            bot.dev, bot.eval, bot.cx_credential,
                            bot.project_id, bot.location_id, bot.agent_id,
                            bot.created_at, bot.updated_at,
                            bot.version, bot.num_t5_paraphrases, bot.num_pegasus_paraphrases,
                            bot.num_intent_utts, bot.num_simulations, bot.max_simulation_rounds
                            ))
        else:
            cursor.execute("""INSERT INTO bots 
                            (name, type, descript, status, stage, dev, eval, end_point, orgId, 
                            deploymentId, buttonId, created_at, updated_at, version, 
                            num_t5_paraphrases, num_pegasus_paraphrases, num_intent_utts, 
                            num_simulations, max_simulation_rounds, has_bot, has_ml) VALUES 
                            (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s, %s, %s, 
                            %s, %s, %s, 0, 0)  RETURNING id """,
                           (bot.name, bot.type, bot.descript, "new", "config",
                            bot.dev, bot.eval,
                            bot.end_point,
                            bot.orgId, bot.deploymentId, bot.buttonId,
                            bot.created_at, bot.updated_at,
                            bot.version, bot.num_t5_paraphrases,
                            bot.num_pegasus_paraphrases,
                            bot.num_intent_utts, bot.num_simulations,
                            bot.max_simulation_rounds
                            ))
        conn.commit()

    bot_id = cursor.fetchone()[0]
    cursor.close()
    return bot_id


def update_test_session(conn, bot):
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if hasattr(bot, 'cx_credential'):
            cursor.execute("""UPDATE bots SET status =  %s, type = %s, descript =  %s, updated_at =  %s, 
                              dev =  %s, eval =  %s, end_point = %s, orgId =  %s, deploymentId =  %s, 
                              buttonId =  %s, version =  %s, num_t5_paraphrases =  %s, num_pegasus_paraphrases = %s, 
                              num_intent_utts =  %s, num_simulations =  %s, max_simulation_rounds =  %s
                              WHERE id =  %s """,
                           (bot.status, bot.type, bot.descript, bot.updated_at, bot.dev, bot.eval,
                            bot.cx_credential, bot.project_id, bot.location_id, bot.agent_id,
                            bot.version, bot.num_t5_paraphrases, bot.num_pegasus_paraphrases,
                            bot.num_intent_utts, bot.num_simulations, bot.max_simulation_rounds, bot.id
                            ))
        else:
            cursor.execute("""UPDATE bots SET status = %s, type = %s, descript = %s, updated_at = %s,  dev = %s, eval = %s, 
                                    end_point = %s, orgId = %s, deploymentId = %s, buttonId = %s,
                                    version = %s, num_t5_paraphrases = %s, num_pegasus_paraphrases = %s, 
                                    num_intent_utts = %s, num_simulations = %s, max_simulation_rounds = %s
                                    WHERE id = %s """,
                           (bot.status, bot.type, bot.descript, bot.updated_at, bot.dev, bot.eval,
                            bot.end_point, bot.orgId, bot.deploymentId, bot.buttonId,
                            bot.version, bot.num_t5_paraphrases, bot.num_pegasus_paraphrases,
                            bot.num_intent_utts, bot.num_simulations,
                            bot.max_simulation_rounds, bot.id
                            ))
        conn.commit()
        cursor.close()


def update_stage(conn, stage, bot_id):
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if stage == 's03_human_in_the_loop_revision':
            status = 'ready'
        elif stage == 's07_remediation_completed':
            status = 'finished'
        elif stage == 's01_bot_design_metadata' or stage == 's02_inputs_completed':
            status = 'upload'
        else:
            status = 'running'
        # sql = "UPDATE bots SET status = %s, stage = %s, " + stage + " = 1 where id = %s"
        sql = "UPDATE bots SET status = %s, stage = %s " + " where id = %s"
        cursor.execute(sql, (status, stage, bot_id))
        conn.commit()
        cursor.close()


def update_status(conn, bot_id, status):
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        sql = "UPDATE bots SET status = %s where id = %s"
        cursor.execute(sql, (status, bot_id))
        conn.commit()
        cursor.close()


def get_one_bot_test_instance(conn, id):
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM bots WHERE id=%s", [id])
    data = cursor.fetchone()
    cursor.close()
    return dict(data)


def get_test_ids(conn, platform):
    ids = []
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT  distinct b.id   FROM  bots b WHERE b.type= %s order by b.id """, [platform])
    rows = cursor.fetchall()
    for row in rows:
        record = dict(row)
        test_id = record['id']
        ids.append(str(test_id))
    return ids


def retrieve_all_test_sessions(conn, project):
    ids = []
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""SELECT  distinct b.id   FROM results r, bots b 
                            WHERE r.bot_id = b.id and b.type= %s
                            order by b.id """, [project])
    rows = cursor.fetchall()
    for row in rows:
        record = dict(row)
        test_id = record['id']
        ids.append(str(test_id))

    in_ids = '(' + ",".join(ids) + ')'

    sql = """ select mode, intent, 
                string_agg(bot_id::varchar, ',') bot_id  ,
                string_agg((COALESCE(total, 0))::varchar, ',') total,
                string_agg((COALESCE(success, 0))::varchar , ',') success,
                string_agg((COALESCE(intent_error, 0))::varchar , ',')intent_error,
                string_agg((COALESCE(ner_error, 0))::varchar , ',')ner_error,
                string_agg((COALESCE(other_error, 0))::varchar , ',')other_error,
                string_agg((COALESCE(turns, 0))::varchar , ',')turns,
                string_agg((COALESCE(success_rate, 0))::varchar , ',')success_rate,
                string_agg((COALESCE(intent_rate, 0))::varchar , ',')intent_rate,
                string_agg((COALESCE(ner_rate, 0))::varchar , ',')ner_rate,
                string_agg((COALESCE(other_rate, 0))::varchar , ',')other_rate,
                string_agg((COALESCE(turns_avg, 0))::varchar , ',')turns_avg
                from (
                select y.* from
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
                        and b.type = %s
                        group by b.id, mode ) t """, [project])

    data = []
    rows = cursor.fetchall()
    for row in rows:
        record = dict(row)
        data.append(record)
    cursor.close()
    return data, dev_metrics, eval_metrics


def insert(conn, bot):
    with conn:
        if bot.type == 'Einstein_Bot':
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""INSERT INTO bots 
            (name, type, descript, status, stage, dev, eval, end_point, orgId, deploymentId, buttonId, created_at, 
            updated_at, version, num_t5_paraphrases, num_pegasus_paraphrases, num_intent_utts, num_simulations, 
            max_simulation_rounds, has_bot, has_ml) VALUES  (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s, %s, %s, %s, %s, %s, 0, 0 )  RETURNING id """,
                           (bot.name, bot.type, bot.descript, "new", "config",
                            bot.dev, bot.eval, bot.cx_credential,
                            bot.project_id, bot.location_id, bot.agent_id,
                            bot.created_at, bot.updated_at,
                            bot.version, bot.num_t5_paraphrases, bot.num_pegasus_paraphrases,
                            bot.num_intent_utts, bot.num_simulations, bot.max_simulation_rounds
                            ))
        else:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute("""INSERT INTO bots 
                        (name, type, descript, status, stage, dev, eval, end_point, orgId, deploymentId, 
                        buttonId, created_at, updated_at, version, num_t5_paraphrases, num_pegasus_paraphrases, 
                        num_intent_utts, num_simulations, max_simulation_rounds, has_bot, has_ml) VALUES 
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,%s, %s, %s, %s, %s, %s, 0, 0)  
                        RETURNING id """,
                           (bot.name, bot.type, bot.descript, "new", "config",
                            bot.dev, bot.eval,
                            bot.end_point,
                            bot.orgId, bot.deploymentId, bot.buttonId,
                            bot.created_at, bot.updated_at,
                            bot.version, bot.num_t5_paraphrases,
                            bot.num_pegasus_paraphrases,
                            bot.num_intent_utts, bot.num_simulations,
                            bot.max_simulation_rounds
                            ))
        conn.commit()

    bot_id = cursor.fetchone()[0]
    cursor.close()
    print('inserted bot with id: ' + str(bot_id))
    return bot_id


def get_last_db_row(conn):
    ids = []
    stages = []
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""   SELECT  distinct b.id, b.stage   FROM  bots b
                        order by b.id """)
    rows = cursor.fetchall()
    cursor.close()
    for row in rows:
        record = dict(row)
        test_id = record['id']
        ids.append(str(test_id))
        stages.append(str(record['stage']))
    if len(ids) > 0:
        latest_bot_id = ids[-1]
        latest_stage = stages[-1]
        return latest_bot_id, latest_stage
    else:
        return -1, 'new'


def get_bot_platform(conn):
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("""   SELECT  distinct b.type, b.dev, b.eval, b.id FROM results r, bots b
                                WHERE r.bot_id = b.id
                                order by b.id """)
    rows = cursor.fetchall()
    cursor.close()
    return get_bot_platform_intents(rows)


def query_test_instance(conn, test_id):
    with conn:
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cursor.execute("""SELECT b.id, mode, b.name, b.version, b.status, b.updated_at, b.created_at,
                    sum(total) total,
                    sum(success) success,
                    sum(intent_error) intent_error,
                    sum(ner_error) ner_error,
                    sum(other_error) other_error,
                    sum(turns) turns
                    FROM bots b, results r
                    where b.id = r.bot_id
                    and b.id = %s
                    group by b.id, mode """, [test_id])

    rows = cursor.fetchall()
    cursor.close()
    return load_reports(test_id, rows)


def retrieve_all(conn):
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute("SELECT * FROM bots order by created_at")
    data = []
    rows = cursor.fetchall()
    for row in rows:
        data.append(list(row))
    cursor.close()
    return data


def retrieve_performance(conn):
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cursor.execute(""" select *, 
                        100 * success / total as success_rate,
                        100 * intent / total as intent_rate,
                        100 * ner / total as ner_rate,
                        100 * other / total as other_rate,
                        turns / total as turns_avg
                        from ( SELECT b.name, mode, 
                        sum(total) total, sum(success) success, sum(intent_error) intent, 
                        sum(ner_error) ner, sum(other_error) other, sum(turns) turns, bot_id
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
    rows = cursor.fetchall()
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
    cursor.close()
    return total, rate, labels
