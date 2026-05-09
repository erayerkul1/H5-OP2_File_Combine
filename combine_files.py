#!/usr/bin/env python3.11
"""
OP2 / H5 File Combiner
Birden fazla .op2 veya .h5 dosyasını tek bir dosyada birleştirir.
"""

import sys
import os
import glob
from pathlib import Path


def get_file_type_choice() -> str:
    print("\n=== Dosya Birleştirme Aracı ===")
    print("Hangi dosya türünü birleştirmek istiyorsunuz?")
    print("  1) OP2 (.op2) - Nastran çıktı dosyaları")
    print("  2) H5  (.h5)  - HDF5 dosyaları")
    print()
    while True:
        choice = input("Seçiminiz (1 veya 2): ").strip()
        if choice == "1":
            return "op2"
        elif choice == "2":
            return "h5"
        else:
            print("Lütfen 1 veya 2 girin.")


def find_files(extension: str) -> list[str]:
    cwd = os.getcwd()
    pattern = os.path.join(cwd, f"*.{extension}")
    files = sorted(glob.glob(pattern))
    return files


def get_files_from_user(extension: str) -> list[str]:
    auto_files = find_files(extension)

    if auto_files:
        print(f"\nMevcut dizinde bulunan .{extension} dosyaları:")
        for i, f in enumerate(auto_files, 1):
            print(f"  {i}) {os.path.basename(f)}")
        print()
        use_auto = input("Bu dosyaların tamamını birleştirmek ister misiniz? (e/h): ").strip().lower()
        if use_auto in ("e", "evet", "y", "yes", ""):
            return auto_files

    print("\nBirleştirilecek dosya yollarını girin (her satıra bir tane, bitince boş satır bırakın):")
    files = []
    while True:
        line = input(f"  Dosya {len(files)+1}: ").strip()
        if not line:
            if len(files) >= 2:
                break
            elif len(files) == 0:
                print("En az 2 dosya girmelisiniz.")
            else:
                print("En az 2 dosya girmelisiniz.")
        else:
            if not os.path.isfile(line):
                print(f"  HATA: Dosya bulunamadı: {line}")
            else:
                files.append(line)
    return files


def get_output_path(extension: str) -> str:
    default_name = f"combined.{extension}"
    ans = input(f"\nÇıktı dosya adı [{default_name}]: ").strip()
    if not ans:
        ans = default_name
    if not ans.endswith(f".{extension}"):
        ans += f".{extension}"
    return os.path.join(os.getcwd(), ans)


# ──────────────────────────────────────────────
# OP2 Birleştirme
# ──────────────────────────────────────────────

def combine_op2(input_files: list[str], output_path: str) -> None:
    try:
        from pyNastran.op2.op2 import OP2
    except ImportError:
        print("HATA: pyNastran kurulu değil. Kurmak için: pip install pyNastran")
        sys.exit(1)

    print(f"\n{len(input_files)} adet OP2 dosyası okunuyor...")

    combined = OP2(debug=False)
    combined.read_mode = 1

    subcase_offset = 0
    all_table_types = combined.get_table_types()

    for file_idx, filepath in enumerate(input_files):
        print(f"  [{file_idx+1}/{len(input_files)}] Okunuyor: {os.path.basename(filepath)}")
        op2 = OP2(debug=False)
        op2.read_op2(filepath)

        # Bu dosyadaki maksimum subcase ID'yi bul
        file_max_subcase = 0
        for table_name in all_table_types:
            result_dict = _get_nested_attr(op2, table_name)
            if result_dict and isinstance(result_dict, dict):
                for key in result_dict:
                    sc_id = key[0] if isinstance(key, tuple) else key
                    if isinstance(sc_id, int):
                        file_max_subcase = max(file_max_subcase, sc_id)

        # Sonuçları combined nesnesine kopyala (subcase offset uygula)
        merged_count = 0
        for table_name in all_table_types:
            result_dict = _get_nested_attr(op2, table_name)
            if not result_dict or not isinstance(result_dict, dict):
                continue

            combined_dict = _get_nested_attr(combined, table_name)
            if combined_dict is None:
                combined_dict = {}
                _set_nested_attr(combined, table_name, combined_dict)

            for key, result_obj in result_dict.items():
                if isinstance(key, tuple):
                    new_key = (key[0] + subcase_offset,) + key[1:]
                else:
                    new_key = key + subcase_offset

                combined_dict[new_key] = result_obj
                merged_count += 1

        print(f"    → {merged_count} sonuç tablosu eklendi (subcase offset: {subcase_offset})")
        subcase_offset += file_max_subcase if file_max_subcase > 0 else 1

    print(f"\nBirleştirilmiş dosya yazılıyor: {output_path}")
    combined.write_op2(output_path, post=-1)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"Tamamlandı. Dosya boyutu: {size_mb:.2f} MB")


