"""Production data analysis utilities."""

import pandas as pd
import numpy as np
import warnings


def locate_key_time_rows(cleaned_data, hold_info: pd.Series, channel_unique_number: str, production=False):
    """Return indices of key time points closest to provided timestamps.
       Always includes all rows, leaving blanks for missing timestamps.
    """
    date_time_index = cleaned_data.set_index('Datetime')

    def parse_time(value):
        if pd.isna(value) or str(value).strip() == "":
            return None
        return pd.to_datetime(
            value,
            format="%Y-%m-%dT%H:%M:%S.%f",
            errors="coerce",
        )

    # Parse timestamps
    sos_time = parse_time(hold_info.get('start_of_stabilisation'))
    soh_time = parse_time(hold_info.get('start_of_hold'))
    eoh_time = parse_time(hold_info.get('end_of_hold'))

    # Use the new column naming format (just the unique_number)
    pressure_col = str(channel_unique_number)
    pressure_col_display = f"{pressure_col} (psi)"

    # Prep index table (always show all, blank if missing)
    index_data = {
        'SOS_Index': [None],
        'SOH_Index': [None],
        'EOH_Index': [None]
    }

    # Default blank table rows
    labels = ['Start of Stabilisation', 'Start of Hold', 'End of Hold']
    times   = [sos_time, soh_time, eoh_time]

    display_table_data = {
        '': labels,
        'Datetime': ['' for _ in labels],
        pressure_col_display: ['' for _ in labels],
        'Ambient Temperature (°C)': ['' for _ in labels]
    }

    # Populate only where valid
    for i, (label, ts) in enumerate(zip(labels, times)):
        if ts is None or pd.isna(ts):
            continue

        # Find nearest index
        nearest_idx = date_time_index.index.get_indexer([ts], method="nearest")[0]

        # Fill index table
        if label == 'Start of Stabilisation':
            index_data['SOS_Index'][0] = nearest_idx
        elif label == 'Start of Hold':
            index_data['SOH_Index'][0] = nearest_idx
        elif label == 'End of Hold':
            index_data['EOH_Index'][0] = nearest_idx

        # Fill display table
        pressure_val = cleaned_data.loc[nearest_idx, pressure_col]

        temp_val = cleaned_data.loc[nearest_idx, 'Ambient Temperature']

        display_table_data['Datetime'][i] = ts.strftime("%d/%m/%Y %H:%M:%S")
        display_table_data[pressure_col_display][i] = int(pressure_val)
        display_table_data['Ambient Temperature (°C)'][i] = temp_val

    holds_indices = pd.DataFrame(index_data)
    display_table = pd.DataFrame(display_table_data)

    return holds_indices, display_table


def locate_calibration_points(cleaned_data, calibration_info):
    """Find the indices for calibration start and end points."""
    calibration_indices = pd.DataFrame(index=range(2), columns=range(len(calibration_info['key_points'])))
    date_time_index = cleaned_data.set_index('Datetime')

    for i, key_point in enumerate(calibration_info['key_points']):
        start_time = pd.to_datetime(key_point, errors="coerce")
        if pd.isna(start_time):
             continue
        end_time = start_time + pd.Timedelta(seconds=10)

        calibration_indices.iloc[0, i] = date_time_index.index.get_indexer([start_time], method="nearest")[0]
        calibration_indices.iloc[1, i] = date_time_index.index.get_indexer([end_time], method="nearest")[0]

    return calibration_indices


def calculate_succesful_calibration(cleaned_data, calibration_indices, calibration_info):
    """Calculate average counts, converted values, and errors for calibration."""
    display_table = pd.DataFrame()

    channel_index = calibration_info['channel_index']

    if channel_index <= 8:
        applied_values = [4000, 8000, 12000, 16000, 20000]
        index_labels = ['Applied (µA)', 'Counts (avg)', 'Converted (µA)', 'Abs Error (µA) - ±3.6 µA']
    elif channel_index == 9:
        applied_values = [-5.89, 9.28, 24.46, 39.64, 54.81]
        index_labels = ['Applied (mV)', 'Counts (avg)', 'Converted (mV)', 'Abs Error (mV) - ±0.12 mV']
    else:
        applied_values = [0, 0, 0, 0, 0]
        index_labels = ['Applied', 'Counts (avg)', 'Converted', 'Abs Error']

    # Adjust applied_values length if necessary (though normally it's 5)
    num_points = len(calibration_indices.columns)
    if len(applied_values) > num_points:
        applied_values = applied_values[:num_points]
    elif len(applied_values) < num_points:
        applied_values = applied_values + [0] * (num_points - len(applied_values))

    slope = (applied_values[-1] - applied_values[0]) / calibration_info['max_range']
    intercept = applied_values[0]

    counts_series = pd.Series(dtype=float)
    expected_series = pd.Series(dtype=float)
    abs_error_series = pd.Series(dtype=float)

    for i in range(num_points):
        start_idx = calibration_indices.iloc[0, i]
        end_idx = calibration_indices.iloc[1, i]

        counts = cleaned_data.loc[start_idx:end_idx, "Calibrated Channel"].mean()
        converted = (slope * counts) + intercept
        error = applied_values[i] - converted

        counts_series.loc[i+1] = counts
        expected_series.loc[i+1] = applied_values[i]
        abs_error_series.loc[i+1] = abs(error)

        display_table.loc[0, i+1] = applied_values[i]
        display_table.loc[1, i+1] = int(round(counts))
        display_table.loc[2, i+1] = round(converted, 3)
        display_table.loc[3, i+1] = round(abs(error), 2)

    display_table.index = index_labels
    display_table.insert(0, "0", display_table.index)

    return display_table, counts_series, expected_series, abs_error_series


def calculate_calibration_regression(counts: pd.Series, expected_counts: pd.Series) -> pd.Series:
    """Return polynomial coefficients mapping counts to expected counts."""

    labels = ["S3", "S2", "S1", "S0"]
    if counts is None or expected_counts is None:
        return pd.Series([np.nan] * 4, index=labels, dtype=float)

    counts_series = pd.to_numeric(pd.Series(counts), errors="coerce")
    expected_series = pd.to_numeric(pd.Series(expected_counts), errors="coerce")
    mask = ~(counts_series.isna() | expected_series.isna())

    valid_counts = counts_series[mask]
    valid_expected = expected_series[mask]

    if len(valid_counts) < 2:
        return pd.Series([np.nan] * 4, index=labels, dtype=float)

    degree = min(3, len(valid_counts) - 1)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        coefficients = np.polyfit(valid_counts, valid_expected, deg=degree)

    padded = np.full(4, np.nan)
    padded[-(degree + 1):] = coefficients
    return pd.Series(padded, index=labels, dtype=float)
