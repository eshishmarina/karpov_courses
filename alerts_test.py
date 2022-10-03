from datetime import timedelta, datetime
import telegram
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import seaborn as sns
import pandahouse
import sys
import os
from darts.models import NaiveSeasonal
from darts import TimeSeries
from airflow.decorators import dag, task

connection = {
    'host': 'https://clickhouse.lab.karpov.courses',
    'password': 'dpo_python_2020',
    'user': 'student',
    'database': 'simulator'
}


# функция предлагает алгоритм поиска аномалий в данных - межквартильный размах
def check_anomaly(df, metric, a=3, n=5):
    df['q25'] = df[metric].shift(1).rolling(n).quantile(0.25)
    df['q75'] = df[metric].shift(1).rolling(n).quantile(0.75)
    df['iqr'] = df['q75'] - df['q25']
    df['up'] = df['q75'] + a * df['iqr']
    df['low'] = df['q25'] - a * df['iqr']

    df['up'] = df['up'].rolling(n, center=True, min_periods=1).mean()
    df['low'] = df['low'].rolling(n, center=True, min_periods=1).mean()

    if df[metric].iloc[-1] < df['low'].iloc[-1] or df[metric].iloc[-1] > df['up'].iloc[-1]:
        is_alert = 1
    else:
        is_alert = 0

    return is_alert, df


# система алертов
def run_alerts_if_necessary(chat_id=None):
    target_chat_id = chat_id or 193085615
    bot = telegram.Bot(token='5630469594:AAGLnB3VCDJDtrkPfQ9MR9JfUW_dhz53Nf0')
    query = """select ts, date, hm, users_feed, views, likes, ctr, users_message, sent_message 
                from
        (select toStartOfFifteenMinutes(time) as ts,
               toDate(time)as date,
               formatDateTime(ts, '%R') as hm,
               uniqExact(user_id) as users_feed,
               countIf(user_id, action='view') as views,
               countIf(user_id, action='like') as likes,
               countIf(user_id, action='like')/countIf(user_id, action='view') as ctr
        from simulator_20220820.feed_actions
        where time >= today()-1 and time < toStartOfFifteenMinutes(now())
        group by ts, date, hm
        order by ts) as feed
full join
        (select toStartOfFifteenMinutes(time) as ts,
                toDate(time)as date,
                formatDateTime(ts, '%R') as hm,
                uniqExact(user_id) as users_message,
                count(user_id) as sent_message
        from simulator_20220820.message_actions
        where time >= today()-1 and time < toStartOfFifteenMinutes(now())
        group by ts, date, hm
        order by ts) as msg

on msg.date=feed.date and msg.hm=feed.hm"""
    query_table = pandahouse.read_clickhouse(query, connection=connection)

    metrics_list = ['users_feed', 'views', 'likes', 'ctr', 'users_message', 'sent_message']
    for metric in metrics_list:
        print(metric)
        df = query_table[['ts', 'date', 'hm', metric]].copy()
        is_alert, df = check_anomaly(df, metric)

        if is_alert == 1 or True:
            msg = "Метрика {metric}: текущее значение {current_val:.2f}, отклонение от предыдущего значения {last_val_diff:.2%}".format(
                metric=metric, current_val=df[metric].iloc[-1],
                last_val_diff=1 - df[metric].iloc[-1] / df[metric].iloc[-2])

            sns.set(rc={'figure.figsize': (16, 10)})
            plt.tight_layout()
            ax = sns.lineplot(x=df['ts'], y=df[metric], label='metric')
            ax = sns.lineplot(x=df['ts'], y=df['up'], label='up')
            ax = sns.lineplot(x=df['ts'], y=df['low'], label='low')
            ax.set(xlabel='time')
            ax.set(ylabel=metric)
            ax.set_title(metric)
            ax.set(ylim=(0, None))

            plot_object = io.BytesIO()
            plt.savefig(plot_object)
            plot_object.seek(0)
            plot_object.name = '{0}.png'.format(metric)
            plt.close()

            bot.sendMessage(chat_id=target_chat_id, text=msg)
            bot.sendPhoto(chat_id=target_chat_id, photo=plot_object)

    return


# Дефолтные параметры, которые прокидываются в таски
default_args = {
    'owner': 'e-shishmarina-10',
    'depends_on_past': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
    'start_date': datetime(2022, 9, 11),
}

# Интервал запуска DAG
schedule_interval = '0 11 * * *'


@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def eshishmarina_alerts_test_dag():
    @task()
    def run_alerts():
        run_alerts_if_necessary()


eshishmarina_alerts_test_dag = eshishmarina_alerts_test_dag()