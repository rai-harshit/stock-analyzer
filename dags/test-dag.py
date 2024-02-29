from datetime import datetime, timedelta

from airflow.decorators import dag, task

default_args = {
    "owner":"root",
    "retires":1,
    "retry_delay":timedelta(60)
}

@dag(
    dag_id="test_dag",
    description="This is a test dag.",
    default_args=default_args,
    start_date=datetime(2024, 2, 27),
    schedule_interval="@daily"
)
def test_dag():
    @task
    def hello():
        print("Hello World!")
        return 1

    @task
    def dag_run():
        print("This is a DAG run via Airflow.")
        return 5

    @task
    def bye(a, b):
        print(a+b)
        print("Good Bye!")

    a = hello()
    b = dag_run()
    bye(a, b)

test_dag_run = test_dag()