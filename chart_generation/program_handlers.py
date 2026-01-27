"""Production and Calibration chart report generators."""

from pathlib import Path
from datetime import datetime
import shutil
from typing import List, Dict, Any
import pandas as pd

from graph_plotter import (
    plot_production_channel_data,
    plot_crosses,
    plot_calibration_data
)
from pdf_helpers import (
    draw_table,
    draw_production_test_details,
    draw_calibration_test_details,
    insert_plot_and_logo,
    draw_regression_table
)
from additional_info_functions import (
    locate_key_time_rows,
    locate_calibration_points,
    calculate_succesful_calibration,
    calculate_calibration_regression
)


class BaseReportGenerator:
    def __init__(self, **kwargs):
        self.program_name = kwargs.get("program_name")
        self.pdf_output_path = kwargs.get("pdf_output_path")
        self.test_metadata = kwargs.get("test_metadata")
        self.active_channels = kwargs.get("active_channels")
        self.cleaned_data = kwargs.get("cleaned_data")
        self.info_obj = kwargs.get("info_obj")
        self.pdf_copy_dir = Path("/var/opt/codesys/PlcLogic/trend_data/static/pdfs")

        if isinstance(self.test_metadata, pd.DataFrame):
            self.test_metadata = self.test_metadata.iloc[:, 0].to_dict()
        elif isinstance(self.test_metadata, pd.Series):
            self.test_metadata = self.test_metadata.to_dict()

    def finalize_output_path(self, temp_path: Path) -> Path:
        """Rename the temporary PDF path to its final name and return it."""
        name = temp_path.name

        if not name.endswith(".tmp.pdf"):
            return temp_path

        final_path = Path(temp_path.parent, name[:-8] + ".pdf")

        if final_path.exists():
            final_path.unlink()

        if not temp_path.exists():
            return final_path

        temp_path.replace(final_path)
        self.copy_pdf(final_path)
        return final_path

    def copy_pdf(self, pdf_path: Path) -> None:
        """Copy the generated PDF to the configured copy directory."""
        if not pdf_path.exists():
            return

        try:
            self.pdf_copy_dir.mkdir(parents=True, exist_ok=True)
            destination = self.pdf_copy_dir / pdf_path.name
            if destination.resolve() == pdf_path.resolve():
                return

            shutil.copy2(pdf_path, destination)
        except Exception:
            # Skip copying if we don't have permissions or other issues
            pass

    def generate(self) -> List[Path]:
        """Generate the report."""
        raise NotImplementedError


class ProductionReportGenerator(BaseReportGenerator):
    """Generate per-channel production reports."""

    def build_output_path(self, test_metadata) -> Path:
        """Construct the output PDF path from metadata."""
        ots_number = test_metadata.get('OTS Number') or 'Unknown'
        line_item = test_metadata.get('Line Item') or 'Unknown'
        unique_number = test_metadata.get('Unique Number') or 'Unknown'
        date_time_raw = test_metadata.get('Date Time', '')

        return self.pdf_output_path / f"{ots_number}_{line_item}_{unique_number}_{date_time_raw}.tmp.pdf"

    def generate(self) -> List[Path]:
        """Generate reports for all visible channels."""
        # Identify visible channels to process
        channel_info = self.info_obj
        visible_channels = [
            row for _, row in channel_info.iterrows()
            if row.get("visible", False)
        ]

        if not visible_channels:
            return []

        generated_paths = []
        for channel in visible_channels:
            generated_paths.append(self.generate_single_report(channel))

        return generated_paths

    def generate_single_report(self, channel_info: pd.Series):
        is_table = True

        unique_number = channel_info["unique_number"]
        channel_col = str(unique_number)

        # Build cleaned_data with the specific channel
        # Ensure we only pick one column even if there are duplicates in self.cleaned_data
        source_cols = list(self.cleaned_data.columns)
        try:
            dt_idx = source_cols.index("Datetime")
            ch_idx = source_cols.index(channel_col)
            at_idx = source_cols.index("Ambient Temperature")
            cleaned_data = self.cleaned_data.iloc[:, [dt_idx, ch_idx, at_idx]].copy()
        except ValueError:
            # Fallback to standard selection if something is missing
            cleaned_data = self.cleaned_data[[
                "Datetime",
                channel_col,
                "Ambient Temperature"
            ]].copy()

        # Copy metadata so you don't mutate shared dict
        metadata = dict(self.test_metadata)
        metadata["Unique Number"] = unique_number

        unique_path = self.build_output_path(metadata)

        # Ensure output directory exists
        unique_path.parent.mkdir(parents=True, exist_ok=True)

        # Get key point indices and display table
        key_point_indicies, display_table = locate_key_time_rows(
            cleaned_data,
            channel_info,
            unique_number,
            production=True
        )

        # Plot the production channel data
        figure, ax = plot_production_channel_data(cleaned_data)

        # Add key point markers
        plot_crosses(
            df=key_point_indicies,
            channel=channel_col,
            data=cleaned_data,
            ax=ax,
        )

        transducer_code = channel_info.get("transducer", "")
        breakout_torque = channel_info.get("breakout_torque", 0)
        running_torque = channel_info.get("running_torque", 0)

        # Calculate allowable drop (typically 10% of test pressure)
        test_pressure = float(self.test_metadata.get('Test Pressure', '0') or 0)
        allowable_drop = int(test_pressure * 0.1) if test_pressure else 0

        # Create PDF with test details
        pdf = draw_production_test_details(
            metadata,
            channel_info,
            unique_path,
            cleaned_data,
            transducer_code,
            allowable_drop,
            breakout_torque,
            running_torque
        )

        # Format display table for PDF
        display_table.loc[-1] = display_table.columns
        display_table.index = display_table.index + 1
        display_table = display_table.sort_index()
        display_table.columns = range(display_table.shape[1])

        # Add table and plot to PDF
        draw_table(pdf_canvas=pdf, dataframe=display_table)
        insert_plot_and_logo(figure, pdf, is_table, True)

        return self.finalize_output_path(unique_path)


