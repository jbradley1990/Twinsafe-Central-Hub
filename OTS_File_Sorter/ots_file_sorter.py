import argparse  # read command-line options
import json  # parse JSON files
import logging  # log to console
import sys  # redirect print() to logger
import os  # file size + atomic replace
import shutil  # copy/move files
import threading  # avoid processing the same folder twice
import time  # sleeping + timeouts
from pathlib import Path  # path handling
import platform  # detect OS
import ctypes  # Windows hidden file attribute

from watchdog.events import FileSystemEventHandler  # watchdog event handler base
from watchdog.observers.polling import PollingObserver  # polling observer (more reliable on network drives)


# -----------------------------
# Config (edit these two paths)
# -----------------------------

ROOT = Path("/mnt/otsdls")
INCOMING_ROOT = ROOT / "Incoming"


# -----------------------------
# Helpers
# -----------------------------

INVALID_WIN_CHARS = r'<>:"/\|?*'  # characters Windows paths can't contain


# -----------------------------
# Logging (circular file capped at 500 MiB by deleting oldest lines)
# -----------------------------

LOG_FILE = INCOMING_ROOT / "ots_file_sorter.log"  # log file
LOG_MAX_BYTES = 500 * 1024 * 1024  # 500 MiB cap


def hide_file(path: Path) -> None:
    """Hide a file (Windows: hidden attribute; non-Windows: no-op unless name starts with '.')."""
    try:
        if platform.system() == "Windows":
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(str(path), FILE_ATTRIBUTE_HIDDEN)
    except Exception:
        # Don't break the script if hiding fails (permissions, filesystem, etc.)
        logging.getLogger(__name__).exception("Failed to hide log file: %s", path)


class TailKeepingFileHandler(logging.Handler):
    """A 'circular' log file that deletes the oldest *lines* once the file exceeds max_bytes.

    Implementation:
      - Always append new log lines.
      - If the file grows beyond max_bytes, keep only the newest ~keep_ratio of bytes
        (rounded to the next newline), discarding the oldest lines.
    """

    def __init__(self, filename: str, max_bytes: int, keep_ratio: float = 0.9, encoding: str = "utf-8"):
        super().__init__()
        self.filename = filename
        self.max_bytes = int(max_bytes)
        self.keep_ratio = float(keep_ratio)
        self.encoding = encoding
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            # Append first so we never lose the newest line.
            with self._lock:
                with open(self.filename, "a", encoding=self.encoding, errors="replace") as f:
                    f.write(msg + "\n")
                self._trim_if_needed()
        except Exception:
            self.handleError(record)

    def _trim_if_needed(self) -> None:
        try:
            size = os.path.getsize(self.filename)
        except FileNotFoundError:
            return

        if size <= self.max_bytes:
            return

        # Keep the newest chunk of the file; discard old lines.
        keep_bytes = int(self.max_bytes * self.keep_ratio)
        keep_bytes = max(1, min(keep_bytes, self.max_bytes))

        # Copy the tail (aligned to the next newline) into a temp file, then atomically replace.
        tmp_path = self.filename + ".tmp"

        with open(self.filename, "rb") as src_f, open(tmp_path, "wb") as dst_f:
            # Seek to the start of the tail window.
            start = max(0, size - keep_bytes)
            src_f.seek(start)

            # If we didn't start from 0, discard the partial first line to keep line boundaries.
            if start > 0:
                _ = src_f.readline()  # discard until next newline

            # Copy remainder in chunks to avoid large RAM usage.
            while True:
                chunk = src_f.read(1024 * 1024)  # 1 MiB
                if not chunk:
                    break
                dst_f.write(chunk)

        os.replace(tmp_path, self.filename)


class _StreamToLogger:
    """File-like object that redirects writes (print) to a logger."""

    def __init__(self, logger: logging.Logger, level: int):
        self.logger = logger
        self.level = level
        self._buffer = ""

    def write(self, message: str) -> int:
        if not message:
            return 0
        self._buffer += message
        # Log whole lines; keep partial line buffered
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.rstrip()
            if line:
                self.logger.log(self.level, line)
        return len(message)

    def flush(self) -> None:
        line = self._buffer.strip()
        if line:
            self.logger.log(self.level, line)
        self._buffer = ""


