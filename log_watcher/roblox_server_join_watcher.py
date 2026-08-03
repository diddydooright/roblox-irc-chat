"""
Docstring for lib.roblox_server_join_watcher
This script if run by itself will start watching your log files in roblox and printing them to the console.
"""
import time
import re
import os
import platform
from pathlib import Path

set_roblox_server_id_func = None

def get_roblox_log_folder():
    system = platform.system()

    if system == "Windows":
        local = os.getenv("LOCALAPPDATA")
        if local:
            return Path(local) / "Roblox" / "logs"

    elif system == "Darwin":  # macOS
        return Path.home() / "Library" / "Logs" / "Roblox"

    else:  # Linux (Wine)
        return Path.home() / ".local" / "share" / "Roblox" / "logs"

LOG_FOLDER = get_roblox_log_folder()

if not LOG_FOLDER or not LOG_FOLDER.exists():
    print("Roblox log folder not found. Launch Roblox at least once.")
    time.sleep(5)
    exit()



print("Watching folder:", LOG_FOLDER)

JOIN_REGEX = re.compile(r"Joining game '([a-f0-9\-]+)'", re.IGNORECASE)
DISCONNECT_REGEX = re.compile(r"\[FLog::Network\] Sending disconnect", re.IGNORECASE)

current_log = None
log_file_handle = None
job_id = ""

def open_newest_log():
    global current_log, log_file_handle

    logs = list(LOG_FOLDER.glob("*.log"))
    if not logs:
        return

    newest = max(logs, key=lambda f: f.stat().st_mtime)
  
    if newest != current_log:
        current_log = newest
        if log_file_handle:
            log_file_handle.close()
        
        log_file_handle = open(current_log, "r", errors="ignore")
        log_file_handle.seek(0, os.SEEK_END)
        print("Now watching:", current_log)


def check_new_lines():
    global log_file_handle

    if not log_file_handle:
        return None

    while True:
        line = log_file_handle.readline()
        if not line:
            break

        join_match = JOIN_REGEX.search(line)
        if join_match:
            job_id = join_match.group(1)
            print("Joined game server:", job_id)
            return job_id
                       
        if DISCONNECT_REGEX.search(line):
            print("Disconnected from game server")
            return False

def run_observer(set_roblox_server_id_func = None, disconnect_roblox_server_func=None):

    print("Log watching thread started...")

    while True:
        open_newest_log()
        check_new_lines_result = check_new_lines()
        if type(check_new_lines_result) is str:
            job_id = check_new_lines_result
            if set_roblox_server_id_func:
                set_roblox_server_id_func(job_id)
        if type(check_new_lines_result) is bool:
            if not check_new_lines_result:
                disconnect_roblox_server_func()

        time.sleep(0.2)


def main():
    run_observer()

if __name__ == "__main__":
    main()

    