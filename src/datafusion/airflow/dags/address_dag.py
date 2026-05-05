from airflow import DAG
from airflow.operators.python import PythonOperator

from datafusion.airflow.dags.utils import create_config_from_path
from datafusion.configs.address_config import AddressConfig
from datafusion.configs.default_paths import get_airflow_config_absolute_path
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.runners.address_runner import AddressRunner


def address_runner_task(**kwargs) -> None:
    dag_run = kwargs.get("dag_run")
    if dag_run.conf:
        config_dict = dag_run.conf
        address_config = AddressConfig.model_validate(config_dict)
    else:
        default_config_path = get_airflow_config_absolute_path() / "address.json"
        address_config = create_config_from_path(AddressConfig, default_config_path)
    AddressRunner(
        config=address_config,
        engine=get_engine(),
        db_settings=DBSettings(),
    ).run()


with DAG(
    dag_id="address_runner_dag",
    schedule_interval=None,
):
    task = PythonOperator(
        task_id="load_prg_data",
        python_callable=address_runner_task,
    )
