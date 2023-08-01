echo "Linking..."
ln -v approve_all.sh ~/
ln -v charRescue.sh ~/
ln -v lockAccount.sh ~/
ln -v pullCharXml.sh ~/
ln -v start__Server.sh ~/
ln -v update-chatwhitelist.sh ~/
ln -v backupDB.sh ~/
ln -v getCharInfo.sh ~/
ln -v restore-database.sh ~/
ln -v stop__Server.sh ~/
ln -v writeCharXml.sh ~/

echo "Copying over settings file.."
cp settings/playerCntSettings_OG.py ./playerCntSettings.py
cp settings/charXmlPullerSettings_OG.py ./charXmlPullerSettings.py

echo "Done."
