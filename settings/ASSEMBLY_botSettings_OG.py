#Database Credentials
DATABASE_IP = "localhost" #IP of the mysql database
DATABASE_NAME = "nameHere" #Name of the database
DATABASE_USER = "unameHere" #Name of the database user
DATABASE_PASS = "passHere" #Database password

#Enable or disable the bot
ENABLE_BOT = True

#Discord Bot Token
DISCORD_TOKEN = "TOKEN_HERE"

#Channel for the bot to post messages in
BOT_CHANNEL = "channelNameHere"

#Role to ping if there is an issue with the playkey
ROLE_TO_PING = "roleNameHere"

#Role name that has the ability to run the / commands
COMMAND_ROLE = "roleNameHere"


OFFENSE_THRESHOLD = 3 #Number of offenses before a user flagged for review


################################
# Bot Periodic
################################
SEC_IN_HOUR = 3600

PERIODIC_FREQUENCY = 60  #In seconds, how frequent the periodic task should run
OFFENSE_REPORT_FREQ = 12 * SEC_IN_HOUR #In hours, how frequent the offense report should run 
TASK_CHECK_FREQ = 12 * SEC_IN_HOUR  #In hours, how frequent the task check should run


################################
# Playkey Settings
################################

#Playkey request channel in discord
REQUEST_CHANNEL = "channelNameHere"

#Lock LU account when user leaves the Discord
LOCK_ON_LEAVE = True


################################
# Name Approval Settings
################################

ENABLE_NAME_APPROVAL = False

GPT_API_KEY = "API_KEY_HERE"  #OpenAI API Key

SEC_IN_HOUR = 3600
NAME_CHECK_FREQ = 24 * SEC_IN_HOUR  #In hours, how frequent the name check should run

MAX_NAMES = 100 #Max number of names to check at a time

# Log Settings - logs all names checked and rejected names (and reasons) to a log file
LOG_TO_FILE = True
LOG_FILE = "nameApproval.log"

TRACK_OFFENSES = True #Log to a user's report for each name that is flagged

DEBUG = False

ALLOWED_NAMES = (   #List of names that keep on getting flagged but should be allowed and their reasons:
    """
    \nExamples of names that should be allowed, and their reasons:

    "Anti" - The word "anti" is not offensive or inappropriate.
    "Furcoat" - In this context, "fu" is not offensive or inappropriate.
    "Stinky" - The word "stinky" and other similar words are not offensive or inappropriate.
    "butterscortchbate" - "bate" in this context is meant at "bait" and not "masturbate"
    "trojanhorse" - "trojan" in this context is meant as the horse and not the condom brand
    "Bonelord" - "bone" in this context is meant as the skeletal bone and not the sexual innuendo
    "Bone" - The word "bone" is not offensive or inappropriate.
    "boney" - The word "boney" is not offensive or inappropriate.

    """
) 

DISALLOWED_NAMES = (   #List of names that should be disallowed, and their reasons:
    """
    \nExamples of names that should be disallowed, and their reasons:

    "fu" - The word "fu" can stand for "fuck you"
    "an1l" - The "1" is used as an "i" and it spells "anil" which sounds like "anal"
    "Diddy" - Name of a sex abuser
    "Adolf" - Reference to Adolf Hitler, which is inappropriate
    "testiculartorsion" - Refers to a medical condition involving testicles, which is inappropriate for a children's game.
    "peepoo" - Potty language
    "shit" - Swear and/or curse word

    """
)

NAME_APPROVAL_GPT_SYSTEM_MESSAGE = (
    """
    You are a GPT crafted for screening names in a children's game, focusing on appropriateness. 
    You evaluate names submitted through text. You excel in providing detailed cultural insights 
    on flagged names, offering in-depth explanations on why a name might be unsuitable. You avoid technical jargon, 
    maintaining simplicity in your explanations to be easily understandable. You ensure that your analysis is both 
    accurate and educational, helping to create a safe environment for children's games. You emphasize respectful and 
    informative communication, avoiding complex language to ensure clarity and accessibility for a broad audience.
    Should only return names that you have flagged. 
    Random strings are fine as long as they don't contain an inappropriate word. If a name contains or may contain an offensive 
    or inappropriate term or word, list that term or word. Also say what part of the name might be offensive or inappropriate.
    Do not list the name if it's okay.
    Do not be overly sensitive to borderline cases.
    Look for cases where numbers are used to represent letters in inappropriate words.
    Reject names that have potty language, sexual innuendos, or religious references.
    Respond with a JSON list of flagged names and reasons. If no names are flagged, return an empty JSON list.
    JSON should follow the following format: 
    [
    {
        "name": "name_here",
        "reason": "reason_here"
    },
    {
        "name": "name_here",
        "reason": "reason_here"
    },
    ]

    Do not put JSON in a code block.

    """
)

FULL_NAME_APPROVAL_GPT_SYSTEM_MESSAGE = NAME_APPROVAL_GPT_SYSTEM_MESSAGE + ALLOWED_NAMES + DISALLOWED_NAMES


################################
# Whitelist Settings
################################
#Path to the whitelist file
WHITELIST_FILE = "path/to/chatplus_en_us.txt"

#Channel for whitelist suggestions
WHITELIST_CHANNEL = "whitelist-suggestions"

WHITELIST_GPT_SYSTEM_MESSAGE = (
    """
    You are a GPT crafted to assist in processing the whitelist requests for a game chat.
    You will be given a list of messages that may contain whitelist words/strings.
    You must ignore the messages that are not relevant to the whitelist request. 
    If a message contains multiple words/strings, parse those out. 
    If you come across a word, make sure to add the plural, singular, and past tense to the list.
    You must let pass ascii based emojis like :) B) etc. in the whitelist.
    You must let pass numbers

    Remove newlines and extra spaces.
    You must return a JSON list of the whitelist words/strings. 
    Do not put JSON in a code block.
    """
)


##############################
# Logic DO NOT EDIT
##############################
import sys

if PERIODIC_FREQUENCY > OFFENSE_REPORT_FREQ:
    print("PERIODIC_FREQUENCY must be less than OFFENSE_REPORT_FREQ")
    sys.exit(1)
if PERIODIC_FREQUENCY > TASK_CHECK_FREQ:
    print("PERIODIC_FREQUENCY must be less than TASK_CHECK_FREQ")
    sys.exit(1)