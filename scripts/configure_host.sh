#!/bin/bash

sudo apt -y install curl git htop mc wget vlc doublecmd-qt

if ! [ -x "$(command -v realpath)" ]; then
   sudo apt -y update
   sudo apt install -y coreutils
fi

if ! [ -x "$(command -v psql)" ]; then
    echo "psql could not be found"
    #sudo -s -- <<DOF
    sudo echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
    sudo apt -y update
    sudo apt -y install postgresql-14 postgresql-client-14 postgresql-contrib-14 postgresql-server-dev-14
    sudo sed -E -i 's/(local.*all.*)postgres(.*)peer/\1all\2trust/g' /etc/postgresql/14/main/pg_hba.conf
    sudo sed -E -i 's/(local.*all.*all.*peer)/# \1/g' /etc/postgresql/14/main/pg_hba.conf
    sudo sed -E -i 's/(host.*all.*all.*)127.0.0.1\/32(.*)scram-sha-256/\10.0.0.0\/0\2trust/g' /etc/postgresql/14/main/pg_hba.conf
    sudo sed -E -i 's/(host.*all.*all.*)127.0.0.1\/32(.*)peer/\127.0.0.1\/0\2trust/g' /etc/postgresql/14/main/pg_hba.conf
    sudo sed -E -i 's/#(listen_addresses = \x27)localhost/\1\*/g' /etc/postgresql/14/main/postgresql.conf
    sudo service postgresql start
    #sudo echo "service postgresql start" >> /etc/bash.bashrc
    #DOF
    echo "Postgres has been installed"
else
    echo "Postgres has been found"
fi

if psql -U postgres -lqt | cut -d \| -f 1 | grep -qw evil_eye_db; then
    # database exists
    # $? is 0
    echo "Postgres has been installed and database exists"
else
    psql -U postgres -c 'create database evil_eye_db;'
    psql -U postgres evil_eye_db < ./db_dump.txt
    echo "evil_eye_db database has been created"
fi