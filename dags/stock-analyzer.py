import requests
import json
from datetime import datetime, timedelta
from airflow.decorators import task, dag
from airflow.hooks.postgres_hook import PostgresHook
import csv
from itertools import chain
import os

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
    import json

    @task(task_id = "fetch_stock_data")
    def fetch_stock_data(stock_symbols: list[str], output_dir: str):
        try:
            for stock_symbol in stock_symbols:
                api_url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={stock_symbol}&outputsize=full&apikey=XGLSH8DND0HHFWKK"
                # Making the API call
                response = requests.get(api_url)
                response.raise_for_status()

                # Storing the response JSON in a file
                output_file = f"{output_dir}/{stock_symbol}.json"
                with open(output_file , 'w') as f:
                    json.dump(response.json(), f, indent=4)

                print("API response saved successfully to", output_file)
        except requests.exceptions.RequestException as e:
            print("Error making API call:", e)

    @task(task_id="convert_json_to_csv")
    def convert_json_to_csv(stock_symbols: list[str], input_dir: str, output_dir: str):
        for stock_symbol in stock_symbols:
            input_file = f"{input_dir}/{stock_symbol}.json"
            output_file = f"{output_dir}/{stock_symbol}.csv"
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
                df["symbol"] = stock_symbol
                df.to_csv(output_file, index=False)
            print(f"Data processed from {input_file} and written to {output_file}")

    @task(task_id="calculate_delta")
    def calculate_delta(stock_symbols: list[str], stage_dir, delta_dir):
        for stock_symbol in stock_symbols:
            stage_file = f"{stage_dir}/{stock_symbol}.csv"
            delta_file = f"{delta_dir}/{stock_symbol}.csv"
            df_stage = pd.read_csv(stage_file)
            if not os.path.exists(delta_file):
                df_new_delta = df_stage
            else:
                df_delta = pd.read_csv(delta_file)
                max_date_delta = df_delta['date'].max()
                df_new_delta = df_stage[df_stage['date_column'] > max_date_delta]
            df_new_delta.to_csv(delta_file, index=False)

    @task(task_id="calculate_derived_fields")
    def calculate_derived_fields(stock_symbols, delta_dir, ingestion_dir):
        for stock_symbol in stock_symbols:
            df_delta = pd.read_csv(f"{delta_dir}/{stock_symbol}.csv")
            df_delta["pct_change"] = (df_delta["close"] - df_delta["open"])/df_delta["open"]
            df_delta.to_csv(f"{ingestion_dir}/{stock_symbol}.csv", index=False)

    @task(task_id="ingenst_data_into_db")
    def ingest_data_into_db(stock_symbols, ingestion_dir, table_name):
        for stock_symbol in stock_symbols:
            with open(f"{ingestion_dir}/{stock_symbol}.csv", "r") as csv_file:
                csv_reader = csv.reader(csv_file)
                next(csv_reader)
                data = list(csv_reader)

                # Prepare INSERT statement with placeholders
                insert_stmt = f"""
                    INSERT INTO {table_name} (date, open, high, low, close, volume, ticker, pct_change) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """

                # Efficiently unpack data using itertools.chain.from_iterable
                rows = []
                for i in range(0, len(data), 8):
                    rows.append(data[i : i + 8])

                postgres_hook = PostgresHook(postgres_conn_id="psql-aiven")
                for outer_list in data:
                    postgres_hook.run(insert_stmt, autocommit=True, parameters=outer_list)


    stock_symbols = ["NIFTYBEES.BSE","IRCTC.BSE"]
    root_dir = "/opt/airflow/data"
    raw_dir = f"{root_dir}/raw"
    stage_dir = f"{root_dir}/stage"
    delta_dir = f"{root_dir}/delta"
    ingestion_dir = f"{root_dir}/ingestion"
    
    fetch_stock_data_task = fetch_stock_data(
        stock_symbols, raw_dir
    )

    convert_json_to_csv_task = convert_json_to_csv(
        stock_symbols, raw_dir, stage_dir
    )

    calculate_delta_task = calculate_delta(
        stock_symbols, stage_dir, delta_dir
    )

    calculate_derived_fields_task = calculate_derived_fields(
        stock_symbols, delta_dir, ingestion_dir
    )

    ingest_data_into_db_task = ingest_data_into_db(stock_symbols, ingestion_dir, "stock_data")

    fetch_stock_data_task >> convert_json_to_csv_task >> calculate_delta_task >> calculate_derived_fields_task >> ingest_data_into_db_task

    return dag

fetch_data_status = stock_analyzer()

