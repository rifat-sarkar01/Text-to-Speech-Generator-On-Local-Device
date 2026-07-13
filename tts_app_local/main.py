import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from gui import TTSApp


if __name__ == "__main__":
    app = TTSApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()
