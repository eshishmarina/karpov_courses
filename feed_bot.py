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
    'start_date': datetime(2022, 9, 13),
}

# Интервал запуска DAG
schedule_interval = '0 11 * * *'


@dag(default_args=default_args, schedule_interval=schedule_interval, catchup=False)
def eshishmarina_feed_dag():
    @task()
    def daily_report():
        chat_id = 0
        bot = telegram.Bot(token='')

        # Данные для сообщения по метрикам за вчерашний день
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

        ctr_yesterday = """
        SELECT round(countIf(user_id, action='like')/countIf(user_id, action='view'),2) as ctr
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) = today() - 1
        """
        ctr_yesterday = pandahouse.read_clickhouse(ctr_yesterday, connection=connection)
        ctr_yesterday = ctr_yesterday.loc[0][0]

        message = f"Метрики за вчерашний день: \n \
                  DAU = {dau_yesterday}, \n \
                  Просмотры = {views_yesterday}, \n \
                  Лайки = {likes_yesterday}, \n \
                  CTR = {ctr_yesterday}"

        bot.sendMessage(chat_id=chat_id, text=message)

        # Данные для графиков
        dau_7days = """
        SELECT toDate(time) as date, count(distinct user_id) as dau
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
        GROUP BY toDate(time)
        """
        dau_7days = pandahouse.read_clickhouse(dau_7days, connection=connection)

        likes_7days = """
        SELECT toDate(time) as date, countIf(user_id, action='like') as likes
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
        GROUP BY toDate(time)
        """
        likes_7days = pandahouse.read_clickhouse(likes_7days, connection=connection)

        views_7days = """
        SELECT toDate(time) as date, countIf(user_id, action='view') as views
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
        GROUP BY toDate(time)
        """
        views_7days = pandahouse.read_clickhouse(views_7days, connection=connection)

        ctr_7days = """
        SELECT toDate(time) as date, round(countIf(user_id, action='like')/countIf(user_id, action='view'),2) as ctr
        FROM simulator_20220820.feed_actions
        WHERE toDate(time) >= today() - 7 and toDate(time) <= today() - 1
        GROUP BY toDate(time)
        """
        ctr_7days = pandahouse.read_clickhouse(ctr_7days, connection=connection)

        # Строим графики и задаем их параметры
        fig, axs = plt.subplots(4, sharex=True, figsize=(12, 12))
        axs[0].plot(dau_7days['date'], dau_7days['dau'], color='red')
        axs[1].plot(likes_7days['date'], likes_7days['likes'], color='green')
        axs[2].plot(views_7days['date'], views_7days['views'], color='orange')
        axs[3].plot(ctr_7days['date'], ctr_7days['ctr'])
        axs[0].legend(['dau'], prop={'size': 15})
        axs[1].legend(['likes'], prop={'size': 15})
        axs[2].legend(['views'], prop={'size': 15})
        axs[3].legend(['ctr'], prop={'size': 15})
        axs[3].set(xlabel='Date')
        axs[0].set_title('Metrics for 7 days')
        axs[0].grid(True)
        axs[1].grid(True)
        axs[2].grid(True)
        axs[3].grid(True)

        plot_object = io.BytesIO()
        plt.savefig(plot_object)
        plot_object.seek(0)
        plot_object.name = 'test_plot.png'
        plt.close()
        bot.sendPhoto(chat_id=chat_id, photo=plot_object)

    daily_report()


eshishmarina_dag = eshishmarina_feed_dag()
