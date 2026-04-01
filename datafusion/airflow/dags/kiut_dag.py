from airflow import DAG
from airflow.operators.python import PythonOperator

from datafusion.airflow.dags.utils import create_config_from_path
from datafusion.configs.default_paths import get_airflow_config_absolute_path
from datafusion.configs.kiut_config import KIUTConfig
from datafusion.database.initialize import initialize_kiut_util_database
from datafusion.database.session import get_engine
from datafusion.runners.kiut_runner import KIUTRunner


def kiut_runner_task(**kwargs) -> None:
    dag_run = kwargs.get("dag_run")
    if dag_run.conf:
        config_dict = dag_run.conf
        kiut_config = KIUTConfig.model_validate(config_dict)
    else:
        default_config_path = get_airflow_config_absolute_path() / "kiut.json"
        kiut_config = create_config_from_path(KIUTConfig, default_config_path)
    engine = get_engine()
    initialize_kiut_util_database(db_engine=engine, kiut_config=kiut_config)
    KIUTRunner(
        config=kiut_config,
        engine=engine,
    ).run()


with DAG(
    dag_id="kiut_runner_dag",
    schedule=None,
):
    task = PythonOperator(
        task_id="load_kiut_data",
        python_callable=kiut_runner_task,
    )
