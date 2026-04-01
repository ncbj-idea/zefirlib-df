#!/bin/bash

set -e
echo "Creating database $POSTGRES_DB_AIRFLOW with owner $POSTGRES_USER..."


psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
  CREATE DATABASE $POSTGRES_DB_AIRFLOW OWNER $POSTGRES_USER;
EOSQL

echo "Database $POSTGRES_DB_AIRFLOW created succesfully."
