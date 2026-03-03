import tkinter as tk
import logging
from host.core.device_manager import DeviceManager
from host.gui.main_view import MainView # <-- IMPORT THE NEW VIEW

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)-22s] %(levelname)-8s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    log = logging.getLogger(__name__)
    log.info("Starting MVC Host Application...")

    # 1. Create the backend DeviceManager instance
    manager = DeviceManager()
    manager.start() # <-- START THE MANAGER'S BACKGROUND THREADS

    # 2. Create the Tkinter root window
    root = tk.Tk()

    # 3. Create the GUI View, injecting the manager into it
    app = MainView(root, manager)

    # 4. Start the Tkinter event loop
    root.mainloop()
    
    # This will run after the window is closed
    log.info("Application has been closed.")

if __name__ == "__main__":
    main()