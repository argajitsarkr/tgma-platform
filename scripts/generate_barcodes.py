#!/usr/bin/env python3
"""Generate barcode label PDFs for field collection and lab inventory.

Generates Code128 barcodes for a list of tracking IDs or sample IDs,
suitable for printing on Brother P-touch or standard label sheets.

Usage:
    python scripts/generate_barcodes.py --ids TGMA-WT-F-0001 TGMA-WT-F-0002
    python scripts/generate_barcodes.py --range TGMA-WT-F 1 20
    python scripts/generate_barcodes.py --samples TGMA-WT-F-0001
    python scripts/generate_barcodes.py --from-db --district WT --output labels.pdf
"""

import os
import sys
import argparse

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import barcode
    from barcode.writer import ImageWriter
    from PIL import Image
except ImportError:
    print('Required packages: pip install python-barcode Pillow')
    sys.exit(1)

from app.utils.helpers import generate_tracking_id, SAMPLE_SUFFIXES


def generate_barcode_image(text, output_dir):
    """Generate a Code128 barcode PNG for the given text."""
    code = barcode.get('code128', text, writer=ImageWriter())
    filename = code.save(os.path.join(output_dir, text.replace('/', '_')),
                         options={'write_text': True, 'module_height': 10,
                                  'font_size': 8, 'text_distance': 2})
    return filename


def generate_sample_barcodes(tracking_id, output_dir):
    """Generate barcodes for all sample types of a participant."""
    files = []
    for sample_type, suffix in SAMPLE_SUFFIXES.items():
        sample_id = f'{tracking_id}-{suffix}'
        f = generate_barcode_image(sample_id, output_dir)
        files.append(f)
        print(f'  {sample_id} -> {f}')
    return files


def main():
    parser = argparse.ArgumentParser(description='Generate barcode labels for TGMA study')
    parser.add_argument('--ids', nargs='+', help='Specific tracking IDs to generate')
    parser.add_argument('--range', nargs=3, metavar=('PREFIX', 'START', 'END'),
                        help='Generate range: PREFIX START END (e.g., TGMA-WT-F 1 20)')
    parser.add_argument('--samples', nargs='+',
                        help='Generate sample barcodes for these tracking IDs')
    parser.add_argument('--output', default='barcodes', help='Output directory (default: barcodes/)')

    args = parser.parse_args()

    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    if args.ids:
        print(f'Generating {len(args.ids)} barcode(s)...')
        for tid in args.ids:
            f = generate_barcode_image(tid, output_dir)
            print(f'  {tid} -> {f}')

    elif args.range:
        prefix, start, end = args.range
        start, end = int(start), int(end)
        parts = prefix.split('-')
        if len(parts) >= 3:
            district = parts[1]
            gender = parts[2]
        else:
            district, gender = 'WT', 'M'

        print(f'Generating barcodes for {prefix}-{start:04d} to {prefix}-{end:04d}...')
        for seq in range(start, end + 1):
            tid = generate_tracking_id(district, gender, seq)
            f = generate_barcode_image(tid, output_dir)
            print(f'  {tid} -> {f}')

    elif args.samples:
        for tid in args.samples:
            print(f'Sample barcodes for {tid}:')
            generate_sample_barcodes(tid, output_dir)

    else:
        parser.print_help()
        sys.exit(1)

    print(f'\nBarcodes saved to: {output_dir}/')


if __name__ == '__main__':
    main()
