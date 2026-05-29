"""
Main Airflow DAG — Economic Analysis Pipeline
Orchestrates: collect → validate → transform → ml → notify

For demo: this DAG runs in Amazon MWAA (Managed Airflow).
Cost-saving: MWAA Small = ~$0.49/hr. For demo, deploy on-demand and pause when not in use.
Alternative: use AWS Step Functions (no persistent cost) — see docs/step_functions_alternative.md
"""
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.empty import EmptyOperator
from airflow.providers.amazon.aws.operators.lambda_function import LambdaInvokeFunctionOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.providers.amazon.aws.sensors.s3 import S3KeySensor

# ── DAG defaults ──────────────────────────────────────────────────────────
default_args = {
    "owner":            "data-engineering",
    "retries":          2,
    "retry_delay":      timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "email_on_failure": False,  # use SNS instead
    "depends_on_past":  False,
}

with DAG(
    dag_id="econ_pipeline_daily",
    description="Daily economic data ingestion and processing",
    schedule="0 22 * * 1-5",  # weekdays 5pm ET (after market close)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["econ", "production", "daily"],
    default_args=default_args,
) as dag:

    start = EmptyOperator(task_id="start")

    # ── Layer 1: Collect from all sources in parallel ─────────────────────
    collect_fred = LambdaInvokeFunctionOperator(
        task_id="collect_fred",
        function_name="econ-pipeline-{{ var.value.environment }}-fred-collector",
        payload="{}",
        aws_conn_id="aws_default",
    )

    collect_market = LambdaInvokeFunctionOperator(
        task_id="collect_market",
        function_name="econ-pipeline-{{ var.value.environment }}-yfinance-collector",
        payload="{}",
        aws_conn_id="aws_default",
    )

    collect_bls = LambdaInvokeFunctionOperator(
        task_id="collect_bls",
        function_name="econ-pipeline-{{ var.value.environment }}-bls-collector",
        payload="{}",
        aws_conn_id="aws_default",
    )

    collect_forex = LambdaInvokeFunctionOperator(
        task_id="collect_forex",
        function_name="econ-pipeline-{{ var.value.environment }}-forex-collector",
        payload="{}",
        aws_conn_id="aws_default",
    )

    # ── Layer 2: Sense that raw files landed in S3 ────────────────────────
    sense_raw_fred = S3KeySensor(
        task_id="sense_raw_fred",
        bucket_name="{{ var.value.s3_bucket_raw }}",
        bucket_key="raw/fred/{{ ds_nodash[:4] }}/{{ ds_nodash[4:6] }}/{{ ds_nodash[6:] }}/",
        wildcard_match=True,
        timeout=300,
        poke_interval=30,
        aws_conn_id="aws_default",
    )

    # ── Layer 3: Transform raw → clean (Glue Python Shell) ────────────────
    transform_silver = GlueJobOperator(
        task_id="transform_silver",
        job_name="econ-pipeline-silver-transform",
        script_args={
            "--raw_bucket":   "{{ var.value.s3_bucket_raw }}",
            "--clean_bucket": "{{ var.value.s3_bucket_clean }}",
            "--date_str":     "{{ ds[:4] }}/{{ ds[5:7] }}/{{ ds[8:10] }}",
        },
        aws_conn_id="aws_default",
    )

    # ── Layer 4: Data quality gate ────────────────────────────────────────
    quality_check = LambdaInvokeFunctionOperator(
        task_id="quality_check",
        function_name="econ-pipeline-{{ var.value.environment }}-quality-check",
        payload='{"date": "{{ ds }}"}',
        aws_conn_id="aws_default",
    )

    # ── Layer 5: ML — correlation + forecasting ───────────────────────────
    run_correlations = LambdaInvokeFunctionOperator(
        task_id="run_correlations",
        function_name="econ-pipeline-{{ var.value.environment }}-correlation-engine",
        payload="{}",
        aws_conn_id="aws_default",
    )

    run_forecasts = LambdaInvokeFunctionOperator(
        task_id="run_forecasts",
        function_name="econ-pipeline-{{ var.value.environment }}-forecasting",
        payload="{}",
        aws_conn_id="aws_default",
    )

    end = EmptyOperator(task_id="end", trigger_rule="all_done")

    # ── DAG dependency graph ──────────────────────────────────────────────
    start >> [collect_fred, collect_market, collect_bls, collect_forex]
    collect_fred >> sense_raw_fred >> transform_silver
    [collect_market, collect_bls, collect_forex] >> transform_silver
    transform_silver >> quality_check >> [run_correlations, run_forecasts]
    [run_correlations, run_forecasts] >> end
