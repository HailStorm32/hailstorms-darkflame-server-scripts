#!/bin/sh
dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)

echo "\nEnter account key: "
read KEY

keyID=$(mysql -u ${dbuser} -p${passwd} -D ${dbname} -N -e "SELECT id FROM play_keys WHERE key_string = '$KEY';" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\n/g')
#echo ${keyID}
accountID=$(mysql -u ${dbuser} -p${passwd} -D ${dbname} -N -e "SELECT id FROM accounts WHERE play_key_id = '${keyID}';" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\n/g')
#echo ${accountID}


echo "\n\nLock[1] or unlock[2]?: "
read OPTION

if [ "$OPTION" = "1" ];
then
	mysql -u ${dbuser} -p${passwd} -D ${dbname} -e "UPDATE accounts SET locked = '1' WHERE id = '${accountID}';"
	echo "Locked account ${accountID}"
	exit
elif [ "$OPTION" = "2" ];
then
	mysql -u ${dbuser} -p${passwd} -D ${dbname} -e "UPDATE accounts SET locked = '0' WHERE id = '${accountID}';"
	echo "Unlocked account ${accountID}"
	exit
else
	echo "\n"
	echo "Invalid option $OPTION"
	exit
fi

