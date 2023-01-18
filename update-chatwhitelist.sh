#!/bin/sh

#Configure storeage information and whitelist name
whitelistName="chatplus_en_us.txt"
storageName="darkflame-storage"

echo "\n"
echo "Pulling list from storage..."

gsutil cp gs://${storageName}/${whitelistName} ${whitelistName} #Pull whitelist file from storage

if test -f "${whitelistName}"; then #Check and make sure file was pulled
	echo "Removing old whitelist..."
	
	rm ~/DarkflameServer/build/res/*.dcf #Remove compiled list
	rm ~/DarkflameServer/build/res/${whitelistName} #Remove old list

	echo "Moveing over new list"
	mv ${whitelistName} ~/DarkflameServer/build/res/ #Move over the new list

	echo "Done."
else
	echo "Whitelist file: $1 does not exsist! Exiting!"
fi

