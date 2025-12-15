#!/usr/bin/env python3
import os
import sys
import time
import argparse
import subprocess
import requests
import re
import shutil
from datetime import datetime, timezone

# Visual Constants
YELLOW = "\033[33m"
BOLD = "\033[1m"
RESET = "\033[0m"
BOLD_GREEN = "\033[1;32m"
RED = "\033[31m"

ROOT_DIRECTORY = os.getcwd()

# Attempt to detect ROM name from directory
try:
    ROM_NAME = os.path.basename(ROOT_DIRECTORY)
except:
    ROM_NAME = "Unknown"

# Detect Android version from manifest
try:
    with open(".repo/manifests/default.xml", "r") as f:
        content = f.read()
        match = re.search(r'(?<=android-)[0-9]+', content)
        ANDROID_VERSION = match.group(0) if match else "Unknown"
except FileNotFoundError:
    ANDROID_VERSION = "Unknown"

# Config Loader
def load_env(file_path):
    config = {}
    if not os.path.exists(file_path):
        print(f"{RED}Error: Config file '{file_path}' not found.{RESET}")
        sys.exit(1)

    with open(file_path, 'r') as f:
        for line in f:
            if line.strip().startswith('#') or not line.strip():
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False

                config[key] = value
    return config

# Telegram Bot Class
class CIBot:
    def __init__(self, config):
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config['BOT_TOKEN']}"
        self.message_id = None

    def send_message(self, text, chat_id=None):
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        url = f"{self.base_url}/sendMessage"
        data = {
            "chat_id": target_chat,
            "text": text,
            "parse_mode": "html",
            "disable_web_page_preview": True
        }
        try:
            r = requests.post(url, data=data)
            response = r.json()
            if response.get("ok"):
                return response["result"]["message_id"]
        except Exception as e:
            print(f"{RED}Failed to send message: {e}{RESET}")
        return None

    def edit_message(self, text, message_id=None, chat_id=None):
        msg_id = message_id if message_id else self.message_id
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        if not msg_id:
            return

        url = f"{self.base_url}/editMessageText"
        data = {
            "chat_id": target_chat,
            "message_id": msg_id,
            "text": text,
            "parse_mode": "html",
            "disable_web_page_preview": True
        }
        try:
            requests.post(url, data=data)
        except Exception as e:
            print(f"{RED}Failed to edit message: {e}{RESET}")

    def send_document(self, file_path, chat_id=None):
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        url = f"{self.base_url}/sendDocument"
        data = {
            "chat_id": target_chat,
            "parse_mode": "html",
            "disable_web_page_preview": True
        }
        try:
            with open(file_path, 'rb') as f:
                requests.post(url, data=data, files={"document": f})
        except Exception as e:
            print(f"{RED}Failed to upload file: {e}{RESET}")

    def pin_message(self, message_id, chat_id=None):
        target_chat = chat_id if chat_id else self.config['CHAT_ID']
        url = f"{self.base_url}/pinChatMessage"
        data = {"chat_id": target_chat, "message_id": message_id}
        try:
            requests.post(url, data=data)
        except Exception as e:
            print(f"{RED}Could not pin message: {e}{RESET}")

# Helper Functions
def upload_gofile(file_path):
    try:
        server_req = requests.get('https://api.gofile.io/servers')
        server_data = server_req.json()
        if server_data['status'] != 'ok':
            return "Error getting gofile server"

        server = server_data['data']['servers'][0]['name']

        with open(file_path, 'rb') as f:
            upload_req = requests.post(
                f'https://{server}.gofile.io/contents/uploadfile',
                files={'file': f}
            )
        resp = upload_req.json()
        if resp['status'] == 'ok':
            return resp['data']['downloadPage']
        else:
            return "Upload Failed"
    except Exception as e:
        return f"Error: {e}"

