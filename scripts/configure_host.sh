#!/bin/bash

sudo apt -y install curl git htop mc wget vlc doublecmd-qt

if ! [ -x "$(command -v realpath)" ]; then
   sudo apt -y update
   sudo apt install -y coreutils
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

psql_as_postgres() {
    sudo -u postgres psql "$@"
}

ensure_postgres_running() {
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl is-active --quiet postgresql; then
            return 0
        fi
        echo "Starting PostgreSQL service..."
        sudo systemctl start postgresql
        return $?
    fi

    if sudo service postgresql status >/dev/null 2>&1; then
        return 0
    fi
    echo "Starting PostgreSQL service..."
    sudo service postgresql start
}

if ! [ -x "$(command -v psql)" ]; then
    echo "psql could not be found"
    #sudo -s -- <<DOF
    sudo echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
    sudo apt -y update
    sudo apt -y install postgresql-14 postgresql-client-14 postgresql-contrib-14 postgresql-server-dev-14
    ensure_postgres_running
    #sudo echo "service postgresql start" >> /etc/bash.bashrc
    #DOF
    echo "Postgres has been installed"
else
    echo "Postgres has been found"
fi

ensure_postgres_running

if psql_as_postgres -lqt | cut -d \| -f 1 | grep -qw evil_eye_db; then
    # database exists
    # $? is 0
    echo "Postgres has been installed and database exists"
else
    psql_as_postgres -c 'create database evil_eye_db;'
    psql_as_postgres evil_eye_db < "${SCRIPT_DIR}/../db_dump.txt"
    echo "evil_eye_db database has been created"
fi