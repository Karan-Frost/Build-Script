# Android CI Bot Script (Python)

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)

A Python script designed to automate Android ROM building and interaction with Telegram. It handles source syncing, compilation, progress monitoring, and file uploading.

Adapted by [Frost](https://github.com/Karan-Frost) from the original Bash script by [hipexscape](https://github.com/hipexscape).

## Requirements

* Python 3.x
* `requests` library (`pip install requests`)
* `repo` tool installed and in your PATH
* `rclone` installed and configured

## Setup

1.  **Clone the repository:**
    Clone this repository to the root of your source tree (or anywhere accessible).

2.  **Install dependencies:**
    ```bash
    pip install requests
    ```

3.  **Create a Configuration File:**
    Create a file named `config.env` (or any name like `config.device.env`) in the same directory as the script (for reference, see config.example.env). You can create multiple config files for different devices.

    **Template:**

    ```env
    # Device Configuration
    DEVICE=your_device_codename
    VARIANT=user
    OFFICIAL_FLAG=False

    # Telegram Configuration
    CHAT_ID=-100xxxxxxxx
    BOT_TOKEN=your_bot_token
    ERROR_CHAT_ID=-100xxxxxxxx

    # Upload Configuration
    RCLONE_REMOTE=drive
    RCLONE_FOLDER=roms/device_name

    # Initial install zip Configuration (Leave empty if you want to use your device's codename or if your device has recovery.img)
    INITIAL_INSTALL_ZIP_DEVICES=codename|codename2

    # Server Management
    POWEROFF=False
    ```

### Configuration Variables

| Variable | Description |
| :--- | :--- |
| `DEVICE` | Your device codename (e.g., `zircon`, `veux`) |
| `VARIANT` | Build variant (`user`, `userdebug`, or `eng`) |
| `OFFICIAL_FLAG` | Set to `True` if this is an official build, `False` otherwise |
| `CHAT_ID` | Your Telegram Group/Channel Chat ID (e.g., `-100xxxxxxx`) |
| `BOT_TOKEN` | Your HTTP API Bot Token from BotFather |
| `ERROR_CHAT_ID` | Secondary Chat ID for sending error logs (can be same as CHAT_ID) |
| `RCLONE_REMOTE` | Your rclone remote name (e.g., `drive`) |
| `RCLONE_FOLDER` | The target folder on the rclone remote |
| `INITIAL_INSTALL_ZIP_DEVICES` | Used **only** if `recovery.img` is missing. Defines allowed devices for the generated install zip. Defaults to `DEVICE` |
| `POWEROFF` | Set to `True` to power off the server after completion |

## Artifact Uploads

The script automatically uploads the build results to two locations:

1.  **ROM Zip:** The main ROM file is uploaded to your **Rclone Remote** defined in the config (e.g., Google Drive, Mega, OneDrive).
2.  **Auxiliary Files:** Uploaded to **GoFile.io** for quick, temporary access. The script uses the following logic:
    * **Recovery:** If `recovery.img` is found in the output, it is uploaded directly.
    * **Initial Install Zip:** If `recovery.img` is *not* found, the script generates a flashable zip containing `boot`, `vendor_boot`, and `dtbo` and uploads that instead.
    * **OTA JSON:** If a matching JSON file is found in `vendor/ota/`, it is also uploaded.

## Command Line Options

Run the script using `python3 ci_bot.py [options]`.

| Option | Flag | Description |
| :--- | :--- | :--- |
| **Config** | `--config` | Path to your specific configuration file. Defaults to `config.env` if not specified. |
| **Sync** | `-s`, `--sync` | Runs `repo sync` before starting the build. Useful for fetching the latest source changes. |
| **Clean** | `-c`, `--clean` | Deletes the entire `out/` directory. Use this for a completely fresh build (takes longer). |
| **Disk Opt.** | `--d-o`, `--disk-optimization` | Runs a disk optimizing script before building. |
