#!/bin/sh
dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)

#Approves each players pending character name
echo "\nApproving character names"
mysql -u ${dbuser} -p -e "USE $dbname; UPDATE charinfo SET name = pending_name WHERE pending_name != '' AND needs_rename = '0';" #Set the player's name to their pending name
mysql -u ${dbuser} -p${passwd} -e "USE $dbname; UPDATE charinfo SET pending_name = '' WHERE pending_name != '' AND needs_rename = '0';" #Set the player's pending name to an empty string

echo "\nApproving pet names"
#Approve all pet names
mysql -u ${dbuser} -p -e "USE $dbname; UPDATE pet_names SET approved = '2' WHERE approved != '0';"

#Approve all player properties
#mysql -u ${dbuser} -p -e "USE $dbname; UPDATE properties SET mod_approved=1;"

echo "\nDone"
