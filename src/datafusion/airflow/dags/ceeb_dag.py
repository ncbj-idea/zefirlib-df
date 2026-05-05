from airflow import DAG
from airflow.operators.python import PythonOperator

from datafusion.airflow.dags.utils import create_config_from_path
from datafusion.configs.ceeb_config import CEEBConfig
from datafusion.configs.default_paths import get_airflow_config_absolute_path
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.runners.ceeb_runner import CEEBRunner


def ceeb_runner_task(**kwargs) -> None:
    dag_run = kwargs.get("dag_run")
    if dag_run.conf:
        config_dict = dag_run.conf
        ceeb_config = CEEBConfig.model_validate(config_dict)
    else:
        default_config_path = get_airflow_config_absolute_path() / "ceeb.json"
        ceeb_config = create_config_from_path(CEEBConfig, default_config_path)
    CEEBRunner(
        config=ceeb_config,
        engine=get_engine(),
        db_settings=DBSettings(),
    ).run()


with DAG(
    dag_id="ceeb_runner_dag",
    schedule=None,
):
    task = PythonOperator(
        task_id="load_ceeb_data",
        python_callable=ceeb_runner_task,
    )