def setup_logging() -> None:
    """Console + capped file logging, plus capture print() output; hides the log file on Windows."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # Console
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # Capped file (single file; deletes oldest lines once it reaches 500 MiB)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)  # ensure folder exists

        # Ensure the file exists so we can hide it immediately
        if not LOG_FILE.exists():
            LOG_FILE.touch()

        # Hide it (Windows only)
        hide_file(LOG_FILE)

        fh = TailKeepingFileHandler(
            filename=str(LOG_FILE),
            max_bytes=LOG_MAX_BYTES,
            keep_ratio=0.9,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except Exception:
        # If file logging fails (permissions, etc.), continue with console-only.
        root.exception("Failed to set up file logging: %s", LOG_FILE)

    # Capture print() calls (stdout/stderr) into the log
    sys.stdout = _StreamToLogger(logging.getLogger("STDOUT"), logging.INFO)
    sys.stderr = _StreamToLogger(logging.getLogger("STDERR"), logging.ERROR)


def safe_part(text: str, fallback: str) -> str:
    """Make a safe folder name for Windows and avoid empty parts."""
    text = (text or "").strip()  # normalise empty/None
    if not text:  # if missing
        return fallback  # use fallback
    return "".join("_" if c in INVALID_WIN_CHARS else c for c in text).strip()  # replace invalid chars


def wait_until_stable(path: Path, stable_for_s: float = 2.0, timeout_s: float = 60.0) -> bool:
    """Wait until a file stops changing (size/mtime) to avoid reading half-written files."""
    start = time.time()  # start time
    last = None  # last (size, mtime)
    stable_since = None  # when it became stable

    while time.time() - start < timeout_s:  # loop until timeout
        if not path.exists():  # file disappeared
            stable_since = None  # reset
            time.sleep(0.25)  # small wait
            continue  # keep looping

        stat = path.stat()  # read file stat
        current = (stat.st_size, stat.st_mtime)  # size + mtime tuple

        if current == last:  # unchanged
            if stable_since is None:  # first stable moment
                stable_since = time.time()  # mark
            if time.time() - stable_since >= stable_for_s:  # stable long enough
                return True  # good to read
        else:  # changed
            stable_since = None  # reset stability timer
            last = current  # update last seen

        time.sleep(0.25)  # avoid busy loop

    return False  # timed out


def load_json(path: Path) -> dict:
    """Load JSON with a clear error message."""
    with path.open("r", encoding="utf-8") as f:  # open file
        return json.load(f)  # parse JSON


def infer_unique_from_pdf_name(pdf_name: str) -> str:
    """
    Extract unique number from:
      OTSNumber_LineItem_UniqueNumber_Date_Time.pdf

    Returns the 3rd underscore-separated part (index 2).
    Example:
      12345_10A_7_9-1-2026_14-18-31.pdf -> "7"
    """
    stem = Path(pdf_name).stem  # filename without extension
    parts = stem.split("_")  # split into all parts

    # Expect at least 5 parts: OTS, LineItem, Unique, Date, Time
    if len(parts) < 5:
        return ""  # can't reliably parse

    return (parts[2] or "").strip()  # UniqueNumber


def add_status_to_pdf_name(pdf_name: str, decision: str) -> str:
    """
    Return filename with _PASS or _FAIL appended before .pdf
    Example: a_b_c.pdf -> a_b_c_PASS.pdf

    If it already ends with _PASS/_FAIL (case-insensitive), leave it unchanged.
    """
    p = Path(pdf_name)  # parse filename
    stem = p.stem  # name without extension
    suffix = p.suffix  # extension (includes the dot), e.g. ".pdf"

    decision = (decision or "").strip().lower()  # normalise
    tag = "PASS" if decision == "pass" else "FAIL"  # choose label

    upper_stem = stem.upper()  # for case-insensitive check
    if upper_stem.endswith("_PASS") or upper_stem.endswith("_FAIL"):  # already tagged
        return pdf_name  # leave unchanged

    return f"{stem}_{tag}{suffix}"  # append tag before extension


def ensure_dir(path: Path) -> None:
    """Create directory if missing."""
    path.mkdir(parents=True, exist_ok=True)  # make folders


# -----------------------------
# Core processing
# -----------------------------

def cleanup_run_folder(run_dir: Path, data_csvs: list, details_path: Path, status_path: Path) -> None:
    """Delete source files and the run folder if empty."""
    # Delete the source data CSVs
    for csv_path in data_csvs:
        try:
            csv_path.unlink()
        except Exception as e:
            logging.warning("Could not delete %s: %s", csv_path, e)

    # Delete the source details.json
    try:
        details_path.unlink()
    except Exception as e:
        logging.warning("Could not delete %s: %s", details_path, e)

    # Delete status.json
    try:
        status_path.unlink()
    except Exception as e:
        logging.warning("Could not delete %s: %s", status_path, e)

    # Remove folder if it is empty now
    try:
        next(run_dir.iterdir())
        logging.info("Run folder not empty (leftovers kept): %s", run_dir)
    except StopIteration:
        run_dir.rmdir()
        logging.info("Processed and removed run folder: %s", run_dir)


def process_calibration_run(
    run_dir: Path,
    details: dict,
    status_map: dict,
    details_path: Path,
    status_path: Path,
    data_csvs: list,
    pdfs: list,
    dry_run: bool = False,
) -> None:
    """Process a calibration run folder."""
    meta = details.get("metadata", {})
    data_logger = safe_part(meta.get("Data Logger"), "Unknown")
    date_time = (meta.get("Date Time") or "").strip()
    date_part = date_time.split("_")[0] if date_time else "Unknown_Date"
    date_folder = safe_part(date_part, "Unknown_Date")

    # Determine overall decision from the first entry in status.json
    decision = "pass"  # default
    if status_map:
        # Get the first value in the status map
        first_val = str(next(iter(status_map.values()))).strip().lower()
        if first_val == "fail":
            decision = "fail"
        # "none", "pass", or anything else defaults to "pass" per instructions

    dest_base = ROOT / "Calibration" / data_logger / date_folder
    dest_data_dir = dest_base / "Data"
    dest_pdf_dir = dest_base / "PDF" / ("Pass" if decision == "pass" else "Fail")

    if dry_run:
        logging.info("[DRY] Calibration routing to %s", dest_base)
    else:
        ensure_dir(dest_data_dir)
        ensure_dir(dest_pdf_dir)

    # Copy Data (CSV and details.json)
    for csv_path in data_csvs:
        target_csv = dest_data_dir / csv_path.name
        if dry_run:
            logging.info("[DRY] Copy %s -> %s", csv_path, target_csv)
        else:
            shutil.copy2(csv_path, target_csv)

    target_details = dest_data_dir / details_path.name
    if dry_run:
        logging.info("[DRY] Copy %s -> %s", details_path, target_details)
    else:
        shutil.copy2(details_path, target_details)

    # Move all PDFs to the decision folder
    for pdf_path in pdfs:
        new_pdf_name = add_status_to_pdf_name(pdf_path.name, decision)
        dest_pdf_path = dest_pdf_dir / new_pdf_name
        if dry_run:
            logging.info("[DRY] Move %s -> %s", pdf_path, dest_pdf_path)
        else:
            shutil.move(str(pdf_path), str(dest_pdf_path))

    if dry_run:
        logging.info("[DRY] Cleanup would delete inputs in %s", run_dir)
    else:
        cleanup_run_folder(run_dir, data_csvs, details_path, status_path)


_processing_lock = threading.Lock()  # lock for processing set
_processing_folders = set()  # folders currently being processed


def process_run_folder(run_dir: Path, dry_run: bool = False) -> None:
    """Process one run folder inside Incoming."""
    if not run_dir.is_dir():  # must be a directory
        return  # ignore

    status_path = run_dir / "status.json"  # gating file
    if not status_path.exists():  # don't do anything until present
        return  # exit

    # Stop double-processing the same folder
    with _processing_lock:  # lock shared state
        if str(run_dir) in _processing_folders:  # already in progress
            return  # skip
        _processing_folders.add(str(run_dir))  # mark in progress

    try:
        # Wait for status.json to finish writing
        if not wait_until_stable(status_path, stable_for_s=2.0, timeout_s=120.0):  # wait for stable file
            logging.warning("status.json not stable yet: %s", status_path)  # log
            return  # try next event/scan

        # Find details json (e.g. 9-1-2026_14-18-31_details.json)
        details_files = sorted(run_dir.glob("*_details.json"))  # locate details json(s)
        if not details_files:  # none found
            logging.warning("No *_details.json found in %s", run_dir)  # log
            return  # can't route without metadata
        details_path = details_files[0]  # take the first match

        # Wait for details.json to finish writing too
        if not wait_until_stable(details_path, stable_for_s=2.0, timeout_s=120.0):  # wait for stable file
            logging.warning("details.json not stable yet: %s", details_path)  # log
            return  # try later

        # Load details.json + status.json
        details = load_json(details_path)  # parse details
        status_map = load_json(status_path)  # parse status

        # Collect run files
        data_csvs = sorted(run_dir.glob("*_data_*.csv"))  # all split packets
        pdfs = sorted(run_dir.glob("*.pdf"))  # all pdfs

        # BRANCH: Calibration vs Standard
        if "calibration" in details:
            process_calibration_run(
                run_dir, details, status_map, details_path, status_path, data_csvs, pdfs, dry_run
            )
            return

        meta = details.get("metadata", {})  # metadata object
        ots_number = safe_part(meta.get("OTS Number"), "UNKNOWN_OTS_NUMBER")  # OTS Number folder
        line_item = safe_part(meta.get("Line Item"), "UNKNOWN_LINE_ITEM")  # Line Item folder

        # Extract unique numbers from channel_info where unique_number != ""
        unique_numbers = []  # list of uniques
        for ci in details.get("channel_info", []):  # iterate channels
            u = (ci.get("unique_number") or "").strip()  # read unique_number
            if u:  # keep only non-empty
                unique_numbers.append(u)  # append

        unique_numbers = sorted(set(unique_numbers))  # de-duplicate + sort
        if not unique_numbers:  # nothing to route to
            logging.warning("No unique_number entries found in channel_info for %s", run_dir)  # log
            return  # can't proceed

        # Create destination folders (one per unique number)
        dest_base_by_unique = {}  # mapping unique -> destination base folder
        for u in unique_numbers:  # each unique folder
            dest_base = ROOT / ots_number / line_item / safe_part(u, "UNKNOWN_UNIQUE")  # build base path
            ensure_dir(dest_base)  # create it

            ensure_dir(dest_base / "Data")  # create data folder

            ensure_dir(dest_base / "PDF" / "Pass")  # create pass folder
            ensure_dir(dest_base / "PDF" / "Fail")  # create fail folder
            ensure_dir(dest_base / "PDF")  # create pdf root too (just in case)
            dest_base_by_unique[u] = dest_base  # store

        # Copy data and details into each unique folder
        for u, dest_base in dest_base_by_unique.items():  # loop each target unique
            dest_data_dir = dest_base / "Data"  # data folder
            ensure_dir(dest_data_dir)  # ensure data folder exists

            # Copy details.json
            target_details = dest_data_dir / details_path.name  # destination path for details.json
            if dry_run:  # if dry-run
                logging.info("[DRY] Copy %s -> %s", details_path, target_details)  # log
            else:
                shutil.copy2(details_path, target_details)  # copy with metadata

            # Copy each data packet CSV
            for csv_path in data_csvs:  # each csv packet
                target_csv = dest_data_dir / csv_path.name  # destination path for csv
                if dry_run:  # if dry-run
                    logging.info("[DRY] Copy %s -> %s", csv_path, target_csv)  # log
                else:
                    shutil.copy2(csv_path, target_csv)  # copy with metadata

        # Move PDFs according to status.json
        # status.json is expected to map unique number -> "pass"/"fail"/"none"
        for pdf_path in pdfs:  # each pdf
            pdf_unique = infer_unique_from_pdf_name(pdf_path.name)  # derive unique number from filename
            pdf_unique = (pdf_unique or "").strip()  # normalise

            if not pdf_unique:  # can't match
                logging.warning("Could not infer unique number from PDF: %s", pdf_path.name)  # log
                continue  # skip

            decision = (status_map.get(pdf_unique) or "").strip().lower()  # pass/fail/none/empty
            if decision == "none" or decision == "":  # ignore "none" / missing
                logging.info("Ignoring PDF (status none/empty): %s", pdf_path.name)  # log
                continue  # leave it in place

            if pdf_unique not in dest_base_by_unique:  # unique not in details.json list
                logging.warning("PDF unique '%s' not in details channel_info; PDF left: %s", pdf_unique, pdf_path.name)  # log
                continue  # skip

            if decision not in ("pass", "fail"):  # unknown value
                logging.warning("Unknown status '%s' for PDF %s; left in place", decision, pdf_path.name)  # log
                continue  # skip

            dest_pdf_dir = dest_base_by_unique[pdf_unique] / "PDF" / ("Pass" if decision == "pass" else "Fail")  # choose folder
            new_pdf_name = add_status_to_pdf_name(pdf_path.name, decision)  # add PASS/FAIL to filename
            dest_pdf_path = dest_pdf_dir / new_pdf_name  # full destination path

            if dry_run:  # if dry-run
                logging.info("[DRY] Move %s -> %s", pdf_path, dest_pdf_path)  # log
            else:
                shutil.move(str(pdf_path), str(dest_pdf_path))  # move PDF

        # If we got here, copies/moves were successful, so we can clean up incoming files
        if dry_run:
            logging.info("[DRY] Cleanup would delete inputs in %s", run_dir)
        else:
            cleanup_run_folder(run_dir, data_csvs, details_path, status_path)

    except Exception:
        logging.exception("Failed processing folder: %s", run_dir)  # log stack trace
    finally:
        with _processing_lock:  # lock shared state
            _processing_folders.discard(str(run_dir))  # unmark in progress


# -----------------------------
# Watchdog plumbing
# -----------------------------

class IncomingEventHandler(FileSystemEventHandler):
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run  # store dry-run option

    def on_created(self, event):
        self._handle(event)  # handle on create

    def on_moved(self, event):
        self._handle(event)  # handle on move (common on network shares)

    def on_modified(self, event):
        self._handle(event)  # handle on modify (status.json appears/finishes)

    def _handle(self, event):
        path = Path(event.src_path)  # event path
        run_dir = path if event.is_directory else path.parent  # folder containing files
        # Only act on direct subfolders of Incoming
        # (e.g. Incoming\9-1-2026_14-18-31\status.json)
        if run_dir.parent == INCOMING_ROOT:  # only immediate run folders
            process_run_folder(run_dir, dry_run=self.dry_run)  # attempt processing


def scan_existing(dry_run: bool = False) -> None:
    """On startup, process anything already sitting in Incoming."""
    if not INCOMING_ROOT.exists():  # incoming must exist
        logging.error("Incoming root does not exist: %s", INCOMING_ROOT)  # log
        return  # stop
    for child in INCOMING_ROOT.iterdir():  # each item inside Incoming
        if child.is_dir():  # only folders
            process_run_folder(child, dry_run=dry_run)  # attempt processing


def main() -> None:
    parser = argparse.ArgumentParser(description="Watch Incoming folder and route OTS DLS files")  # CLI
    parser.add_argument("--dry-run", action="store_true", help="Log actions without changing files")  # option
    parser.add_argument("--poll", type=float, default=2.0, help="Polling interval in seconds (default: 2.0)")  # option
    args = parser.parse_args()  # parse options

    setup_logging()

    logging.info("Incoming: %s", INCOMING_ROOT)  # show config
    logging.info("Dest root: %s", ROOT)  # show config
    logging.info("Dry-run: %s", args.dry_run)  # show mode

    scan_existing(dry_run=args.dry_run)  # process anything already present

    handler = IncomingEventHandler(dry_run=args.dry_run)  # event handler
    observer = PollingObserver(timeout=args.poll)  # polling observer (good for mapped drives)
    observer.schedule(handler, str(INCOMING_ROOT), recursive=True)  # watch Incoming recursively
    observer.start()  # start watching

    logging.info("Watching for new run folders... (Ctrl+C to stop)")  # log
    try:
        while True:  # run forever
            time.sleep(1)  # idle loop
    except KeyboardInterrupt:
        logging.info("Stopping watcher...")  # log
    finally:
        observer.stop()  # stop observer
        observer.join()  # wait for stop


if __name__ == "__main__":
    main()  # entry point