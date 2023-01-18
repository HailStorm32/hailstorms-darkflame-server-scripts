


# Intro
These are the scripts I used for my darkflame LU server instance that was hosted on Google Cloud. Some of these scripts will need to be edited to work properly. I have included a brief rundown of what each script does below.
<br>

## Setup
All the bash scripts pull from a file named `dbInfo.txt` located in the home directory. This file contains the credentials needed to access the server database. You will need to create the file in the home directory and fill it out the following way.
```
databaseName
databaseUserName
databasePassword
```

<br>
<br>

## Script Descriptions

<br>

## approve_all.sh
#### Description:
Approves all pending usernames and pet names. Can be edited to also approve all pending properties.

<br>

## backupDB.sh<br>
#### Description:

Backs up the database to a Google Cloud storage bucket.  

> This script will need to be edited to work properly for your environment

<br>

## charRescue.sh<br>
#### Description:
Rescues a stuck player by modifying their xml file and playing them in a predetermined world and location.

#### Use:
1. Enter the location to which to move the player to. 
	> See locations table below
2. Enter the player's playkey
	> Enter anything to skip to step 4
3. From the list of characters on that account, copy down the character ID for the stuck character
4. Enter the character ID of the stuck character

##### options
| location | location command |
|--|--|
|AG Landing Zone  | ag1 |
|AG Picnic Area	| ag2 |
|NS Plaza | ns1 |

	

<br>

## getCharInfo.sh<br>
#### Description:
Displays all the characters and their info for the provided play key.

<br>

## install.sh<br>
#### Description:
Places a link to all the scripts in the home directory, as well as copies over the settings file for  `playerCntDisplay.py`

<br>

## lockAccount.sh<br>
#### Description:
Locks or unlocks the account tied to the given play key.

<br>
 
 ## playerCntDisplay.py<br>
 
#### Description:
Displays the current count of online players, as well as what worlds are populated. Pushes this info, via a webhook, to a Discord server channel. 

If enabled, will also publish an MQTT JSON message with world info. This is used by my player tracker board (WIP)

#### Setup:
1. Navigate to the cloned repo and install the required python packages with `pip install -r requirements.txt`
2. Copy the `playerCntSettings_OG.py` from `settings` to the root directory of the repo. 
3. Rename the file you just copied to `playerCntSettings.py`
4. Open `playerCntSettings.py` and add the credentials
	4a. To get your webhook, open your Discord server and go to `Server Settings` -> `Integrations` -> `Webhooks` 
5. Run the script. It will refresh the player count based on the interval set in the settings file
	6a. I would recommend setting up a systemd process to start and stop the script

**To prevent inaccurate readings in the case of a server crash or shutdown, delete the last 24 hrs of the activity log every time you start your server.** 
`mysql -u DBuser -p -D DBname -e "DELETE from activity_log WHERE time > UNIX_TIMESTAMP(now() - interval 24 hour);"`

<br>

## pullCharXml.sh<br>
#### Description:
Pulls the character xml data for the give character ID and puts it in a file called `xmlData.txt`

#### Use:
`python3 pullCharXml.sh [characterID]`

<br>

## restore-database.sh<br>
#### Description:
Pulls the given database backup file from a Google Cloud storage bucket and restores the database from it.

> This script will need to be edited to work properly for your environment

#### Use:
`python3 restore-database.sh [backupFileName]`

<br>

## start__Server.sh<br>
#### Description:
Starts the server in a screen session and deletes the last 24hrs from the activity log table.

> This script will need to be edited to work properly for your environment

<br>

## stop__Server.sh<br>
#### Description:
Stops the server by sending `^C` to the screen session.

> This script will need to be edited to work properly for your environment

<br>

## update-chatwhitelsit.sh<br>
#### Description:
Pulls the chat whitelist file from a Google Cloud storage bucket and replaces the whitelist currently in use by the server.

> This script will need to be edited to work properly for your environment

<br>

## writeCharXml.sh<br>
#### Description:
Writes XML data in `xmlData.txt` to the given character ID. Creates a backup of the database before the write and saves it to `deleteMe.sql`

#### Use:
`./writeCharXml.sh [characterID]`

<br>
