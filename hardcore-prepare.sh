#!/bin/bash

set -euo pipefail

# HARDCORE SETTINGS:
disable_extra_backpack="1"
hardcore_mode="1"
hardcore_dropinventory_on_death="1"
hardcore_uscore_enemies_multiplier="2"
hardcore_lose_uscore_on_death_percent="10"
hardcore_excluded_item_drops="6086,7044"
hardcore_uscore_reduction=""
hardcore_uscore_reduced_worlds=""
hardcore_uscore_reduced_lots=""
hardcore_uscore_excluded_enemies=""
hardcore_disabled_worlds=""
hardcore_coin_keep=""

# STATIC SETTINGS:
dashboard_config="/etc/nginx/sites-available/nexus_universe.online"
dashboard_enabled_config="/etc/nginx/sites-enabled/nexus_universe.online"
dashboard_settings_file="$HOME/Services/NexusDashboardapp/settings.py"
assembly_bot_settings_file="$HOME/hailstorms-darkflame-server-scripts/ASSEMBLY_bot_files/ASSEMBLY_botSettings.py"
server_config_dir="$HOME/GameServer/DarkflameServer/build"
master_config_file="$server_config_dir/masterconfig.ini"
shared_config_file="$server_config_dir/sharedconfig.ini"
world_config_file="$server_config_dir/worldconfig.ini"

renew_only=false

prompt_non_empty() {
	local prompt_message="$1"
	local result_var="$2"
	local read_mode="${3:-plain}"
	local input_value=""

	while [[ -z "$input_value" ]]; do
		if [[ "$read_mode" = "silent" ]]; then
			read -s -p "$prompt_message" input_value
			echo
		else
			read -p "$prompt_message" input_value
		fi

		if [[ -z "$input_value" ]]; then
			echo "A value is required."
		fi
	done

	printf -v "$result_var" '%s' "$input_value"
}

if [ "${1:-}" = "--renew" ]; then
	renew_only=true
	shift
fi

if [ "$#" -ne 0 ]; then
	echo "Usage: $0 [--renew]"
	exit 1
fi

if [ "$renew_only" = true ]; then
	prompt_non_empty "Enter the hardcore dashboard address: " hardcore_dashboard_address
	prompt_non_empty "Enter the email address for Certbot renewal notices: " certbot_email

	echo "Enabling nginx nexusdashboard site..."
	ln -sf "$dashboard_config" "$dashboard_enabled_config"

	echo "Starting nginx..."
	nginx -t
	systemctl start nginx

	echo "Requesting a new certificate for $hardcore_dashboard_address..."
	certbot --nginx --non-interactive --agree-tos -m "$certbot_email" -d "$hardcore_dashboard_address"

	exit 0
fi

echo "This script will prepare your system for hardcore mode. Certain things will be permanently changed, so please read the instructions carefully before proceeding."
prompt_non_empty "Do you want to continue? (yes/no or y/n): " response

if [ "$response" = "no" ] || [ "$response" = "n" ]; then
	exit 0
fi

echo -e "\n\n\n"
echo "###########################################################"
echo "# STOP SERVICES"
echo "###########################################################"

# Stop nginx
echo "Stopping nginx..."
systemctl stop nginx

# Stop player counter service
echo "Stopping player counter service..."
systemctl disable --now player-count-display

# Stop ASSEMBLY bot
echo "Stopping ASSEMBLY bot..."
systemctl disable --now ASSEMBLY_bot

# Stop darkflame server
echo "Stopping darkflame server..."
systemctl disable --now darkflame

# Stop dashboard
echo "Stopping dashboard..."
systemctl disable --now nexusdashboard

# Stop LU info bot
echo "Stopping LU info bot..."
systemctl disable --now LU_info_bot

echo "###########################################################"
echo "# GET USER INPUT"
echo "###########################################################"

# Prompt for the main server IP
prompt_non_empty "Enter the main server IP address currently used in nginx: " main_server_ip
clear

