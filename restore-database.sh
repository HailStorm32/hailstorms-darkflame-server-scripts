#!/bin/sh

#Configure databse and storeage information
dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)
storageName="darkflame-storage"

echo "\n"
echo "Pulling backup from storage..."

gsutil cp gs://${storageName}/$1 $1 #Pull backup file from storage

if test -f "$1"; then #Check and make sure file was pulled
	echo "Restoring backup..."
	
	mysql -u ${dbuser} -p ${dbname} < $1 #Restore from database from backup

	rm $1 #remove the backup file

	echo "Done."
else
	echo "Backup file: $1 does not exsist! Exiting!"
fi

