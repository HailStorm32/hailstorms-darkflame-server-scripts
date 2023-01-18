#!/bin/bash
dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)

echo "Backing up Database"

sec=$(date +"%s")

echo $sec

mysqldump -u ${dbuser} ${dbname} --result-file=/mnt/disks/dbDisk/darkflameDB_bkp_`date +"%Y%m%d"`_${sec}.sql -p${passwd}

echo "Copying to storage server"
gsutil cp /mnt/disks/dbDisk/darkflameDB_bkp_`date +"%Y%m%d"`_${sec}.sql gs://darkflame-storage/darkflameDB_bkp_`date +"%Y%m%d"`_${sec}.sql

echo "Removing local file"
rm /mnt/disks/dbDisk/darkflameDB_bkp_`date +"%Y%m%d"`_${sec}.sql

echo "Done."
