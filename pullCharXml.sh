#!/bin/sh
#Enter server database info
fileName="xmlData.txt"
dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)

mysql -u ${dbuser} -p${passwd} -D ${dbname} -N  -e "SELECT xml_data FROM charxml WHERE id = '$1';" > ${fileName} #Get the xml data from the database

echo "\n"
echo "Done! Coppied xml data for user $1"


