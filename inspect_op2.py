#!/usr/bin/env python3
"""OP2 dosyasındaki tüm sonuç tiplerini ve subcase'leri listeler."""
import sys
from pathlib import Path

def inspect_op2(filepath: str):
    try:
        from pyNastran.op2.op2 import OP2
    except ImportError:
        print("HATA: pyNastran kurulu değil.")
        sys.exit(1)

    print(f"\nOkunuyor: {filepath}")
    op2 = OP2(debug=False)
    op2.read_op2(filepath)

    found_any = False
    for table_name in op2.get_table_types():
        try:
            result_dict = op2.get_result(table_name)
        except Exception:
            continue
        if not result_dict or not isinstance(result_dict, dict):
            continue
        found_any = True
        keys = list(result_dict.keys())
        print(f"  {table_name:45s}  {len(keys)} subcase  keys={keys}")

    if not found_any:
        print("  (hiç sonuç bulunamadı)")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Kullanım: python inspect_op2.py dosya.op2")
        sys.exit(1)
    inspect_op2(sys.argv[1])
