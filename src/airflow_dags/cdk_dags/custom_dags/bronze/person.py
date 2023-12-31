from __future__ import annotations

import logging
import sys
import tempfile
import time
from pprint import pprint

import pendulum

from airflow import DAG
from airflow.decorators import task
from airflow.operators.python import ExternalPythonOperator, PythonVirtualenvOperator, is_venv_installed
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator
from datetime import datetime
log = logging.getLogger(__name__)



with DAG("landing_person",start_date=datetime(2023,5,27),
    schedule_interval="@daily", catchup=False) as dag:
    run_spark_job = SparkSubmitOperator(
        task_id = "run_spark_job",
        application = "/opt/bitnami/spark/apps/landing/person.py",
        conn_id = "spark_conn",
        verbose = True
    )