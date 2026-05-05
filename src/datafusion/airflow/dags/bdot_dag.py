from airflow import DAG
from airflow.operators.python import PythonOperator

from datafusion.airflow.dags.utils import create_config_from_path
from datafusion.configs.bdot_config import BDOTConfig
from datafusion.configs.default_paths import get_airflow_config_absolute_path
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.runners.bdot_runner import BDOTRunner


def bdot_runner_task(**kwargs) -> None:
    dag_run = kwargs.get("dag_run")

    if dag_run.conf:
        config_dict = dag_run.conf
        bdot_config = BDOTConfig.model_validate(config_dict)
    else:
        default_config_path = get_airflow_config_absolute_path() / "bdot.json"
        bdot_config = create_config_from_path(BDOTConfig, default_config_path)
    BDOTRunner(
        config=bdot_config,
        engine=get_engine(),
        db_settings=DBSettings(),
    ).run()


with DAG(
    dag_id="bdot_runner_dag",
    schedule_interval=None,
):
    task = PythonOperator(
        task_id="load_bdot_data",
        python_callable=bdot_runner_task,
    )
