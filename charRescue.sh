#!/bin/sh
fileName="xmlData.txt"
dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)

#AG starting area
ag1X="-398"
ag1Y="350"
ag1Z="-156"

#AG pinic area
ag2X="522"
ag2Y="406"
ag2Z="129"

#NS plaza
ns1X="-11"
ns1Y="291"
ns1Z="-123"

X=""
Y=""
Z=""

worldID=""

echo "Enter location: "
read LOC

echo "\n\nEnter account key: "
read KEY

if [ "$LOC" = "ag1" ];
then
	X=${ag1X}
	Y=${ag1Y}
	Z=${ag1Z}
	worldID="1100"
elif [ "$LOC" = "ag2" ];
then
	X=${ag2X}
	Y=${ag2Y}
	Z=${ag2Z}
	worldID="1100"
elif [ "$LOC" = "ns1" ];
then
	X=${ns1X}
	Y=${ns1Y}
	Z=${ns1Z}
	worldID="1200"
else
	echo "\n"
	echo "Invalid command $1"
	exit
fi

keyID=$(mysql -u ${dbuser} -p${passwd} -D ${dbname} -N -e "SELECT id FROM play_keys WHERE key_string = '$KEY';" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\n/g')
#echo ${keyID}
accountID=$(mysql -u ${dbuser} -p${passwd} -D ${dbname} -N -e "SELECT id FROM accounts WHERE play_key_id = '${keyID}';" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\n/g')
#echo ${accountID}

echo "\nChoose character"
mysql -u ${dbuser} -p${passwd} -D ${dbname} -e "SELECT id,name FROM charinfo WHERE account_id = '${accountID}';"

echo "\nEnter character ID: "
read ID

echo "\nPulling XML data for $ID..."
./pullCharXml.sh $ID

#echo "DEBUG! ${X} ${Y} ${Z} ${worldID}"

echo "\nEditing file..."
sed -i s/lzx=\"[0-9.-]*\"/lzx=\"${X}\"/g ${fileName} #Replace the lzx
sed -i s/lzy=\"[0-9.-]*\"/lzy=\"${Y}\"/g ${fileName} #Replace the lzy
sed -i s/lzz=\"[0-9.-]*\"/lzz=\"${Z}\"/g ${fileName} #Replace the lzz
sed -i s/tscene=\"[a-zA-Z]*\"/tscene=\"\"/g ${fileName} #Replace the tscene

sed -i s/lwid=\"[0-9]*\"/lwid=\"${worldID}\"/g ${fileName} #Replace the lwid

echo "\nWriting XML data back to database for $ID..."
./writeCharXml.sh $ID

echo "\n\nDone!"
