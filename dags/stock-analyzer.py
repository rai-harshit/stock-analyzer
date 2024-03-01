import requests
import json
from datetime import datetime, timedelta
from airflow.decorators import task, dag

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
            print(df.head())
        print(f"Data processed from {input_file} and written to {output_file}")
    

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

    confirm_run_task = confirm_run()

    fetch_bse_data_task.set_downstream(process_bse_data_task)
    fetch_irctc_data_task.set_downstream(process_irctc_data_task)
    process_bse_data_task.set_downstream(confirm_run_task)
    process_irctc_data_task.set_downstream(confirm_run_task)

fetch_data_status = stock_analyzer()