# Prompt for the main server dashboard address
prompt_non_empty "Enter the main dashboard web address currently used in nginx: " main_server_dashboard_address
clear

# Prompt for the hardcore dashboard address
prompt_non_empty "Enter the hardcore dashboard web address to configure: " hardcore_dashboard_address
clear

# Prompt for server IP
prompt_non_empty "Enter this server's IP address: " server_ip
clear

# Prompt for the main server database password
prompt_non_empty "Enter the main server database password: " main_db_password silent
clear

# Prompt for hardcore database password
prompt_non_empty "Enter the hardcore server database password: " dashboard_db_password silent
clear

# Prompt for captcha public and private keys
prompt_non_empty "Enter the captcha PRIVATE key: " captcha_secret_key silent
prompt_non_empty "Enter the captcha PUBLIC key: " captcha_site_key
clear

echo -e "\n\n\n"
echo "###########################################################"
echo "# NGINX CONFIGURATION"
echo "###########################################################"

# Remove the nexus universe site from sites-enabled
echo "Removing nexus universe site from nginx..."
rm -f "$dashboard_enabled_config"

# Update the nginx nexusdashboard config with the hardcore address and server IP
echo "Updating nginx nexusdashboard config..."

if [ ! -f "$dashboard_config" ]; then
	echo "Nginx nexusdashboard config not found: $dashboard_config"
	exit 1
fi

# Backup the original config before modifying it
dashboard_config_backup="${dashboard_config}.bak.$(date +%Y%m%d%H%M%S)"
cp "$dashboard_config" "$dashboard_config_backup"

# Use sed to replace the main server dashboard address and IP with the hardcore ones
sed -i \
	-e "s/${main_server_dashboard_address}/${hardcore_dashboard_address}/g" \
	-e "s/${main_server_ip}/${server_ip}/g" \
	"$dashboard_config"

echo "nginx nexusdashboard config updated successfully."


echo -e "\n\n\n"
echo "###########################################################"
echo "# DATABASE CONFIGURATION"
echo "###########################################################"

echo "Updating darkflame database user password..."
mysqladmin -u darkflame --password="$main_db_password" password "$dashboard_db_password"
echo "darkflame database user password updated successfully."

# Dropping BLU database if it exists, since it's not needed for hardcore mode
echo "Dropping BLU database if it exists..."
mysql -u darkflame --password="$dashboard_db_password" -e "DROP DATABASE IF EXISTS blu;"
echo "BLU database dropped successfully (if it existed)."

# Remove existing gameplay and social data for hardcore mode.
echo "Clearing selected darkflame tables..."
mysql -u darkflame --password="$dashboard_db_password" darkflame <<'SQL'
SET FOREIGN_KEY_CHECKS = 0;
TRUNCATE TABLE leaderboard;
TRUNCATE TABLE mail;
TRUNCATE TABLE charinfo;
TRUNCATE TABLE bug_reports;
TRUNCATE TABLE pet_names;
TRUNCATE TABLE properties;
TRUNCATE TABLE properties_contents;
TRUNCATE TABLE ignore_list;
TRUNCATE TABLE friends;
TRUNCATE TABLE activity_log;
TRUNCATE TABLE ugc;
TRUNCATE TABLE ugc_modular_build;
TRUNCATE TABLE charxml;
SET FOREIGN_KEY_CHECKS = 1;
SQL
echo "Selected darkflame tables cleared successfully."


echo -e "\n\n\n"
echo "###########################################################"
echo "# DASHBOARD CONFIGURATION"
echo "###########################################################"

echo "Updating dashboard settings..."

if [ ! -f "$dashboard_settings_file" ]; then
	echo "Dashboard settings file not found: $dashboard_settings_file"
	exit 1
fi

dashboard_settings_backup="${dashboard_settings_file}.bak.$(date +%Y%m%d%H%M%S)"
cp "$dashboard_settings_file" "$dashboard_settings_backup"

