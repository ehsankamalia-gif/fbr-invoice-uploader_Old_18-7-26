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

            # Exit the current application immediately so the installer can
            # overwrite our files. This runs inside a Qt slot invoked via
            # Qt's C++ event dispatch, not a plain Python call chain back to
            # qt_main.py's app.exec() - sys.exit() only raises SystemExit,
            # which PyQt6 catches and swallows for exceptions raised inside
            # slots (it logs them and keeps the event loop running), so the
            # old process never actually terminated even though the
            # installer correctly overwrote the files on disk. os._exit()
            # is an immediate, unconditional OS-level termination that
            # nothing can intercept.
            logger.info("Exiting application for update...")
            os._exit(0)
            
        except Exception as e:
            logger.error(f"Failed to launch installer: {e}")
            return False
