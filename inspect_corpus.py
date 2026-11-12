"""CLI utility to inspect documents/ and produce an inventory report."""

import os
from pathlib import Path
from ingestion.pdf_inspector import inspect_all_documents, generate_inventory_report


def main():
    print("Discovering and inspecting documents in documents/ ...")
    inspections = inspect_all_documents("documents")
    report = generate_inventory_report(inspections)
    
    print("\n" + report)
    
    # Save derived artifact to data/
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    report_path = data_dir / "inventory_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nInventory report saved to: {report_path}")


if __name__ == "__main__":
    main()
