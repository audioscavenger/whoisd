#!/bin/bash

# Debug
echo pwd=$(pwd)
echo whoami=$(id)

echo ./download_dumps.sh
./download_dumps.sh

python --version
# python -c "import sqlalchemy; print('SQLAlchemy',sqlalchemy.__version__)"
pip freeze | egrep -wi "netaddr|psycopg|psycopg-c|psycopg-pool|sqlalchemy"

echo /app/create_db.py "$@"
/app/create_db.py "$@"