def _get_nested_attr(obj, dotted_name: str):
    """'a.b.c' → obj.a.b.c"""
    parts = dotted_name.split(".")
    current = obj
    for part in parts:
        current = getattr(current, part, None)
        if current is None:
            return None
    return current


def _set_nested_attr(obj, dotted_name: str, value) -> None:
    """'a.b.c' → obj.a.b.c = value"""
    parts = dotted_name.split(".")
    current = obj
    for part in parts[:-1]:
        current = getattr(current, part, None)
        if current is None:
            return
    setattr(current, parts[-1], value)


# ──────────────────────────────────────────────
# H5 Birleştirme
# ──────────────────────────────────────────────

def combine_h5(input_files: list[str], output_path: str) -> None:
    try:
        import h5py
        import numpy as np
    except ImportError:
        print("HATA: h5py kurulu değil. Kurmak için: pip install h5py")
        sys.exit(1)

    print(f"\n{len(input_files)} adet H5 dosyası birleştiriliyor...")

    conflict_mode = _ask_conflict_mode()

    with h5py.File(output_path, "w") as out_file:
        for file_idx, filepath in enumerate(input_files):
            file_label = Path(filepath).stem
            print(f"  [{file_idx+1}/{len(input_files)}] İşleniyor: {os.path.basename(filepath)}")

            with h5py.File(filepath, "r") as in_file:
                item_count = [0]

                def _copy_item(name, obj):
                    if conflict_mode == "prefix":
                        dest_name = f"{file_label}/{name}"
                    else:
                        dest_name = name

                    if isinstance(obj, h5py.Dataset):
                        if dest_name in out_file:
                            if conflict_mode == "skip":
                                return
                            elif conflict_mode == "overwrite":
                                del out_file[dest_name]
                            elif conflict_mode == "rename":
                                dest_name = f"{dest_name}_file{file_idx+1}"

                        # Grubun üst yolunu oluştur
                        parent = "/".join(dest_name.split("/")[:-1])
                        if parent and parent not in out_file:
                            out_file.require_group(parent)

                        in_file.copy(name, out_file, name=dest_name)
                        item_count[0] += 1

                    elif isinstance(obj, h5py.Group):
                        if conflict_mode != "prefix":
                            out_file.require_group(dest_name)
                            # Grup attribute'larını kopyala
                            src_grp = in_file[name]
                            dst_grp = out_file[dest_name]
                            for attr_k, attr_v in src_grp.attrs.items():
                                if attr_k not in dst_grp.attrs:
                                    dst_grp.attrs[attr_k] = attr_v

                in_file.visititems(_copy_item)
                # Kök attribute'larını kopyala
                for attr_k, attr_v in in_file.attrs.items():
                    if attr_k not in out_file.attrs:
                        out_file.attrs[attr_k] = attr_v

                print(f"    → {item_count[0]} dataset eklendi")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\nTamamlandı: {output_path} ({size_mb:.2f} MB)")


def _ask_conflict_mode() -> str:
    print("\nAynı isimde dataset'ler çakışırsa ne yapılsın?")
    print("  1) prefix  - Her dosyanın içeriğini kendi adıyla bir grup altına koy (önerilen)")
    print("  2) skip    - Var olanı koru, yeni geleni atla")
    print("  3) overwrite - Yeni gelen eskinin üzerine yaz")
    print("  4) rename  - Yeni gelene _fileN eki ekle")
    while True:
        choice = input("Seçiminiz (1-4) [1]: ").strip()
        if choice in ("", "1"):
            return "prefix"
        elif choice == "2":
            return "skip"
        elif choice == "3":
            return "overwrite"
        elif choice == "4":
            return "rename"
        else:
            print("Lütfen 1-4 arasında bir değer girin.")


# ──────────────────────────────────────────────
# Ana akış
# ──────────────────────────────────────────────

def main() -> None:
    file_type = get_file_type_choice()
    input_files = get_files_from_user(file_type)

    if len(input_files) < 2:
        print("HATA: Birleştirmek için en az 2 dosya gerekli.")
        sys.exit(1)

    print(f"\nBirleştirilecek dosyalar ({len(input_files)} adet):")
    for f in input_files:
        size_kb = os.path.getsize(f) / 1024
        print(f"  • {os.path.basename(f)}  ({size_kb:.1f} KB)")

    output_path = get_output_path(file_type)

    if os.path.exists(output_path):
        ans = input(f"\nUyarı: {os.path.basename(output_path)} zaten var. Üzerine yazılsın mı? (e/h): ").strip().lower()
        if ans not in ("e", "evet", "y", "yes"):
            print("İşlem iptal edildi.")
            sys.exit(0)

    if file_type == "op2":
        combine_op2(input_files, output_path)
    else:
        combine_h5(input_files, output_path)


if __name__ == "__main__":
    main()
