"""Application-wide logging configuration."""

import logging
import sys

_FORMAT = "%(asctime)s:\t%(levelname)s:\t%(name)s\t%(funcName)s:\t%(message)s"


def _harden_console_encoding() -> None:
    """Stop an un-encodable character in a log message from killing a run.

    On Windows the console hands Python a cp1252 stream. TFS metadata and
    filenames carry symbols that codec cannot represent — Greek mu (U+03BC,
    one of the three micro-sign spellings TFS emits) and the Angstrom sign
    both raise UnicodeEncodeError, while the more common U+00B5 micro sign
    happens to survive. Logging a parse failure for such a file would then
    raise from inside the logger, turning a skipped image into a crash.
    Degrading those characters to escapes keeps the message readable and
    the run alive.
    """

    for stream in (sys.stderr, sys.stdout):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(errors="backslashreplace")
        except (ValueError, OSError):
            # Redirected to something that cannot be reconfigured; the
            # handler below still works, it just may not be lossless.
            pass


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger for the application."""

    _harden_console_encoding()

    logging.basicConfig(
        format=_FORMAT,
        level=level,
        force=True,
    )


def attach_file_handler(path: str) -> None:
    """Attach a plain file handler alongside the console one.

    Only used when the operator passes --log-file; the default remains
    console-only to match the rest of the app family.
    """

    # UTF-8 explicitly: the file must hold the µ and μ that appear in TFS
    # filenames and metadata, whatever the console code page is.
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(_FORMAT))
    logging.getLogger().addHandler(handler)
