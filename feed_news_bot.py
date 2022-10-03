from datetime import timedelta, datetime

import telegram
import matplotlib.pyplot as plt
import io
import pandahouse
from airflow.decorators import dag, task

connection = {
    'host': 'https://clickhouse.lab.karpov.courses',
    'password': '',
    'user': 'student',
    'database': 'simulator'
}

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
def eshishmarina_feed_news_dag():
    @task()
    def test_report():
        chat_id = 0
        bot = telegram.Bot(token='')

        feed_and_msg = """SELECT count(DISTINCT user_id) as uniq_user_id, time FROM
        (SELECT user_id, toStartOfDay(toDateTime(time)) AS time from simulator_20220820.feed_actions) as feed_actions
        join
        (SELECT user_id, toStartOfDay(toDateTime(time)) AS time from simulator_20220820.message_actions) as message_actions
        using user_id
        where toStartOfDay(feed_actions.time)=toStartOfDay(message_actions.time) and
        (toDate(time) >= today() - 7 and toDate(time) <= today() - 1)
        group by time
        order by time"""
        feed_and_msg = pandahouse.read_clickhouse(feed_and_msg, connection=connection)

        only_feed = """
        SELECT count(distinct user_id) as uniq_user_id, time FROM
        (
            SELECT fa.user_id, toStartOfDay(toDateTime(fa.time)) AS time
            FROM simulator_20220820.feed_actions fa
        ) as t1
        LEFT JOIN
        (
            SELECT ma.user_id, toStartOfDay(toDateTime(ma.time)) as time
            FROM simulator_20220820.message_actions ma
        ) as t2
        ON t1.user_id = t2.user_id AND t1.time = t2.time
        WHERE t2.user_id = 0 and (toDate(time) >= today() - 7 and toDate(time) <= today() - 1)
        GROUP BY time
        order by time"""
        only_feed = pandahouse.read_clickhouse(only_feed, connection=connection)

        only_msg = """
        SELECT count(distinct user_id) as uniq_user_id, time FROM (
          SELECT ma.user_id, toStartOfDay(toDateTime(ma.time)) AS time
          FROM simulator_20220820.message_actions ma
        ) as t1 LEFT JOIN (
          SELECT fa.user_id, toStartOfDay(toDateTime(fa.time)) as time
          FROM simulator_20220820.feed_actions fa
        ) as t2 ON t1.user_id = t2.user_id AND t1.time = t2.time
        WHERE t2.user_id = 0 and (toDate(time) >= today() - 7 and toDate(time) <= today() - 1)
        group by time
        order by time
        """
        only_msg = pandahouse.read_clickhouse(only_msg, connection=connection)

        # DAU графики
        fig, axs = plt.subplots(3, sharex=True, figsize=(12, 12))
        axs[0].plot(feed_and_msg['time'], feed_and_msg['uniq_user_id'], color='red')
        axs[1].plot(only_feed['time'], only_feed['uniq_user_id'], color='green')
        axs[2].plot(only_msg['time'], only_msg['uniq_user_id'], color='orange')

        axs[0].legend(['both feed and message'], prop={'size': 15})
        axs[1].legend(['only feed'], prop={'size': 15})
        axs[2].legend(['only message'], prop={'size': 15})

        axs[2].set(xlabel='Date')
        axs[0].set_title('DAU for 7 days')
        axs[0].grid(True)

        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'DAU_plot.png'
        plt.close()
        bot.sendPhoto(chat_id=chat_id, photo=plot_object)

        actions_per_user_feed = """
        SELECT countIf(user_id, action='like')/count(distinct user_id) as likes_per_user,
               countIf(user_id, action='view')/count(distinct user_id) as views_per_user,
               toDate(time) as time FROM simulator_20220820.feed_actions
        WHERE (toDate(time) >= today() - 7 and toDate(time) <= today() - 1)
        group by time
        order by time
        """
        actions_per_user_feed = pandahouse.read_clickhouse(actions_per_user_feed, connection=connection)

        ctr_7days = """
        SELECT round(countIf(user_id, action='like')/countIf(user_id, action='view'),2) as ctr, toDate(time) as date
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
        GROUP BY date
        """
        ctr_7days = pandahouse.read_clickhouse(ctr_7days, connection=connection)

        fig, axs = plt.subplots(3, sharex=True, figsize=(12, 12))
        axs[0].plot(actions_per_user_feed['time'], actions_per_user_feed['likes_per_user'], color='red')
        axs[1].plot(actions_per_user_feed['time'], actions_per_user_feed['views_per_user'], color='blue')
        axs[2].plot(ctr_7days['date'], ctr_7days['ctr'], color='green')

        axs[0].legend(['likes_per_user'], prop={'size': 15})
        axs[1].legend(['views_per_user'], prop={'size': 15})
        axs[2].legend(['ctr'], prop={'size': 15})

        axs[2].set(xlabel='Date')
        axs[0].set_title('Event per user - feed')
        axs[0].grid(True)

        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'feed_events_plot.png'
        plt.close()
        bot.sendPhoto(chat_id=chat_id, photo=plot_object)

        query_message = """
        WITH msg_received as (SELECT reciever_id,
                                     count(ma2.user_id) as cnt
                              FROM simulator_20220820.message_actions ma2
                              WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
                              GROUP BY reciever_id),

             num_of_receivers as (SELECT user_id,
                                         count(DISTINCT ma2.reciever_id) as cnt
                                  FROM simulator_20220820.message_actions ma2
                                  WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
                                  GROUP BY user_id),

             msg_sent as (SELECT user_id,
                                 count(ma2.reciever_id) as cnt
                          FROM simulator_20220820.message_actions ma2
                          WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
                          GROUP BY user_id),

             num_of_senders as (SELECT reciever_id, count(DISTINCT ma2.user_id) as cnt
                                FROM simulator_20220820.message_actions ma2
                                WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
                                GROUP BY reciever_id)

        SELECT DISTINCT count (distinct ma.user_id) as number_of_user_id,
                        sum(msg_received.cnt) as messages_received,
                        sum(num_of_receivers.cnt) as number_of_receivers,
                        sum(msg_sent.cnt) as messages_sent,
                        sum(num_of_senders.cnt) as number_of_senders,
                        sum(msg_sent.cnt)/count (distinct ma.user_id) as msg_sent_per_user,
                        sum(msg_received.cnt)/count (distinct ma.user_id) as msg_received_per_user,
                        sum(num_of_receivers.cnt)/count (distinct ma.user_id) as receivers_per_users,
                        toDate(ma.time) as event_date
        FROM simulator_20220820.message_actions ma
                 LEFT JOIN msg_received ON ma.user_id = msg_received.reciever_id
                 LEFT JOIN num_of_receivers ON ma.user_id = num_of_receivers.user_id
                 LEFT JOIN msg_sent ON ma.user_id = msg_sent.user_id
                 LEFT JOIN num_of_senders ON ma.user_id = num_of_senders.reciever_id
        WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
        group by event_date
        """
        message_table = pandahouse.read_clickhouse(query_message, connection=connection)

        fig, axs = plt.subplots(2, sharex=True, figsize=(12, 8))
        axs[0].plot(message_table['event_date'], message_table['msg_sent_per_user'])
        axs[0].plot(message_table['event_date'], message_table['msg_received_per_user'])
        axs[1].plot(message_table['event_date'], message_table['receivers_per_users'])

        axs[0].legend(['msg sent per user', 'msg received per user'], prop={'size': 10})
        axs[1].legend(['receivers per user'], prop={'size': 12})

        axs[1].set(xlabel='Date')
        axs[0].set_title('Event per user - messages')
        axs[0].grid(True)

        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'msg_events_plot.png'
        plt.close()
        bot.sendPhoto(chat_id=chat_id, photo=plot_object)

        dau_yesterday = """
        SELECT count(distinct user_id) as dau
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) = today() - 1
        """
        dau_yesterday = pandahouse.read_clickhouse(dau_yesterday, connection=connection)
        dau_yesterday = dau_yesterday.loc[0][0]

        likes_yesterday = """
        SELECT countIf(user_id, action='like') as likes
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) = today() - 1
        """
        likes_yesterday = pandahouse.read_clickhouse(likes_yesterday, connection=connection)
        likes_yesterday = likes_yesterday.loc[0][0]

        views_yesterday = """
        SELECT countIf(user_id, action='view') as views
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) = today() - 1
        """
        views_yesterday = pandahouse.read_clickhouse(views_yesterday, connection=connection)
        views_yesterday = views_yesterday.loc[0][0]

        message = f"События за вчерашний день: \n \
                    Просмотры = {views_yesterday}, \n \
                    Лайки = {likes_yesterday}, \n \
                    Отправленные сообщения = {message_table.iloc[0, 3]}, \n \
                    DAU новостей всего = {dau_yesterday}, \n \
                    DAU сообщений всего = {message_table.iloc[0, 0]}"

        bot.sendMessage(chat_id=chat_id, text=message)

    test_report()


eshishmarina_dag = eshishmarina_feed_news_dag()
