from airflow import DAG
from airflow.operators.python import PythonOperator

from datafusion.airflow.dags.utils import create_config_from_path
from datafusion.configs.default_paths import get_airflow_config_absolute_path
from datafusion.configs.pvgis_config import PVGISConfig
from datafusion.database.db_settings import DBSettings
from datafusion.database.session import get_engine
from datafusion.runners.pvgis_runner import PVGISRunner


def pvgis_runner_task(**kwargs) -> None:
    dag_run = kwargs.get("dag_run")
    if dag_run.conf:
        config_dict = dag_run.conf
        pvgis_config = PVGISConfig.model_validate(config_dict)
    else:
        default_config_path = get_airflow_config_absolute_path() / "pvgis.json"
        pvgis_config = create_config_from_path(PVGISConfig, default_config_path)
    PVGISRunner(
        config=pvgis_config,
        engine=get_engine(),
        db_settings=DBSettings(),
    ).run()


with DAG(
    dag_id="pvgis_runner_dag",
    schedule_interval=None,
):
    task = PythonOperator(
        task_id="load_pvgis_data",
        python_callable=pvgis_runner_task,
    )
