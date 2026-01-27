"""Production and Calibration chart report generator."""

from pathlib import Path
import argparse

from data_loading import (
    load_test_information,
    prepare_primary_data,
)
from program_handlers import ProductionReportGenerator, CalibrationReportGenerator


def generate_report(primary_data_file, test_details_file, pdf_output_path):
    """
    Processes data files to generate PDF reports.
    """
    test_metadata, info_obj = load_test_information(test_details_file)

    cleaned_data, active_channels = prepare_primary_data(
        primary_data_file,
        info_obj,
    )

    if isinstance(info_obj, dict) and "channel_index" in info_obj:
        handler_class = CalibrationReportGenerator
        program_name = "Calibration"
    else:
        handler_class = ProductionReportGenerator
        program_name = "Production"

    handler_instance = handler_class(
        program_name=program_name,
        pdf_output_path=pdf_output_path,
        test_metadata=test_metadata,
        active_channels=active_channels,
        cleaned_data=cleaned_data,
        info_obj=info_obj,
    )
    handler_instance.generate()



def main():
    """
    Main entry point for chart generation.
    Takes command-line arguments for a single report generation run.
    """
    parser = argparse.ArgumentParser(description="Generate PDF reports from CSV data.")
    parser.add_argument("primary_data_file", type=str, help="Path to the primary data CSV file")
    parser.add_argument("test_details_file", type=str, help="Path to the test details JSON file")
    parser.add_argument("pdf_output_path", type=str, help="Directory for PDF output")

    args = parser.parse_args()

    try:
        generate_report(
            primary_data_file=args.primary_data_file,
            test_details_file=args.test_details_file,
            pdf_output_path=Path(args.pdf_output_path),
        )
        print("Done")
    except Exception as exc:
        print(f"Error: {exc}")
        raise

if __name__ == "__main__":
    main()
