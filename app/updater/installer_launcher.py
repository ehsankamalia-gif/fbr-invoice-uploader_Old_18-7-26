import os
import sys
import subprocess
import logging

logger = logging.getLogger(__name__)

class InstallerLauncher:
    """
    Handles closing the current application and launching the new installer.
    """
    
    @staticmethod
    def launch_and_exit(installer_path: str):
        """
        Launches the installer and exits the current process.
        Args:
            installer_path: Path to the downloaded .exe installer.
        """
        try:
            if not os.path.exists(installer_path):
                logger.error(f"Installer not found at {installer_path}")
                return False

            # On Windows, os.startfile() is the cleanest way to hand-off
            # It launches the process detached from the current one
            logger.info(f"Launching installer: {installer_path}")
            
            if sys.platform == "win32":
                os.startfile(installer_path)
            else:
                # Fallback for other platforms (though user specified Windows)
                subprocess.Popen([installer_path], start_new_session=True)

            # Exit the current application immediately
            # This is important so the installer can overwrite the files
            logger.info("Exiting application for update...")
            sys.exit(0)
            
        except Exception as e:
            logger.error(f"Failed to launch installer: {e}")
            return False
