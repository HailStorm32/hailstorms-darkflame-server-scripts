echo "Stopping server..."
screen -S darkflame-server -X at 0 stuff '^C'
echo "Done."

#echo "Stopping player counter"
#sudo systemctl stop lu-discord-update
#echo "Done."