def upload_rclone(file_path, remote, folder):
    try:
        cmd = ["rclone", "copy", file_path, f"{remote}:{folder}"]
        subprocess.run(cmd, check=True)

        cmd_link = ["rclone", "link", f"{remote}:{folder}/{os.path.basename(file_path)}"]
        result = subprocess.run(cmd_link, capture_output=True, text=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return "Rclone Upload Failed"

def fetch_progress(log_file):
    try:
        if not os.path.exists(log_file):
            return None

        with open(log_file, "r") as f:
            lines = f.readlines()

        for line in reversed(lines):
            if "ninja" in line or "%" in line:
                match = re.search(r'(\d+%) (\d+/\d+)', line)
                if match:
                    return f"{match.group(1)} ({match.group(2)})"
    except Exception:
        pass
    return "Initializing..."

def format_duration(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{int(hours)} hours(s) and {int(minutes)} minutes(s)"
    return f"{int(minutes)} minutes(s) and {int(seconds)} seconds(s)"

# Main Execution
def main():
    parser = argparse.ArgumentParser(description="Android ROM Build Bot")
    parser.add_argument('--config', type=str, default="config.env", help="Path to config file (default: config.env)")
    parser.add_argument('-s', '--sync', dest='sync', action='store_true', help='Sync sources')
    parser.add_argument('-c', '--clean', dest='clean', action='store_true', help='Clean output')
    parser.add_argument('--c-d', '--clean-device', dest='clean_device', action='store_true', help='Clean device output')
    parser.add_argument('--d-o', '--disk-optimization', dest='disk_optimization', action='store_true', help='Optimize disk')
    args = parser.parse_args()

    # Load Configuration
    CONFIG = load_env(args.config)

    # Validate configuration
    required_keys = ["DEVICE", "VARIANT", "BOT_TOKEN", "CHAT_ID"]
    for key in required_keys:
        if key not in CONFIG or not CONFIG[key]:
            print(f"{RED}\nERROR: Missing {key} in config file. Exiting...{RESET}\n")
            sys.exit(1)

    bot = CIBot(CONFIG)
    cpu_count = os.cpu_count()
    sync_jobs = 12 if cpu_count > 8 else cpu_count

    now = datetime.now(timezone.utc)
    build_datetime = str(int(now.timestamp()))
    build_number = now.strftime("%Y%m%d00")

    # 1. Disk Optimization
    if args.disk_optimization:
        io_script = os.path.expanduser("~/io.sh")
        if os.path.exists(io_script):
            subprocess.run(["bash", io_script])
        else:
            print(f"{BOLD_GREEN}Downloading and running disk optimization script...{RESET}")
            subprocess.run("curl -s https://raw.githubusercontent.com/KanishkTheDerp/scripts/master/io.sh | bash", shell=True)
        print(f"{BOLD_GREEN}\nDisk optimization complete.{RESET}\n")

    # 2. Syncing
    if args.sync:
        msg = (f"<b>Build Status: Syncing Sources</b>\n\n"
               f"<b>ROM:</b> <code>{ROM_NAME}</code>\n"
               f"<b>Device:</b> <code>{CONFIG['DEVICE']}</code>\n"
               f"<b>Jobs:</b> <code>{sync_jobs} Threads</code>\n"
               f"<b>Directory:</b> <code>{ROOT_DIRECTORY}</code>")

        bot.message_id = bot.send_message(msg)
        start_sync = time.time()
        print(f"{BOLD_GREEN}\nStarting repo sync...{RESET}\n")

        cmd_sync = f"repo sync -c -j{sync_jobs} --force-sync --no-clone-bundle --no-tags"
        ret = subprocess.run(cmd_sync, shell=True)

        if ret.returncode != 0:
            print(f"{BOLD_GREEN}\nSync failed. Retrying with force...{RESET}")
            ret = subprocess.run("repo sync --force-sync", shell=True)

        if ret.returncode == 0:
            duration = format_duration(time.time() - start_sync)
            done_msg = (f"<b>Build Status: Sync Complete</b>\n\n"
                        f"<b>ROM:</b> <code>{ROM_NAME}</code>\n"
                        f"<b>Device:</b> <code>{CONFIG['DEVICE']}</code>\n"
                        f"<b>Duration:</b> <code>{duration}</code>")
            bot.edit_message(done_msg)
        else:
            fail_msg = (f"<b>Build Status: Sync Failed</b>\n\n"
                        f"Attempting compilation regardless...")
            bot.edit_message(fail_msg)

    # 3. Cleaning
    if args.clean:
        print(f"{BOLD_GREEN}\nCleaning 'out' directory...{RESET}")
        shutil.rmtree("out", ignore_errors=True)

    if args.clean_device:
        device_out = f"out/target/product/{CONFIG['DEVICE']}"
        print(f"{BOLD_GREEN}\nCleaning device output: {device_out}{RESET}")
        shutil.rmtree(device_out, ignore_errors=True)

    # 4. Preparation
    for f in ["out/error.log", "out/.lock", "build.log"]:
        if os.path.exists(f):
            os.remove(f)

    official_txt = "Official" if CONFIG.get('OFFICIAL_FLAG') else "Unofficial"
    build_msg = (f"<b>Build Status: Compiling</b>\n\n"
                 f"<b>ROM:</b> <code>{ROM_NAME}</code>\n"
                 f"<b>Device:</b> <code>{CONFIG['DEVICE']}</code>\n"
                 f"<b>Android:</b> <code>{ANDROID_VERSION}</code>\n"
                 f"<b>Type:</b> <code>{official_txt}</code>\n"
                 f"<b>Jobs:</b> <code>{cpu_count} Threads</code>\n"
                 f"<b>Status:</b> <code>Initializing...</code>")

    bot.message_id = bot.send_message(build_msg)
    start_build = time.time()

    print(f"{BOLD_GREEN}\nSetting up build environment and running brunch...{RESET}")

    export_vars = f"export BUILD_DATETIME={build_datetime} BUILD_NUMBER={build_number}"
    
    build_cmd = (f"bash -c '{export_vars} && source build/envsetup.sh && {export_vars} && "
                 f"brunch {CONFIG['DEVICE']} {CONFIG['VARIANT']}' 2>&1 | tee -a build.log")

    process = subprocess.Popen(build_cmd, shell=True)

    previous_prog = ""
    while process.poll() is None:
        current_prog = fetch_progress("build.log")
        if current_prog and current_prog != previous_prog:
            prog_msg = (f"<b>Build Status: Compiling</b>\n\n"
                        f"<b>ROM:</b> <code>{ROM_NAME}</code>\n"
                        f"<b>Device:</b> <code>{CONFIG['DEVICE']}</code>\n"
                        f"<b>Android:</b> <code>{ANDROID_VERSION}</code>\n"
                        f"<b>Type:</b> <code>{official_txt}</code>\n"
                        f"<b>Jobs:</b> <code>{cpu_count} Threads</code>\n"
                        f"<b>Progress:</b> <code>{current_prog}</code>")
            bot.edit_message(prog_msg)
            previous_prog = current_prog
        time.sleep(10)

    # 5. Post-Build
    duration = format_duration(time.time() - start_build)

    build_success = False

    if os.path.exists("build.log"):
        try:
            with open("build.log", "r", encoding="utf-8", errors="ignore") as f:
                if "build completed successfully" in f.read():
                    build_success = True
        except Exception as e:
            print(f"{YELLOW}Warning: Could not read build.log: {e}{RESET}")

    out_dir = f"out/target/product/{CONFIG['DEVICE']}"
    if not build_success and os.path.exists(out_dir):
         files = [f for f in os.listdir(out_dir) if CONFIG['DEVICE'] in f and f.endswith(".zip")]
         if files:
             print(f"{YELLOW}Log success message not found, but ZIP exists. Assuming success.{RESET}")
             build_success = True

    if not build_success:
        fail_msg = (f"<b>Build Status: Failed</b>\n\n"
                    f"<i>Check the attached log for details.</i>")

        target_error_chat = CONFIG.get('ERROR_CHAT_ID') if CONFIG.get('ERROR_CHAT_ID') else CONFIG['CHAT_ID']
        bot.edit_message(fail_msg, chat_id=target_error_chat)

        if os.path.exists("out/error.log"):
             bot.send_document("out/error.log", chat_id=target_error_chat)

        sys.exit(1)

    try:
        all_files = [f for f in os.listdir(out_dir) if CONFIG['DEVICE'] in f and f.endswith(".zip")]

        if not all_files:
            raise FileNotFoundError("Build passed (log check), but no ZIP file found in output.")

        main_files = [f for f in all_files if "ota" not in f.lower() and "target_files" not in f.lower()]

        if main_files:
            main_files.sort(key=lambda x: os.path.getsize(os.path.join(out_dir, x)), reverse=True)
            rom_filename = main_files[0]
        else:
            all_files.sort(key=lambda x: os.path.getsize(os.path.join(out_dir, x)), reverse=True)
            rom_filename = all_files[0]

        rom_zip = os.path.join(out_dir, rom_filename)

        rom_folder = os.path.join(out_dir, "rom_temp")
        os.makedirs(rom_folder, exist_ok=True)

        required_imgs = ["vendor_boot.img", "boot.img", "dtbo.img"]
        for img in required_imgs:
            src = os.path.join(out_dir, img)
            if os.path.exists(src):
                shutil.copy(src, rom_folder)

        board_req = CONFIG.get('INITIAL_INSTALL_ZIP_DEVICES')
        if not board_req:
            board_req = CONFIG['DEVICE']

        with open(os.path.join(rom_folder, "android-info.txt"), "w") as f:
            f.write(f"require board={board_req}\n")

        with open(os.path.join(rom_folder, "fastboot-info.txt"), "w") as f:
            f.write("version 1\nflash boot\nflash vendor_boot\nflash dtbo\nreboot bootloader\n")

        initial_zip_name = rom_zip.replace(".zip", "-initial-install.zip")
        shutil.make_archive(initial_zip_name.replace(".zip", ""), 'zip', rom_folder)
        shutil.rmtree(rom_folder)

        print(f"{BOLD_GREEN}\nUploading files...{RESET}")
        rom_link = upload_rclone(rom_zip, CONFIG['RCLONE_REMOTE'], CONFIG['RCLONE_FOLDER'])
        initial_link = upload_gofile(initial_zip_name)

        json_path = os.path.join(ROOT_DIRECTORY, "vendor", "ota", f"{CONFIG['DEVICE']}.json")
        json_link = None
        if os.path.exists(json_path):
            print(f"{BOLD_GREEN}Found OTA JSON: {json_path}... Uploading.{RESET}")
            uploaded_json = upload_gofile(json_path)
            if "http" in str(uploaded_json):
                json_link = uploaded_json
            else:
                print(f"{RED}JSON upload failed: {uploaded_json}{RESET}")

        md5 = subprocess.check_output(f"md5sum {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()
        size_human = subprocess.check_output(f"ls -sh {rom_zip} | awk '{{print $1}}'", shell=True).decode().strip()

        downloads = f"<a href=\"{rom_link}\">ROM</a> | <a href=\"{initial_link}\">Initial Install</a>"
        if json_link:
            downloads += f" | <a href=\"{json_link}\">OTA JSON</a>"

        success_msg = (f"<b>Build Status: Success</b>\n\n"
                       f"<b>ROM:</b> <code>{ROM_NAME}</code>\n"
                       f"<b>Device:</b> <code>{CONFIG['DEVICE']}</code>\n"
                       f"<b>Android:</b> <code>{ANDROID_VERSION}</code>\n"
                       f"<b>Type:</b> <code>{official_txt}</code>\n"
                       f"<b>Size:</b> <code>{size_human}</code>\n"
                       f"<b>MD5:</b> <code>{md5}</code>\n"
                       f"<b>Duration:</b> <code>{duration}</code>\n\n"
                       f"<b>Download:</b> {downloads}")

        bot.edit_message(success_msg)
        bot.pin_message(bot.message_id)

    except Exception as e:
        print(f"{RED}Packaging error: {e}{RESET}")
        bot.send_message(f"Build passed but packaging failed: {e}")

    if CONFIG.get('POWEROFF'):
        print(f"{BOLD_GREEN}Shutting down server.{RESET}")
        os.system("sudo poweroff")

if __name__ == "__main__":
    main()
