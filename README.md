  
  
  

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

Rescues a stuck player by modifying their xml data and placing them in a predetermined world and location.

  

#### Use:

1. Enter the location to which to move the player to.

> See locations table below

2. Enter the player's playkey

> Enter anything to skip to step 4

3. From the list of characters on that account, copy down the character ID for the stuck character

4. Enter the character ID of the stuck character

  

##### options

| location        | location command |
|-----------------|------------------|
| AG Landing Zone | ag1             |
| AG Picnic Area  | ag2             |
| NS Plaza        | ns1             |


  

  

<br>

  

## getCharInfo.sh<br>

#### Description:

Displays all the characters and their info for the provided play key.

  

<br>

  

## install.sh<br>

#### Description:

Places a link to all the scripts in the home directory, as well as copies over the settings file for `playerCntDisplay.py`

  

<br>

  

## lockAccount.sh<br>

#### Description:

Locks or unlocks the account tied to the given play key.
  
<br>

## playerCntDisplay.py<br>

#### Description:

Displays the current count of online players, as well as what worlds are populated. Pushes this info, along with stats, via webhooks, to a Discord server channel.

  

If enabled, will also publish an MQTT JSON message with world info. This is used by the [player tracker board](https://github.com/HailStorm32/LU-Player-Tracker-Code) that I am developing (WIP)

  

#### Setup:

1. Navigate to the cloned repo and install the required python packages with `pip install -r requirements.txt`

2. Copy the `playerCntSettings_OG.py` from `settings` to the root directory of the repo.

3. Rename the file you just copied to `playerCntSettings.py`

4. Open `playerCntSettings.py` and add the credentials

  

4a. To get your webhook URL, open your Discord server and go to `Server Settings` -> `Integrations` -> `Webhooks`

4b. You will want two webhooks, one for the online count and one for the stats.

```

DATABASE_IP = "localhost" #IP of the mysql database

DATABASE_NAME = "darkflame" #Name of the database

DATABASE_USER = "darkflame" #Name of the database user

DATABASE_PASS = "passHere" #Database password

MQTT_BROKER_ADDR = "ipHere" #IP of MQTT broker (should be server IP)

MQTT_BROKER_PORT = 1883 #Port # for MQTT broker (should be 1883)

MQTT_UNAME = "unameHere" #Username used to connect to MQTT broker

MQTT_PASS = "passHere" #Password used to connect to MQTT broker

COUNT_WEBHOOK_URL = "1ST_URL_HERE" #URL of the webhook to send the online count

STATS_WEBHOOK_URL = "2ND_URL_HERE" #URL of the webhook to send the stats

```

5. Run the script. It will refresh the player count based on the interval set in the settings file

6. I would recommend setting up a systemd process to start and stop the script

  

**To prevent inaccurate readings in the case of a server crash or shutdown, delete the last 24 hrs of the activity log every time you start your server.**

`mysql -u DBuser -p -D DBname -e "DELETE from activity_log WHERE time > UNIX_TIMESTAMP(now() - interval 24 hour);"`


<br>

  ## playkeyGiverBot.py<br>

#### Description:
A Discord bot that manages and distributes play keys. Will automatically generate and distribute a play key when a user requests in the configured channel. If enabled, it will also automatically lock the LU account of a user if they leave the Discord. 

Also implements player notes, allowing moderators to add, remove and display notes for a given user.

#### Setup:
1. Navigate to the cloned repo and install the required python packages with `pip install -r requirements.txt`

2. Copy the `playkeyBotSettings_OG.py` from `settings` to the root directory of the repo.

3. Rename the file you just copied to `playkeyBotSettings.py`

4. Open `playkeyBotSettings.py` and configure the settings

5. Set Up Discord Bot:
   - Create a new application in the [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a bot for the application and copy the bot token into `DISCORD_TOKEN` in `playkeyBotSettings.py`
		>   *You may need to go to the bot tab and regenerate the token*

   - Installation tab should look as follows:
   ![enter image description here](https://i.imgur.com/9Dz2nDF.png)
   
   - Oauth2 tab should look like the following (use the generated link to invite the bot to your server):
   ![enter image description here](https://i.imgur.com/6Bi6fuT.png)
   - Bot tab should look like the following:
   ![enter image description here](https://i.imgur.com/imjMkux.png)
   - Lastly, go into the integration settings of the Discord server and make sure to assign a role that can use the commands
   - Also make sure that the channels you want the bot to have access to, also has the bot role assigned to it

6. Run the Bot:
   ```sh
   python3 playkeyGiverBot.py
   ```

#### Commands:
- **`/addnote <username> <note>`**:  Adds a note to the specified user
- **`/displaynotes <username>`**:  Displays all the notes for the specified user
- **`/removenote <username> <id>`**: Removes the specific note ID from the specified user
- **`/showkey <username>`**: Shows the playkey for the specified user
- **`/showaccount <play_key>`**: Shows Discord account name tied to given play key
- **`/lockaccount <username_or_playkey>`**: Locks the account (or key if no account has been made) for the specified user
- **`/unlockaccount <username_or_playkey>`**: Unlocks the account (or key if no account has been made) for the specified user

> **Note:** Ensure that the bot has the necessary permissions in the server and channels it will operate in.

<br>

## autoNameApproval.py<br>

#### Description:
Uses OpenAI GPT4o to automatically approve and reject character and pet names every 24 hours.

#### Setup:
1. Navigate to the cloned repo and install the required python packages with `pip install -r requirements.txt`

2. Copy the `nameApprovalSettings_OG.py` from `settings` to the root directory of the repo.

3. Rename the file you just copied to `nameApprovalSettings.py`

4. Open `nameApprovalSettings.py`
5. Add the database credentials
6. Add your OpenAI API key (you can get one [here](https://platform.openai.com/docs/overview))

```

DATABASE_IP = "localhost" #IP of the mysql database

DATABASE_NAME = "darkflame" #Name of the database

DATABASE_USER = "darkflame" #Name of the database user

DATABASE_PASS = "passHere" #Database password

API_KEY  =  "API_KEY_HERE"  #OpenAI API Key

```

There are further settings in the file that can be changed to your liking, including changing the prompt used and disabling logging.


<br>

## charXmlPuller.py<br>

#### Description:

"Downloads" all the charxmls that belonging to single account. If selected, will also run the `xmlClean.py` script on each charxml.

  

#### Setup:

1. Navigate to the cloned repo and install the required python packages with `pip install -r requirements.txt`

2. Copy the `charXmlPullerSettings_OG.py` from `settings` to the root directory of the repo.

3. Rename the file you just copied to `charXmlPullerSettings.py`

4. Open `charXmlPullerSettings.py` and add the credentials

  

```

DATABASE_IP = "localhost" #IP of the mysql database

DATABASE_NAME = "darkflame" #Name of the database

DATABASE_USER = "darkflame" #Name of the database user

DATABASE_PASS = "passHere" #Database password

```

5. Run the script and follow the onscreen prompts

  

If you are getting the following error `Authentication plugin 'caching_sha2_password' is not supported` run:

`pip install --upgrade mysql-connector-python`

  

<br>

## contrabandCheck.py<br>

#### Description:

Searches all accounts (exept those excluded in the settings file) in the database for contraband items. Uses the `contrabandIds` dictionary for what items are to be searched for.

  

#### Setup:

1. Navigate to the cloned repo and install the required python packages with `pip install -r requirements.txt`

2. Copy the `contrabandCheckSettings_OG.py` from `settings` to the root directory of the repo.

3. Rename the file you just copied to `contrabandCheckSettings.py`

4. Open `contrabandCheckSettings.py` and add the credentials

  

```

DATABASE_IP = "localhost" #IP of the mysql database

DATABASE_NAME = "darkflame" #Name of the database

DATABASE_USER = "darkflame" #Name of the database user

DATABASE_PASS = "passHere" #Database password

```

5. Run the script

6. If contraband is found, the account key, offending character name and list of contraband items will be printed

  

<br>

## xmlClean.py<br>

#### Description:

Removes items and changes the account ID in a charxml.

  

#### Use:

`xmlClean.py [charxml_path] [new_account_id]`

  

<br>

  

## pullCharXml.sh<br>

#### Description:

Pulls the character xml data for the give character ID and puts it in a file called `xmlData.txt`

  

#### Use:

`./pullCharXml.sh [characterID]`

  

<br>

  

## restore-database.sh<br>

#### Description:

Pulls the given database backup file from a Google Cloud storage bucket and restores the database from it.

  

> This script will need to be edited to work properly for your environment

  

#### Use:

`./restore-database.sh [backupFileName]`

  

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
----
updated: 12/30/2024
