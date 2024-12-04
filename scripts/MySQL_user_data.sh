#!/bin/bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install python3 python3-pip -y
## Install MySQL
sudo apt-get install mysql-server -y
# Start MySQL service
sudo systemctl start mysql
# Enable MySQL to start on boot
sudo systemctl enable mysql
# Run the MySQL secure installation script (interactive by default)
sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH 'mysql_native_password' BY '';"
sudo mysql -e "DELETE FROM mysql.user WHERE User='';"
sudo mysql -e "DROP DATABASE IF EXISTS test;"
sudo mysql -e "DELETE FROM mysql.db WHERE Db='test' OR Db='test\\_%';"
sudo mysql -e "FLUSH PRIVILEGES;"

# Download and set up Sakila database
sudo apt-get install unzip -y
cd /home/ubuntu
wget https://downloads.mysql.com/docs/sakila-db.zip

unzip sakila-db.zip -d /home/ubuntu/
# Create the database structure
sudo mysql -u root -e "source /home/ubuntu/sakila-db/sakila-schema.sql"
# Populate the database
sudo mysql -u root -e "source /home/ubuntu/sakila-db/sakila-data.sql"
# Confirm
sudo mysql -u root -e "USE sakila; SHOW FULL TABLES; SELECT COUNT(*) FROM film; SELECT COUNT(*) FROM film_text;"

## sysbench verification
# Install sysbench
sudo apt-get install sysbench -y
# Prepare the DB for sysbench
sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user="root" --mysql-password="" prepare
# Run sysbench
sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user="root" --mysql-password="" run

## Make a new user to access SQL Server
sudo sed -i "s/^bind-address.*/bind-address = 0.0.0.0/" /etc/mysql/mysql.conf.d/mysqld.cnf
sudo systemctl restart mysql
sudo mysql -e "CREATE USER 'proxy_user'@'%' IDENTIFIED BY '98486293';"
sudo mysql -e "GRANT SELECT, INSERT, UPDATE, DELETE ON *.* TO 'proxy_user'@'%';"
sudo mysql -e "FLUSH PRIVILEGES;"