DASHBOARD_SETTINGS_FILE="$dashboard_settings_file" \
DASHBOARD_DB_PASSWORD="$dashboard_db_password" \
CAPTCHA_SITE_KEY="$captcha_site_key" \
CAPTCHA_SECRET_KEY="$captcha_secret_key" \
python3 - <<'PY'
import os
import re
import secrets
from pathlib import Path

settings_path = Path(os.environ["DASHBOARD_SETTINGS_FILE"])
content = settings_path.read_text()

replacements = {
	r'^APP_NAME = ".*"$': 'APP_NAME = "Hardcore Dashboard"',
	r'^APP_SECRET_KEY = ".*"$': f"APP_SECRET_KEY = {secrets.token_urlsafe(48)!r}",
	r'^APP_DATABASE_URI = ".*"$': f"APP_DATABASE_URI = {'mysql+pymysql://darkflame:' + os.environ['DASHBOARD_DB_PASSWORD'] + '@localhost/darkflame'!r}",
	r"^RECAPTCHA_PUBLIC_KEY = '.*'$": f"RECAPTCHA_PUBLIC_KEY = {os.environ['CAPTCHA_SITE_KEY']!r}",
	r"^RECAPTCHA_PRIVATE_KEY = '.*'$": f"RECAPTCHA_PRIVATE_KEY = {os.environ['CAPTCHA_SECRET_KEY']!r}",
}

for pattern, replacement in replacements.items():
	updated_content, replacements_made = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
	if replacements_made != 1:
		raise SystemExit(f"Failed to update dashboard settings entry matching: {pattern}")
	content = updated_content

settings_path.write_text(content)
PY

echo "Dashboard settings updated successfully."

# Start the dashboard service again
echo "Starting dashboard service..."
systemctl enable --now nexusdashboard

echo -e "\n\n\n"
echo "###########################################################"
echo "# ASSEMBLY BOT CONFIGURATION"
echo "###########################################################"

echo "Updating ASSEMBLY bot settings..."

if [ ! -f "$assembly_bot_settings_file" ]; then
	echo "ASSEMBLY bot settings file not found: $assembly_bot_settings_file"
	exit 1
fi

assembly_bot_settings_backup="${assembly_bot_settings_file}.bak.$(date +%Y%m%d%H%M%S)"
cp "$assembly_bot_settings_file" "$assembly_bot_settings_backup"

ASSEMBLY_BOT_SETTINGS_FILE="$assembly_bot_settings_file" \
DASHBOARD_DB_PASSWORD="$dashboard_db_password" \
python3 - <<'PY'
import os
import re
from pathlib import Path

settings_path = Path(os.environ["ASSEMBLY_BOT_SETTINGS_FILE"])
content = settings_path.read_text()

replacements = {
	r"^DATABASE_PASS\s*=.*$": f"DATABASE_PASS = {os.environ['DASHBOARD_DB_PASSWORD']!r} #Database password",
	r"^ENABLE_BOT\s*=.*$": "ENABLE_BOT = False",
}

for pattern, replacement in replacements.items():
	content, replacements_made = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
	if replacements_made != 1:
		raise SystemExit(f"Failed to update ASSEMBLY bot setting matching: {pattern}")

settings_path.write_text(content)
PY

echo "ASSEMBLY bot settings updated successfully."

# Starting ASSEMBLY bot
echo "Starting ASSEMBLY bot..."
systemctl enable --now ASSEMBLY_bot

echo -e "\n\n\n"
echo "###########################################################"
echo "# Server CONFIGURATION"
echo "###########################################################"

echo "Updating darkflame server config files..."

for config_file in "$master_config_file" "$shared_config_file" "$world_config_file"; do
	if [ ! -f "$config_file" ]; then
		echo "Darkflame server config file not found: $config_file"
		exit 1
	fi

	config_backup="${config_file}.bak.$(date +%Y%m%d%H%M%S)"
	cp "$config_file" "$config_backup"
done

