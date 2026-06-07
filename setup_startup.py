"""
setup_startup.py — MAX v4.8 (Startup Installer)
- Automatically creates a Windows Startup shortcut for start.bat.
- Uses native PowerShell via subprocess (Zero external dependencies).
"""
import os
import sys
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MAX.STARTUP_SETUP")

def add_max_to_windows_startup():
    if sys.platform != "win32":
        logger.error("Platform is not Windows. Startup automation skipped.")
        return False

    # 1. Paths nikaalo
    root_dir = os.path.dirname(os.path.abspath(__file__))
    bat_path = os.path.join(root_dir, "start.bat")
    
    if not os.path.exists(bat_path):
        logger.error(f"Error: Could not find start.bat at {bat_path}")
        return False

    # 2. Windows Startup folder ka path dhoondho
    app_data = os.environ.get("APPDATA")
    if not app_data:
        logger.error("APPDATA environment variable not found.")
        return False
        
    startup_folder = os.path.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    shortcut_path = os.path.join(startup_folder, "MAX_Assistant.lnk")

    # 3. PowerShell Command taiyar karo shortcut banane ke liye
    # WindowStyle = 7 ka matlab hai hamesha 'Minimized' (background) mein start hoga, screen par popup nahi karega!
    ps_command = f"""
    $WshShell = New-Object -ComObject WScript.Shell;
    $Shortcut = $WshShell.CreateShortcut('{shortcut_path}');
    $Shortcut.TargetPath = '{bat_path}';
    $Shortcut.WorkingDirectory = '{root_dir}';
    $Shortcut.WindowStyle = 7;
    $Shortcut.Save();
    """

    try:
        logger.info("Generating Windows Startup shortcut via PowerShell...")
        # PowerShell command execute karo silently
        subprocess.run(
            ["powershell", "-Command", ps_command], 
            check=True, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        logger.info(f"Success! MAX has been added to Windows Startup.")
        logger.info(f"Shortcut created at: {shortcut_path}")
        print("\n[SUCCESS] MAX ab PC startup par successfully add ho gayi hai! [SUCCESS]\n")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"PowerShell shortcut generation failed: {e.stderr.decode().strip()}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return False

def remove_max_from_windows_startup():
    if sys.platform != "win32":
        logger.error("Platform is not Windows. Startup automation skipped.")
        return False

    # 1. Windows Startup folder ka path dhoondho
    app_data = os.environ.get("APPDATA")
    if not app_data:
        logger.error("APPDATA environment variable not found.")
        return False
        
    startup_folder = os.path.join(app_data, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    shortcut_path = os.path.join(startup_folder, "MAX_Assistant.lnk")

    if os.path.exists(shortcut_path):
        try:
            os.remove(shortcut_path)
            logger.info("Successfully removed MAX from Windows Startup.")
            print("\n[SUCCESS] MAX ko Windows Startup se remove kar diya gaya hai! [REMOVED]\n")
            return True
        except Exception as e:
            logger.error(f"Failed to remove shortcut: {e}")
            return False
    else:
        logger.info("MAX is not currently registered in Windows Startup.")
        print("\n[INFO] MAX startup menu mein nahi mili (already removed).\n")
        return True

if __name__ == "__main__":
    print("=============================================")
    print("     MAX AI - Startup Installer/Uninstaller  ")
    print("=============================================")
    if len(sys.argv) > 1 and sys.argv[1] in ["--remove", "-r", "remove"]:
        remove_max_from_windows_startup()
    else:
        add_max_to_windows_startup()