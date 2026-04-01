import logging
from pathlib import Path

from openpyxl import load_workbook
from pandas import DataFrame

from datafusion import get_resource_path

logger = logging.getLogger(__name__)

# Default konfigurator path

DEFAULT_KONFIGURATOR_PATH = get_resource_path("konfigurator.xlsx")


def save_to_konfigurator(
    df: DataFrame,
    output_path: Path | None = None,
    sheet_name: str = "i_agregaty",
) -> None:
    """
    Save DataFrame to konfigurator Excel file in specified sheet.

    Args:
        df: DataFrame to save.
        sheet_name: Name of the sheet to write to (default: "i_agregaty").
    """
    konfigurator_path = DEFAULT_KONFIGURATOR_PATH

    konfigurator_path = Path(konfigurator_path).expanduser().resolve()

    if not konfigurator_path.exists():
        logger.warning("Konfigurator file not found at %s, skipping save", konfigurator_path)
        return

    try:
        # Load workbook
        wb = load_workbook(konfigurator_path)

        # Get or create sheet
        if sheet_name in wb.sheetnames:
            # Remove old sheet and create new one
            wb.remove(wb[sheet_name])
        ws = wb.create_sheet(sheet_name)

        # Write DataFrame to sheet
        # Write headers
        for col_idx, col_name in enumerate(df.columns, start=1):
            ws.cell(row=1, column=col_idx, value=col_name)

        # Write data
        for row_idx, row in enumerate(df.itertuples(index=False), start=2):
            for col_idx, value in enumerate(row, start=1):
                ws.cell(row=row_idx, column=col_idx, value=value)

        output_file = output_path / "konfigurator.xlsx"
        wb.save(output_file)
        logger.info("Saved %d rows to %s sheet '%s'", len(df), output_file, sheet_name)

    except Exception as e:
        logger.error("Failed to save to konfigurator: %s", e)
        raise
