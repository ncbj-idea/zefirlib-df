from airflow import DAG
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

with DAG(
    dag_id="master_runner_dag",
    schedule_interval=None,
) as dag:
    trigger_bdot = TriggerDagRunOperator(
        task_id="trigger_bdot_dag",
        trigger_dag_id="bdot_runner_dag",
    )
    trigger_borders = TriggerDagRunOperator(
        task_id="trigger_borders_dag",
        trigger_dag_id="borders_runner_dag",
    )
    trigger_kiut = TriggerDagRunOperator(
        task_id="trigger_kiut_dag",
        trigger_dag_id="kiut_runner_dag",
    )
    trigger_ceeb = TriggerDagRunOperator(
        task_id="trigger_ceeb_dag",
        trigger_dag_id="ceeb_runner_dag",
    )
    trigger_address = TriggerDagRunOperator(
        task_id="trigger_address_dag",
        trigger_dag_id="address_runner_dag",
    )
    trigger_pvgis = TriggerDagRunOperator(
        task_id="trigger_pvgis_dag",
        trigger_dag_id="pvgis_runner_dag",
    )

    (trigger_bdot >> trigger_borders >> trigger_kiut >> trigger_ceeb >> trigger_address >> trigger_pvgis)
