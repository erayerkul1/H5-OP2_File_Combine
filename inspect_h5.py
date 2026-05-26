#!/usr/bin/env python3.11
"""
H5 dosyasının tam iç yapısını (grup + dataset + attribute) yazdırır.
Kullanım:  python3.11 inspect_h5.py dosya.h5
"""
import sys, h5py, os

def inspect(path: str, max_items: int = 300):
    print(f"\n{'='*60}")
    print(f"Dosya : {os.path.basename(path)}")
    print(f"Boyut : {os.path.getsize(path)/1024/1024:.2f} MB")
    print(f"{'='*60}")
    count = [0]
    with h5py.File(path, "r") as f:
        # Kök attribute'lar
        if f.attrs:
            print(f"[KÖK] attrs: {dict(f.attrs)}")
        def _visit(name, obj):
            if count[0] >= max_items:
                return
            count[0] += 1
            depth = name.count("/")
            indent = "  " * depth
            short = name.split("/")[-1]
            if isinstance(obj, h5py.Dataset):
                attrs = {k: v for k, v in obj.attrs.items()}
                print(f"{indent}[D] {short}  shape={obj.shape}  dtype={obj.dtype}"
                      + (f"  attrs={attrs}" if attrs else ""))
            else:
                attrs = {k: v for k, v in obj.attrs.items()}
                print(f"{indent}[G] {short}/"
                      + (f"  attrs={attrs}" if attrs else ""))
        f.visititems(_visit)
    if count[0] >= max_items:
        print(f"\n... (ilk {max_items} öğe gösterildi)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Kullanım: python3.11 inspect_h5.py <dosya.h5>")
        sys.exit(1)
    for p in sys.argv[1:]:
        inspect(p)
