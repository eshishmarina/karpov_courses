from datetime import datetime, timedelta

import pandahouse
import pandas as pd
from airflow.decorators import dag, task

# для подключения к CH

connection = {
    'host': 'https://clickhouse.lab.karpov.courses',
    'password': '',
    'user': 'student',
    'database': 'simulator_20220820'
}

connection_test = {
    'host': 'https://clickhouse.lab.karpov.courses',
    'password': '',
    'user': 'student-rw',
    'database': 'test'
}

# Дефолтные параметры, которые прокидываются в таски
default_args = {
    'owner': 'e-shishmarina-10',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2022, 9, 7),
}

# Интервал запуска DAG
schedule_interval = '0 23 * * *'
@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def eshishmarina_dag():

    @task()
    def extract_feed():
        query_feed = """SELECT DISTINCT user_id,
                gender,
                age,
                os,
                countIf(user_id, action='like') as likes,
                countIf(user_id, action='view') as views,
                toDate(time) as event_date

        FROM simulator_20220820.feed_actions
        WHERE event_date = today()
        GROUP BY user_id, gender, age, os, event_date"""
        feed_table = pandahouse.read_clickhouse(query_feed, connection=connection)
        return feed_table

    @task()
    def extract_message():
        query_message = """
        WITH msg_received as (SELECT reciever_id,
                                     count(ma2.user_id) as cnt
                              FROM simulator_20220820.message_actions ma2
                              WHERE toDate(time) = today()
                              GROUP BY reciever_id),

             num_of_receivers as (SELECT user_id,
                                         count(DISTINCT ma2.reciever_id) as cnt
                                  FROM simulator_20220820.message_actions ma2
                                  WHERE toDate(time) = today()
                                  GROUP BY user_id),

             msg_sent as (SELECT user_id,
                                 count(ma2.reciever_id) as cnt
                          FROM simulator_20220820.message_actions ma2
                          WHERE toDate(time) = today()
                          GROUP BY user_id),

             num_of_senders as (SELECT reciever_id, count(DISTINCT ma2.user_id) as cnt
                                FROM simulator_20220820.message_actions ma2
                                WHERE toDate(time) = today()
                                GROUP BY reciever_id)

        SELECT DISTINCT ma.user_id as user_id,
                        ma.gender as gender,
                        ma.age as age,
                        ma.os as os,
                        msg_received.cnt as messages_received,
                        num_of_receivers.cnt as number_of_receivers,
                        msg_sent.cnt as messages_sent,
                        num_of_senders.cnt as number_of_senders,
                        toDate(ma.time) as event_date
        FROM simulator_20220820.message_actions ma
                 LEFT JOIN msg_received ON ma.user_id = msg_received.reciever_id
                 LEFT JOIN num_of_receivers ON ma.user_id = num_of_receivers.user_id
                 LEFT JOIN msg_sent ON ma.user_id = msg_sent.user_id
                 LEFT JOIN num_of_senders ON ma.user_id = num_of_senders.reciever_id
        WHERE toDate(ma.time) = today()
        """
        message_table = pandahouse.read_clickhouse(query_message, connection=connection)
        return message_table

    @task()
    def extract_merge(feed_table, message_table):
        merged_table = message_table.merge(feed_table, how='outer', on=['user_id', 'gender', 'age', 'os'])
        merged_table['event_date_x'].fillna(merged_table['event_date_y'], inplace=True)
        merged_table.fillna(0, inplace=True)
        merged_table.drop('event_date_y', axis=1, inplace=True)
        merged_table.rename(columns={"event_date_x": "event_date"}, inplace=True)
        return merged_table

    @task()
    def transform_gender(merged_table):
        df_cube_gender: pd.DataFrame = merged_table.groupby(['gender']) \
            .agg(views=('views', 'sum'), likes=('likes', 'sum'), messages_received=('messages_received', 'sum'), messages_sent=('messages_sent', 'sum'), users_received=('number_of_senders', 'sum'), users_sent=('number_of_receivers', 'sum'), event_date=('event_date', 'max')) \
            .reset_index()
        df_cube_gender.insert(0, 'dimension', 'gender')
        df_cube_gender = df_cube_gender.rename(columns={"gender": "dimension_value"})
        return df_cube_gender

    @task()
    def transform_os(merged_table):
        df_cube_os = merged_table.groupby(['os']) \
            .agg(views=('views', 'sum'), likes=('likes', 'sum'), messages_received=('messages_received', 'sum'), messages_sent=('messages_sent', 'sum'), users_received=('number_of_senders', 'sum'), users_sent=('number_of_receivers', 'sum'), event_date=('event_date', 'max')) \
            .reset_index()
        df_cube_os.insert(0, 'dimension', 'os')
        df_cube_os = df_cube_os.rename(columns={"os": "dimension_value"})
        return df_cube_os

    @task()
    def transform_age(merged_table):
        df_cube_age = merged_table.groupby(['age']) \
            .agg(views=('views', 'sum'), likes=('likes', 'sum'), messages_received=('messages_received', 'sum'), messages_sent=('messages_sent', 'sum'), users_received=('number_of_senders', 'sum'), users_sent=('number_of_receivers', 'sum'), event_date=('event_date', 'max')) \
            .reset_index()
        df_cube_age.insert(0, 'dimension', 'age')
        df_cube_age = df_cube_age.rename(columns={"age": "dimension_value"})
        return df_cube_age

    @task()
    def concat_tables(df_cube_gender, df_cube_os, df_cube_age):
        result = pd.concat([df_cube_gender, df_cube_os, df_cube_age])
        return result

    @task()
    def load(result):
        create_table = """
            create table if not exists test.eshishmarina_result
        (
            event_date Date,
            dimension String,
            dimension_value String,
            views UInt32,
            likes UInt32,
            messages_received UInt32,
            messages_sent UInt32,
            users_received UInt32,
            users_sent UInt32
        )   ENGINE = MergeTree()
            order by event_date"""

        pandahouse.execute(connection=connection_test, query=create_table)
        pandahouse.to_clickhouse(result, table='eshishmarina_result', connection=connection_test, index=False)

    message_table = extract_message()
    feed_table = extract_feed()
    merged_table = extract_merge(feed_table, message_table)
    df_cube_gender = transform_gender(merged_table)
    df_cube_os = transform_os(merged_table)
    df_cube_age = transform_age(merged_table)
    result = concat_tables(df_cube_gender, df_cube_os, df_cube_age)
    load(result)

eshishmarina_dag = eshishmarina_dag()
