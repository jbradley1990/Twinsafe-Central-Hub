"""Production and Calibration chart report generator."""

from pathlib import Path
import argparse
import sys

from data_loading import (
    load_test_information,
    prepare_primary_data,
)
from program_handlers import ProductionReportGenerator, CalibrationReportGenerator


def generate_report(primary_data_file, test_details_file, pdf_output_path):
    """
    Processes data files to generate PDF reports.
    """
    print(f"Loading test information from {test_details_file}...")
    test_metadata, info_obj = load_test_information(test_details_file)

    print(f"Preparing primary data from {primary_data_file}...")

    cleaned_data, active_channels = prepare_primary_data(
        primary_data_file,
        info_obj,
    )

    print(f"Active channels: {active_channels}")

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
    print(f"Generating {program_name} report(s)...")
    generated = handler_instance.generate()
    print(f"Successfully generated {len(generated)} report(s).")



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
        print(f"Starting report generation for {args.primary_data_file}")
        generate_report(
            primary_data_file=args.primary_data_file,
            test_details_file=args.test_details_file,
            pdf_output_path=Path(args.pdf_output_path),
        )
        print("Done")
    except Exception as exc:
        import traceback
        print(f"Error: {exc}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