class CalibrationReportGenerator(BaseReportGenerator):
    """Generate calibration reports."""

    def build_output_path(self, test_metadata, calibration_info) -> Path:
        """Construct the output PDF path for calibration."""
        # Calibration_Channel-{index}_{Date_Time}.pdf
        channel_index = calibration_info.get("channel_index", "Unknown")
        date_time = test_metadata.get("Date Time", "Unknown")

        # Ensure Date Time is formatted dd-mm-yyyy_hh-mm-ss as requested
        # metadata["Date Time"] should already be in this format or we format it here

        return self.pdf_output_path / f"Calibration_Channel-{channel_index}_{date_time}.tmp.pdf"

    def generate(self) -> List[Path]:
        """Generate the calibration report."""
        is_table = True
        calibration_info = self.info_obj

        unique_path = self.build_output_path(self.test_metadata, calibration_info)
        unique_path.parent.mkdir(parents=True, exist_ok=True)

        calibration_indices = locate_calibration_points(self.cleaned_data, calibration_info)
        (
            average_values,
            counts_series,
            expected_series,
            abs_errors,
        ) = calculate_succesful_calibration(
            self.cleaned_data,
            calibration_indices,
            calibration_info,
        )

        # Check for threshold breaches
        from pdf_helpers import evaluate_calibration_thresholds
        breach_mask = evaluate_calibration_thresholds(average_values)
        has_breach = not breach_mask.empty and breach_mask.to_numpy().any()

        regression_coefficients = None
        if has_breach:
            regression_coefficients = calculate_calibration_regression(
                counts_series,
                expected_series,
            )

        figure, ax = plot_calibration_data(self.cleaned_data, channel_index=calibration_info.get("channel_index"))

        # Add calibration markers to plot
        for phase in calibration_indices.columns:
            positions = calibration_indices[phase].dropna().astype(int).tolist()
            times = self.cleaned_data["Datetime"].iloc[positions]
            values = self.cleaned_data["Calibrated Channel"].iloc[positions]
            ax.scatter(
                times, values, marker='x', s=50, color='black'
            )

        pdf = draw_calibration_test_details(self.test_metadata, unique_path, channel_index=calibration_info.get("channel_index"))

        # Add main calibration table
        draw_table(pdf_canvas=pdf, dataframe=average_values)

        # Add regression table if there were breaches
        if regression_coefficients is not None and not regression_coefficients.dropna().empty:
            draw_regression_table(pdf, regression_coefficients)

        insert_plot_and_logo(figure, pdf, is_table, True)

        return [self.finalize_output_path(unique_path)]
