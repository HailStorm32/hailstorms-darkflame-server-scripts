dbInfoPath=$HOME"/dbInfo.txt"
dbname=$(sed -n 1p $dbInfoPath)
dbuser=$(sed -n 2p $dbInfoPath)
passwd=$(sed -n 3p $dbInfoPath)

echo "starting server..."
screen -dmS darkflame-server bash -c "cd ~/DarkflameServer/build/; ./MasterServer"
echo "done."


echo "cleaning playercount..."
mysql -u ${dbuser} -p${passwd} -D ${dbname} -e "DELETE from activity_log WHERE time > UNIX_TIMESTAMP(now() - interval 24 hour);" #remove last 24hrs of activity log 
echo "done."

#echo "starting player counter..."
#sudo systemctl start lu-discord-update
#echo "done."
