#!/bin/sh
#Enter server database info
dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)
fileName="xmlData.txt"

#Create backup of database
mysqldump ${dbname}  -u ${dbuser} -p${passwd} --result-file=$HOME/deleteMe.sql

echo "\nConfirm write by entering [yes]: "
read CONFIRM

if [ "$CONFIRM" = "yes" ];
then
	#Move xml file to where mysql can read it
	sudo cp ${fileName} /mnt/disks/dbDisk/mysql/${dbname}/

	sudo chown mysql:mysql /mnt/disks/dbDisk/mysql/${dbname}/${fileName} 	#Change ownership of file to mysql

	#Write to database
	mysql -u ${dbuser} -p${passwd} -D ${dbname} -e "UPDATE charxml SET xml_data = LOAD_FILE('/mnt/disks/dbDisk/mysql/${dbname}/${fileName}') WHERE id = '$1';"  #Write the file to the database

	echo "\n"
	echo "Done! Wrote xml data for user $1" 
else
	echo "\nNo data written\n"
	echo "Exiting..."
	exit
fi
