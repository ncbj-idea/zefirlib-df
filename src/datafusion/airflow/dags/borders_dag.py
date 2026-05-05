from airflow import DAG
from airflow.operators.python import PythonOperator

from datafusion.airflow.dags.utils import create_config_from_path
from datafusion.configs.borders_config import BordersConfig
from datafusion.configs.default_paths import get_airflow_config_absolute_path
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.runners.borders_runner import BordersRunner

default_args = {
    # "owner": "airflow",
    # "depends_on_past": False,
    # "retries": 1,
    # "retry_delay": timedelta(minutes=5),
}


def borders_runner_task(**kwargs) -> None:
    dag_run = kwargs.get("dag_run")
    if dag_run.conf:
        config_dict = dag_run.conf
        borders_config = BordersConfig.model_validate(config_dict)
    else:
        default_config_path = get_airflow_config_absolute_path() / "borders.json"
        borders_config = create_config_from_path(BordersConfig, default_config_path)
    BordersRunner(
        config=borders_config,
        engine=get_engine(),
        db_settings=DBSettings(),
    ).run()


with DAG(
    dag_id="borders_runner_dag",
    schedule=None,
):
    task = PythonOperator(
        task_id="load_borders_data",
        python_callable=borders_runner_task,
    )
