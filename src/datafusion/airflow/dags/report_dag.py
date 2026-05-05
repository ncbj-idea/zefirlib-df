from airflow import DAG
from airflow.operators.python import PythonOperator

from datafusion.airflow.dags.utils import create_config_from_path
from datafusion.configs.default_paths import get_airflow_config_absolute_path
from datafusion.configs.report_config import ReportConfig
from datafusion.database.session import get_engine
from datafusion.runners.report_runner import ReportRunner


def report_runner_task(**kwargs) -> None:
    dag_run = kwargs.get("dag_run")
    if dag_run.conf:
        config_dict = dag_run.conf
        report_config = ReportConfig.model_validate(config_dict)
    else:
        default_config_path = get_airflow_config_absolute_path() / "report.json"
        report_config = create_config_from_path(ReportConfig, default_config_path)
    ReportRunner(
        config=report_config,
        engine=get_engine(),
    ).run()


with DAG(
    dag_id="report_runner_dag",
    schedule_interval=None,
):
    task = PythonOperator(
        task_id="generate_report",
        python_callable=report_runner_task,
    )
