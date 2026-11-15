"""Open the isolated bot profile for manual Google sign-in; never read credentials.

Close the browser window when finished. Do not run while another bot is active.
"""
import os
from pathlib import Path
import shutil
import subprocess
from app.connectors.bot import PROFILE


def run():
    PROFILE.mkdir(parents=True,exist_ok=True)
    if os.name!='nt':PROFILE.chmod(0o700)
    candidates=[os.getenv('MEETMIND_BOT_CHROME_EXECUTABLE'),shutil.which('google-chrome'),shutil.which('chromium')]
    for directory in ('PROGRAMFILES','PROGRAMFILES(X86)','LOCALAPPDATA'):
        if os.getenv(directory):candidates.append(str(Path(os.environ[directory])/'Google/Chrome/Application/chrome.exe'))
    executable=next((item for item in candidates if item and Path(item).is_file()),None)
    if not executable:raise RuntimeError('Google Chrome was not found. Set MEETMIND_BOT_CHROME_EXECUTABLE to its executable.')
    # This is a normal interactive Chrome window, without Playwright automation.
    # Only the account owner handles login/challenges. No cookie copying/export.
    process=subprocess.Popen([executable,'--user-data-dir='+str(PROFILE.resolve()),'--new-window','https://accounts.google.com/'],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('Sign in manually to a dedicated bot account in the browser. Close the window when finished.',flush=True)
    print('MeetMind does not read passwords, verification codes, or export cookies.',flush=True)
    process.wait()
    print('Sign-in browser closed. The bot can now reuse its own profile.',flush=True)


if __name__=='__main__':run()
