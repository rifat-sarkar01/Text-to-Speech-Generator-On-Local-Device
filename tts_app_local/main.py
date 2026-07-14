import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from gui import TTSApp

__version__ = "1.0.0"

if __name__ == "__main__":
    app = TTSApp(version=__version__)
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
