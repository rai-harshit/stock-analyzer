import requests
import json
from datetime import datetime, timedelta
from airflow.decorators import task, dag
from airflow.providers.postgres.operators.postgres import PostgresOperator
import csv

default_args = {
    "owner":"root",
    "retires":1,
    "retry_delay":timedelta(60)
}

@dag(
    dag_id="stock_analyzer",
    description="This DAG fetches stock market data.",
    default_args=default_args,
    start_date=datetime(2024, 2, 28),
    schedule_interval="@daily"
)
def stock_analyzer():
    import pandas as pd
    import numpy as np
    import json
    def call_api_and_save_response(api_url, output_file):
        try:
            # Making the API call
            response = requests.get(api_url)
            response.raise_for_status()

            # Storing the response JSON in a file
            with open(output_file, 'w') as f:
                json.dump(response.json(), f, indent=4)

            print("API response saved successfully to", output_file)
        except requests.exceptions.RequestException as e:
            print("Error making API call:", e)

    def process_data(input_file, output_file):
        print(f"Reading {input_file} for processing.")
        with open(input_file) as f:
            json_data = json.load(f)
            time_series_data = json_data["Time Series (Daily)"]
            df = pd.DataFrame(time_series_data).T
            df.columns = ['open', 'high', 'low', 'close', 'volume']
            df = df.astype(float)
            df.index = pd.to_datetime(df.index)
            df.reset_index(inplace=True)
            df.rename(columns={'index': 'date'}, inplace=True)
            df.to_csv(output_file, index=False)
        print(f"Data processed from {input_file} and written to {output_file}")

    def insert_data_into_db(data_file_path, table_name):
        with open(data_file_path, "r") as csv_file:
            csv_reader = csv.reader(csv_file)
            next(csv_reader)  # Skip header row (assuming the file has a header)
            data_list = list(csv_reader)
            insert_stmt = f"""
                INSERT INTO {table_name} (date, open, high, low, close, volume) VALUES (%s, %s, %s, %s, %s, %s)
            """
            values = [", ".join(["%s"] * len(data_list[0])) for _ in data_list]
            full_stmt = insert_stmt + ", ".join(values)
            print(full_stmt)
            print([row for sublist in data_list for row in sublist])
            # Execute the statement with prepared data
            PostgresOperator(
                task_id="insert_data",
                postgres_conn_id="psql-aiven",
                sql=full_stmt,
                parameters=[row for sublist in data_list for row in sublist],
                autocommit=True,
            )

    

    @task(task_id="fetch_bse_data")
    def fetch_bse_data(api_url, output_file):
        return call_api_and_save_response(api_url, output_file)
    
    @task(task_id="fetch_irctc_data")
    def fetch_irctc_data(api_url, output_file):
        return call_api_and_save_response(api_url, output_file)

    @task(task_id="process_bse_data")
    def process_bse_data(input_file, output_file):
        process_data(input_file, output_file)

    @task(task_id="process_irctc_data")
    def process_irctc_data(input_file, output_file):
        process_data(input_file, output_file)

    @task(task_id="confirm_run")
    def confirm_run():
        print("All the tasks completed successfully!")

    @task(task_id="insert_bse_data_into_db")
    def insert_bse_data_into_db(data_file_path, table_name):
        insert_data_into_db(data_file_path, table_name)

    @task(task_id="insert_irctc_data_into_db")
    def insert_irctc_data_into_db(data_file_path, table_name):
        insert_data_into_db(data_file_path, table_name)

    fetch_bse_data_task = fetch_bse_data(
        "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=BSE&outputsize=full&apikey=XGLSH8DND0HHFWKK",
        "/opt/airflow/data/bse_data.json"
    )
    fetch_irctc_data_task = fetch_irctc_data(
        "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IRCTC.BSE&outputsize=full&apikey=XGLSH8DND0HHFWKK",
        "/opt/airflow/data/irctc_data.json"
    )
    process_bse_data_task = process_bse_data("/opt/airflow/data/bse_data.json","/opt/airflow/data/bse_processed.csv")
    process_irctc_data_task = process_irctc_data("/opt/airflow/data/irctc_data.json","/opt/airflow/data/irctc_processed.csv")

    insert_bse_data_into_postgres_task = insert_bse_data_into_db("/opt/airflow/data/bse_processed.csv","bse_stock_data")

    insert_irctc_data_into_postgres_task = insert_irctc_data_into_db("/opt/airflow/data/irctc_processed.csv","irctc_stock_data")

    confirm_run_task = confirm_run()

    fetch_bse_data_task >> process_bse_data_task >> insert_bse_data_into_postgres_task >> confirm_run_task
    fetch_irctc_data_task >> process_irctc_data_task >> insert_irctc_data_into_postgres_task >> confirm_run_task

    return dag

fetch_data_status = stock_analyzer()

