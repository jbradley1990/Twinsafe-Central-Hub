"""Helpers for loading CSV test data."""

import pandas as pd
import json


def load_test_information(test_details_path: str):
    """Load all test information from the details JSON file."""

    with open(test_details_path) as f:
        root = json.load(f)

    if "calibration" in root:
        test_metadata = root.get("metadata", {})
        calibration = root["calibration"]
        return test_metadata, calibration

    test_metadata = root["metadata"]
    channel_info = pd.DataFrame(root["channel_info"])

    # Filter to only visible channels with unique_number
    channel_info = channel_info[channel_info["visible"] == True].reset_index(drop=True)

    return test_metadata, channel_info

def prepare_primary_data(primary_data_path: str, info_obj):
    """Load the primary data CSV and return cleaned data with mapped columns."""
    # Load raw data from CSV with performance optimizations
    try:
        raw_data = pd.read_csv(primary_data_path, engine='c', low_memory=False)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"File not found: {primary_data_path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise ValueError(f"File is empty: {primary_data_path}") from exc
    except Exception as exc:
        raise Exception(f"Error reading file {primary_data_path}: {exc}") from exc

    # Build column mapping based on what's actually in the CSV
    column_map = {}
    if isinstance(info_obj, dict) and "channel_index" in info_obj:
        # Calibration mode
        channel_index = info_obj["channel_index"]
        active_channels = ["Calibrated Channel"]

        col_name = str(channel_index)
        unnamed_name = f"Unnamed: {channel_index}"
        if col_name in raw_data.columns:
            column_map[col_name] = "Calibrated Channel"
        elif unnamed_name in raw_data.columns:
            column_map[unnamed_name] = "Calibrated Channel"
    else:
        # Production mode
        channel_info = info_obj
        unique_numbers = channel_info["unique_number"].tolist()
        active_channels = [uid for uid in unique_numbers if uid]

        for idx, uid in enumerate(unique_numbers, start=1):
            if not uid:
                continue
            col_name = str(idx)
            unnamed_name = f"Unnamed: {idx}"
            if col_name in raw_data.columns:
                column_map[col_name] = uid
            elif unnamed_name in raw_data.columns:
                column_map[unnamed_name] = uid

    # Rename columns to meaningful names
    raw_data = raw_data.rename(columns=column_map)

    # Ensure Datetime column is properly formatted
    # format is provided for speed; cache=True is default in modern pandas
    raw_data["Datetime"] = pd.to_datetime(
        raw_data["Datetime"],
        format="%Y-%m-%dT%H:%M:%S.%f",
        errors="coerce",
    )

    # Drop duplicate timestamps early to reduce data size
    raw_data = raw_data.drop_duplicates(subset=["Datetime"], keep="first")

    # Ensure Datetime is monotonic for nearest index searches
    raw_data = raw_data.sort_values("Datetime").reset_index(drop=True)

    # Keep only Datetime, active channel data, and Ambient Temperature
    if isinstance(info_obj, dict) and "channel_index" in info_obj:
        required_columns = ["Datetime", "Calibrated Channel", "Ambient Temperature"]
    else:
        required_columns = ["Datetime"] + active_channels + ["Ambient Temperature"]
    # Filter to only columns that actually exist to avoid KeyError
    required_columns = [c for c in required_columns if c in raw_data.columns]
    data_subset = raw_data[required_columns].copy()

    return data_subset, active_channels
