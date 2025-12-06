import argparse
import json
import sys
from pathlib import Path
from .extractor import extract_from_directory
from .validator import validate_batch
from .utils import logger

def extract_command(args):
    """Extract purchase orders from PDFs"""
    logger.info(f"Extracting from {args.pdf_dir}...")
    
    if not Path(args.pdf_dir).exists():
        logger.error(f"Directory not found: {args.pdf_dir}")
        sys.exit(1)
    
    purchase_orders = extract_from_directory(args.pdf_dir)
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(purchase_orders, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Extracted {len(purchase_orders)} purchase orders to {args.output}")

def validate_command(args):
    """Validate extracted purchase orders"""
    logger.info(f"Validating {args.input}...")
    
    if not Path(args.input).exists():
        logger.error(f"File not found: {args.input}")
        sys.exit(1)
    
    with open(args.input, 'r', encoding='utf-8') as f:
        purchase_orders = json.load(f)
    
    results = validate_batch(purchase_orders)
    
    with open(args.report, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    # Print summary
    summary = results['summary']
    print("\n" + "="*60)
    print("PURCHASE ORDER VALIDATION SUMMARY")
    print("="*60)
    print(f"Total Purchase Orders: {summary['total_purchase_orders']}")
    print(f"Valid: {summary['valid']}")
    print(f"Invalid: {summary['invalid']}")
    
    if summary['error_counts']:
        print("\nTop Errors:")
        for error, count in sorted(summary['error_counts'].items(), key=lambda x: x[1], reverse=True)[:5]:
            print(f"  - {error}: {count}")
    
    print(f"\nFull report saved to: {args.report}")
    print("="*60 + "\n")
    
    # Exit with error code if there are invalid POs
    if summary['invalid'] > 0:
        sys.exit(1)

def full_run_command(args):
    """Extract and validate in one step"""
    logger.info("Running full extraction and validation...")
    
    # Extract
    temp_file = "temp_extracted.json"
    extract_args = argparse.Namespace(pdf_dir=args.pdf_dir, output=temp_file)
    extract_command(extract_args)
    
    # Validate
    validate_args = argparse.Namespace(input=temp_file, report=args.report)
    validate_command(validate_args)
    
    # Cleanup temp file
    Path(temp_file).unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser(
        description="German B2B Purchase Order QC System",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract purchase orders from PDFs')
    extract_parser.add_argument('--pdf-dir', required=True, help='Directory containing PDF files')
    extract_parser.add_argument('--output', required=True, help='Output JSON file')
    
    # Validate command
    validate_parser = subparsers.add_parser('validate', help='Validate extracted purchase orders')
    validate_parser.add_argument('--input', required=True, help='Input JSON file with extracted data')
    validate_parser.add_argument('--report', required=True, help='Output validation report JSON')
    
    # Full-run command
    fullrun_parser = subparsers.add_parser('full-run', help='Extract and validate in one step')
    fullrun_parser.add_argument('--pdf-dir', required=True, help='Directory containing PDF files')
    fullrun_parser.add_argument('--report', required=True, help='Output validation report JSON')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    if args.command == 'extract':
        extract_command(args)
    elif args.command == 'validate':
        validate_command(args)
    elif args.command == 'full-run':
        full_run_command(args)

if __name__ == '__main__':
    main()