MASTER_CONFIG_FILE="$master_config_file" \
SHARED_CONFIG_FILE="$shared_config_file" \
WORLD_CONFIG_FILE="$world_config_file" \
SERVER_IP="$server_ip" \
DASHBOARD_DB_PASSWORD="$dashboard_db_password" \
DISABLE_EXTRA_BACKPACK="$disable_extra_backpack" \
HARDCORE_MODE="$hardcore_mode" \
HARDCORE_DROPINVENTORY_ON_DEATH="$hardcore_dropinventory_on_death" \
HARDCORE_USCORE_ENEMIES_MULTIPLIER="$hardcore_uscore_enemies_multiplier" \
HARDCORE_LOSE_USCORE_ON_DEATH_PERCENT="$hardcore_lose_uscore_on_death_percent" \
HARDCORE_EXCLUDED_ITEM_DROPS="$hardcore_excluded_item_drops" \
HARDCORE_USCORE_REDUCTION="$hardcore_uscore_reduction" \
HARDCORE_USCORE_REDUCED_WORLDS="$hardcore_uscore_reduced_worlds" \
HARDCORE_USCORE_REDUCED_LOTS="$hardcore_uscore_reduced_lots" \
HARDCORE_USCORE_EXCLUDED_ENEMIES="$hardcore_uscore_excluded_enemies" \
HARDCORE_DISABLED_WORLDS="$hardcore_disabled_worlds" \
HARDCORE_COIN_KEEP="$hardcore_coin_keep" \
python3 - <<'PY'
import os
import re
from pathlib import Path


def update_ini(path, updates):
	content = Path(path).read_text()

	for key, value in updates.items():
		line = f"{key}={value}"
		pattern = re.compile(rf"^({re.escape(key)}\s*=).*$", re.MULTILINE)
		content, replacements_made = pattern.subn(line, content, count=1)

		if replacements_made == 0:
			if content and not content.endswith("\n"):
				content += "\n"
			content += f"{line}\n"

	Path(path).write_text(content)


server_ip = os.environ["SERVER_IP"]
dashboard_db_password = os.environ["DASHBOARD_DB_PASSWORD"]

update_ini(os.environ["MASTER_CONFIG_FILE"], {
	"external_ip": server_ip,
})

update_ini(os.environ["SHARED_CONFIG_FILE"], {
	"mysql_password": dashboard_db_password,
	"external_ip": server_ip,
})

update_ini(os.environ["WORLD_CONFIG_FILE"], {
	"disable_extra_backpack": os.environ["DISABLE_EXTRA_BACKPACK"],
	"hardcore_mode": os.environ["HARDCORE_MODE"],
	"hardcore_dropinventory_on_death": os.environ["HARDCORE_DROPINVENTORY_ON_DEATH"],
	"hardcore_uscore_enemies_multiplier": os.environ["HARDCORE_USCORE_ENEMIES_MULTIPLIER"],
	"hardcore_lose_uscore_on_death_percent": os.environ["HARDCORE_LOSE_USCORE_ON_DEATH_PERCENT"],
	"hardcore_excluded_item_drops": os.environ["HARDCORE_EXCLUDED_ITEM_DROPS"],
	"hardcore_uscore_reduction": os.environ["HARDCORE_USCORE_REDUCTION"],
	"hardcore_uscore_reduced_worlds": os.environ["HARDCORE_USCORE_REDUCED_WORLDS"],
	"hardcore_uscore_reduced_lots": os.environ["HARDCORE_USCORE_REDUCED_LOTS"],
	"hardcore_uscore_excluded_enemies": os.environ["HARDCORE_USCORE_EXCLUDED_ENEMIES"],
	"hardcore_disabled_worlds": os.environ["HARDCORE_DISABLED_WORLDS"],
	"hardcore_coin_keep": os.environ["HARDCORE_COIN_KEEP"],
})
PY

echo "Darkflame server config files updated successfully."

# Start the darkflame server service again
echo "Starting darkflame server service..."
systemctl enable --now darkflame
