#!/bin/bash

echo pwd=$(pwd)

echo ./download_dumps.sh
./download_dumps.sh

echo /app/create_db.py "$@"
/app/create_db.py "$@"
