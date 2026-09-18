"""DeskFlow launcher.

Run with:  python main.py
"""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from config import APP_NAME, APP_VERSION
from data_manager import DataManager
from main_window import MainWindow

GLOBAL_QSS = """
QMainWindow { background-color: #F7F6F3; }
QMenuBar { background-color: #FFFFFF; border-bottom: 1px solid #E2E0DB; }
QMenuBar::item { padding: 5px 10px; background: transparent; }
QMenuBar::item:selected { background-color: #F5F3EF; }
QMenu { background-color: #FFFFFF; border: 1px solid #E2E0DB; padding: 4px; }
QMenu::item { padding: 5px 22px; }
QMenu::item:selected { background-color: #F5F3EF; }
QMenu::separator { height: 1px; background: #E2E0DB; margin: 4px 8px; }
QToolBar { background-color: #FFFFFF; border-bottom: 1px solid #E2E0DB; spacing: 4px; }
QToolBar QToolButton { padding: 4px 9px; border-radius: 3px; color: #1A1A1A; }
QToolBar QToolButton:hover { background-color: #F5F3EF; }
QToolBar QToolButton:checked { background-color: #E8EDF2; }
QStatusBar { background-color: #FFFFFF; border-top: 1px solid #E2E0DB; color: #8C8C8C; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #D8D6D1; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal { background: #D8D6D1; border-radius: 5px; min-width: 24px; }
QMessageBox { background-color: #F7F6F3; }
"""


def parse_args(argv):
    """Command line options; unknown arguments are left for Qt."""
    parser = argparse.ArgumentParser(
        prog=APP_NAME,
        description="A quiet desktop board for sticky notes, mind maps and tasks.",
    )
    parser.add_argument(
        "--data-dir",
        dest="data_dir",
        default=None,
        help="folder that stores projects (default: the app's own data folder)",
    )
    parser.add_argument(
        "--version", action="version", version="{} {}".format(APP_NAME, APP_VERSION)
    )
    return parser.parse_known_args(argv)[0]


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    args = parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_QSS)

    window = MainWindow(DataManager(data_root=args.data_dir))
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
