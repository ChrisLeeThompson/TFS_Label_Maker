# This Python file uses the following encoding: utf-8
"""TFS Label Maker — application entry point."""

from __future__ import annotations

import argparse
import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from tfs_lm import __version__, defaults, paths
from tfs_lm.app_controller import AppController
from tfs_lm.logging_setup import attach_file_handler, setup_logging

logger = logging.getLogger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tfs_label_maker",
        description="Build styled labels from TFS microscope image metadata.",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Log at DEBUG level."
    )
    parser.add_argument(
        "--log-file",
        metavar="PATH",
        help="Also write the log to this file. Console-only by default.",
    )
    # parse_known_args so Qt's own flags (-style, -platform, ...) pass through.
    args, _ = parser.parse_known_args(argv[1:])
    return args


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    args = parse_args(argv)
    setup_logging(logging.DEBUG if args.verbose else logging.INFO)
    if args.log_file:
        attach_file_handler(args.log_file)

    logger.info("Starting TFS Label Maker v%s", __version__)

    app = QGuiApplication(argv)
    app.setOrganizationName(defaults.ORGANIZATION_NAME)
    app.setApplicationName(defaults.APPLICATION_NAME)

    # Must precede the engine load, or the controls fall back to Basic.
    QQuickStyle.setStyle("Universal")
    app.setWindowIcon(QIcon(str(paths.assets_dir() / "catbug_waiting_color.svg")))

    # Built before the engine so every QML binding target exists at load.
    app_controller = AppController()
    app.aboutToQuit.connect(app_controller.shutdown)

    engine = QQmlApplicationEngine()
    engine.quit.connect(app.quit)
    engine.addImportPath(str(paths.qml_dir()))
    engine.rootContext().setContextProperty("appController", app_controller)
    engine.rootContext().setContextProperty("appVersion", __version__)

    engine.load(str(paths.qml_dir() / "main.qml"))
    if not engine.rootObjects():
        logger.error("Failed to load QML file")
        return -1

    # Deferred so the window paints before any filesystem work happens.
    QTimer.singleShot(0, app_controller.initialize)

    result = app.exec()

    del engine

    return result


if __name__ == "__main__":
    sys.exit(main())
