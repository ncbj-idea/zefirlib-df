# !/bin/bash

VENV=".venv"
if [[ "$OSTYPE" == "win32" ]]; then
    VENV_ACTIVATE=".venv/Scripts/activate"
else
    VENV_ACTIVATE=".venv/bin/activate"
fi

echo "Creating virtual environment..."
python -m venv "$VENV"

echo "Activating virtual environment..."
source $VENV_ACTIVATE && pip install --upgrade pip && pip install .
echo "Setup complete."

# Create .env file which contain all environment variables
ENV_FILE=".env"

# The following step is used to create environment variables for the project. 
# The number of variables is larger than in template.env because the script is prepared for 
# later extensions that can be implemented
cp template.env $ENV_FILE
echo "Environment variables have been written to $ENV_FILE"

# Up the container with postgres database
export $(grep -v '^#' $ENV_FILE | xargs) && docker compose up db -d
echo "Database has been set"

sleep 5
# Apply migration scripts to bring the database schema up to the last version
source $VENV_ACTIVATE && alembic upgrade head
echo "Migrations applied"

# source $VENV_ACTIVATE && bdot -c config.yml
# source $VENV_ACTIVATE && borders -c config.yml
# source $VENV_ACTIVATE && kiut -c config.yml
# source $VENV_ACTIVATE && ceeb -c config.yml
# source $VENV_ACTIVATE && prg -c config.yml
# source $VENV_ACTIVATE && pvgis -c config.yml
# source $VENV_ACTIVATE && pvgis_merger -c config.yml
# source $VENV_ACTIVATE && report -c config.yml
# source $VENV_ACTIVATE && merge -c config.yml
# source $VENV_ACTIVATE && postprocessing 

echo "Report and merged data files saved to output folder"
