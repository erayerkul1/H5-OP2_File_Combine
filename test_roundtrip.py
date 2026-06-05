#!/usr/bin/env python3
"""
Orijinal OP2 dosyasını pyNastran ile okuyup tekrar yazar,
ardından geri okuyarak sonuç tiplerini karşılaştırır.
Sonuç: pyNastran'ın write_op2'sinin hangi tipleri koruyabildiğini gösterir.
"""
import sys, os
from pathlib import Path

def roundtrip(filepath: str):
    try:
        from pyNastran.op2.op2 import OP2
    except ImportError:
        print("HATA: pyNastran kurulu değil.")
        sys.exit(1)

    # 1) Oku
    print(f"\n[1] Okunuyor: {filepath}")
    op2 = OP2(debug=False)
    op2.read_op2(filepath)

    orig = {}
    for t in op2.get_table_types():
        try:
            d = op2.get_result(t)
        except Exception:
            continue
        if d and isinstance(d, dict):
            orig[t] = len(d)
    print(f"    {len(orig)} sonuç tipi bulundu:")
    for t, n in orig.items():
        print(f"      {t:45s}  {n} subcase")

    # 2) Geri yaz
    out = Path(filepath).with_suffix('.roundtrip.op2')
    print(f"\n[2] Yazılıyor: {out}")
    try:
        op2.write_op2(str(out), post=-1)
        print(f"    OK, boyut={os.path.getsize(out)/1024:.1f} KB")
    except Exception as e:
        print(f"    HATA: {e}")
        return

    # 3) Geri oku
    print(f"\n[3] Geri okunuyor: {out}")
    op2b = OP2(debug=False)
    try:
        op2b.read_op2(str(out))
    except Exception as e:
        print(f"    HATA: {e}")
    back = {}
    for t in op2b.get_table_types():
        try:
            d = op2b.get_result(t)
        except Exception:
            continue
        if d and isinstance(d, dict):
            back[t] = len(d)

    print(f"\n    Geri okunan tipler ({len(back)}/{len(orig)}):")
    for t in orig:
        status = "✓" if t in back else "✗ KAYIP"
        print(f"      {status}  {t}")
    os.remove(out)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Kullanım: python test_roundtrip.py dosya.op2")
        sys.exit(1)
    roundtrip(sys.argv[1])
