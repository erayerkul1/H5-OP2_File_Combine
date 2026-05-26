#!/usr/bin/env python3.11
"""
OP2 / H5 File Combiner
Birden fazla .op2 veya .h5 dosyasını tek bir dosyada birleştirir.
"""

import sys
import os
import glob
import io
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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

    combined: OP2 | None = None
    subcase_offset = 0

    for file_idx, filepath in enumerate(input_files):
        print(f"  [{file_idx+1}/{len(input_files)}] Okunuyor: {os.path.basename(filepath)}")
        op2 = OP2(debug=False)
        op2.read_op2(filepath)

        all_table_types = op2.get_table_types()

        # Bu dosyadaki maksimum subcase ID'yi bul
        file_max_subcase = 0
        for table_name in all_table_types:
            result_dict = _get_nested_attr(op2, table_name)
            if result_dict and isinstance(result_dict, dict):
                for key in result_dict:
                    sc_id = key[0] if isinstance(key, tuple) else key
                    if isinstance(sc_id, int):
                        file_max_subcase = max(file_max_subcase, sc_id)

        if combined is None:
            # İlk dosyayı temel al — başlık/metadata bu objede korunur
            combined = op2
            print(f"    → temel dosya olarak alındı (max subcase: {file_max_subcase})")
            subcase_offset = file_max_subcase if file_max_subcase > 0 else 1
            continue

        # Sonraki dosyaların sonuçlarını combined'a ekle (offset + isubcase güncelle)
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
                    new_sc = key[0] + subcase_offset
                    new_key = (new_sc,) + key[1:]
                else:
                    new_sc = key + subcase_offset
                    new_key = new_sc

                # pyNastran yazarken result_obj.isubcase değerini kullanır;
                # dictionary key'i ile senkron olmazsa subcase çakışması yaşanır.
                try:
                    result_obj.isubcase = new_sc
                except AttributeError:
                    pass  # salt okunur ya da yoksa geç

                combined_dict[new_key] = result_obj
                merged_count += 1

        print(f"    → {merged_count} sonuç tablosu eklendi (subcase offset: {subcase_offset})")
        subcase_offset += file_max_subcase if file_max_subcase > 0 else 1

    if combined is None:
        print("HATA: Hiç dosya okunamadı.")
        return

    print(f"\nBirleştirilmiş dosya yazılıyor: {output_path}")
    combined.write_op2(output_path, post=-1)
    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"✓ Tamamlandı! Dosya boyutu: {size_mb:.2f} MB")


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

def _h5_deep_merge(src_file, dst_file, src_grp_path: str, dst_grp_path: str,
                   file_idx: int, counters: list) -> None:
    """
    src_file içindeki src_grp_path grubunu dst_file'ın dst_grp_path grubuna
    özyinelemeli olarak birleştirir.

    Strateji:
    - Grup yoksa  → tümüyle kopyala (içindeki her şeyle)
    - Grup varsa  → attribute ekle, içine in ve aynı işlemi tekrarla
                    ANCAK iç item'lar dataset ise (yaprak grup = sonuç grubu)
                    grubu bütünüyle _fN adıyla kopyala (HyperView uyumluluğu)
    - Dataset yoksa → kopyala
    - Dataset varsa → _fN sonekiyle yeniden adlandır
    """
    import h5py

    src_grp = src_file[src_grp_path] if src_grp_path != "/" else src_file

    for name, item in src_grp.items():
        src_child = f"{src_grp_path.rstrip('/')}/{name}".lstrip("/")
        dst_child = f"{dst_grp_path.rstrip('/')}/{name}".lstrip("/")

        if isinstance(item, h5py.Group):
            if dst_child not in dst_file:
                # Hedefte hiç yok → tümünü tek seferde kopyala
                src_file.copy(src_child, dst_file, name=dst_child)
                counters[0] += _count_datasets(item)
            else:
                # Hedefte var → bu grubun "yaprak grup" (leaf group) olup
                # olmadığını kontrol et: içindeki tüm çocuklar dataset ise
                # grubu bütünüyle _fN adıyla kopyala; değilse içine gir.
                all_children_are_datasets = all(
                    isinstance(item[child], h5py.Dataset) for child in item
                )
                if all_children_are_datasets:
                    # Yaprak grup (örn. SUBCASE_1) → grubu bütünüyle rename et
                    suffix = 2
                    candidate = f"{dst_child}_f{file_idx + 1}"
                    while candidate in dst_file:
                        candidate = f"{dst_child}_f{file_idx + 1}_{suffix}"
                        suffix += 1
                    src_file.copy(src_child, dst_file, name=candidate)
                    counters[0] += _count_datasets(item)
                else:
                    # Ara grup → attribute'ları ekle ve içine in
                    for k, v in item.attrs.items():
                        if k not in dst_file[dst_child].attrs:
                            try:
                                dst_file[dst_child].attrs[k] = v
                            except Exception:
                                pass
                    _h5_deep_merge(src_file, dst_file, src_child, dst_child,
                                   file_idx, counters)

        elif isinstance(item, h5py.Dataset):
            if dst_child not in dst_file:
                src_file.copy(src_child, dst_file, name=dst_child)
                counters[0] += 1
            else:
                # Çakışan dataset → _fN sonekiyle yeniden adlandır
                suffix = 2
                candidate = f"{dst_child}_f{file_idx + 1}"
                while candidate in dst_file:
                    candidate = f"{dst_child}_f{file_idx + 1}_{suffix}"
                    suffix += 1
                src_file.copy(src_child, dst_file, name=candidate)
                counters[0] += 1


def _count_datasets(grp) -> int:
    """Bir grup içindeki toplam dataset sayısını döner."""
    import h5py
    count = [0]
    def _visit(name, obj):
        if isinstance(obj, h5py.Dataset):
            count[0] += 1
    grp.visititems(_visit)
    return count[0]


def combine_h5(input_files: list[str], output_path: str, conflict_mode: str | None = None) -> None:
    try:
        import h5py
    except ImportError:
        print("HATA: h5py kurulu değil. Kurmak için: pip install h5py")
        sys.exit(1)

    print(f"\n{len(input_files)} adet H5 dosyası birleştiriliyor...")

    if conflict_mode is None:
        conflict_mode = _ask_conflict_mode()

    with h5py.File(output_path, "w") as out_file:
        for file_idx, filepath in enumerate(input_files):
            print(f"  [{file_idx+1}/{len(input_files)}] İşleniyor: {os.path.basename(filepath)}")

            with h5py.File(filepath, "r") as in_file:
                # Kök attribute'larını kopyala (ilk dosyadan)
                for k, v in in_file.attrs.items():
                    if k not in out_file.attrs:
                        try:
                            out_file.attrs[k] = v
                        except Exception:
                            pass

                counters = [0]

                if conflict_mode == "deep_merge":
                    # Kök yapıyı koruyarak özyinelemeli birleştir
                    _h5_deep_merge(in_file, out_file, "/", "/", file_idx, counters)

                elif conflict_mode == "prefix":
                    # Her dosyanın içeriğini kendi adıyla bir üst grup altına koy
                    file_label = Path(filepath).stem
                    in_file.copy("/", out_file, name=file_label)
                    counters[0] = _count_datasets(in_file)

                else:
                    # skip / overwrite / rename — düz kopyalama (çakışma yönetimi ile)
                    def _flat_copy(name, obj):
                        if isinstance(obj, h5py.Dataset):
                            dest = name
                            if dest in out_file:
                                if conflict_mode == "skip":
                                    return
                                elif conflict_mode == "overwrite":
                                    del out_file[dest]
                                elif conflict_mode == "rename":
                                    dest = f"{name}_f{file_idx+1}"
                            parent = "/".join(dest.split("/")[:-1])
                            if parent and parent not in out_file:
                                out_file.require_group(parent)
                            in_file.copy(name, out_file, name=dest)
                            counters[0] += 1
                        elif isinstance(obj, h5py.Group):
                            dest = name
                            if dest not in out_file:
                                out_file.require_group(dest)
                            src_g = in_file[name]
                            dst_g = out_file[dest]
                            for k, v in src_g.attrs.items():
                                if k not in dst_g.attrs:
                                    try:
                                        dst_g.attrs[k] = v
                                    except Exception:
                                        pass
                    in_file.visititems(_flat_copy)

                print(f"    → {counters[0]} dataset eklendi")

    size_mb = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n✓ Tamamlandı: {output_path} ({size_mb:.2f} MB)")


def _ask_conflict_mode() -> str:
    print("\nBirleştirme modu seçin:")
    print("  1) deep_merge - Kök yapıyı koru, grupları içten birleştir (HyperView için önerilen)")
    print("  2) prefix     - Her dosyayı kendi adıyla ayrı bir üst grup altına koy")
    print("  3) skip       - Var olanı koru, çakışanı atla")
    print("  4) overwrite  - Çakışanda yeni gelen eskinin üzerine yaz")
    print("  5) rename     - Çakışana _fN soneki ekle")
    while True:
        choice = input("Seçiminiz (1-5) [1]: ").strip()
        mapping = {"": "deep_merge", "1": "deep_merge", "2": "prefix",
                   "3": "skip", "4": "overwrite", "5": "rename"}
        if choice in mapping:
            return mapping[choice]
        print("Lütfen 1-5 arasında bir değer girin.")


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


# ──────────────────────────────────────────────
# Tkinter GUI
# ──────────────────────────────────────────────

class _PrintRedirector(io.StringIO):
    """sys.stdout'u tkinter Text widget'ına yönlendirir."""
    def __init__(self, callback):
        super().__init__()
        self._cb = callback

    def write(self, text: str) -> int:
        if text:
            self._cb(text)
        return len(text)

    def flush(self):
        pass


class LoadExtractionApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("OP2 / H5 Dosya Birleştirici")
        self.root.resizable(True, True)
        self.file_type = tk.StringVar(value="op2")
        self.conflict_mode = tk.StringVar(value="deep_merge")
        self._build_ui()

    # ── UI ──────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 8, "pady": 4}

        # Dosya türü
        type_frame = ttk.LabelFrame(self.root, text="Dosya Türü")
        type_frame.pack(fill="x", **pad)
        for label, val in [("OP2 (.op2) — Nastran", "op2"), ("H5 (.h5) — HDF5", "h5")]:
            ttk.Radiobutton(
                type_frame, text=label, variable=self.file_type,
                value=val, command=self._on_type_change
            ).pack(side="left", padx=12, pady=4)

        # Dosya listesi
        list_frame = ttk.LabelFrame(self.root, text="Birleştirilecek Dosyalar")
        list_frame.pack(fill="both", expand=True, **pad)

        btn_bar = ttk.Frame(list_frame)
        btn_bar.pack(fill="x", padx=4, pady=2)
        ttk.Button(btn_bar, text="Ekle...", command=self._add_files).pack(side="left", padx=2)
        ttk.Button(btn_bar, text="Kaldır", command=self._remove_selected).pack(side="left", padx=2)

        sb = ttk.Scrollbar(list_frame, orient="vertical")
        self.listbox = tk.Listbox(list_frame, selectmode="extended", yscrollcommand=sb.set, height=6)
        sb.config(command=self.listbox.yview)
        sb.pack(side="right", fill="y", padx=(0, 4))
        self.listbox.pack(fill="both", expand=True, padx=(4, 0), pady=4)

        # Çıktı
        out_frame = ttk.LabelFrame(self.root, text="Çıktı Dosyası")
        out_frame.pack(fill="x", **pad)
        self.out_var = tk.StringVar()
        ttk.Entry(out_frame, textvariable=self.out_var).pack(side="left", fill="x", expand=True, padx=4, pady=4)
        ttk.Button(out_frame, text="Gözat...", command=self._browse_output).pack(side="right", padx=4, pady=4)

        # H5 birleştirme modu (başlangıçta gizli)
        self.conflict_frame = ttk.LabelFrame(self.root, text="H5 Birleştirme Modu")
        for label, val in [
            ("deep_merge — HyperView uyumlu (önerilen)", "deep_merge"),
            ("prefix — ayrı üst grup", "prefix"),
            ("skip", "skip"),
            ("overwrite", "overwrite"),
            ("rename", "rename"),
        ]:
            ttk.Radiobutton(
                self.conflict_frame, text=label,
                variable=self.conflict_mode, value=val
            ).pack(anchor="w", padx=8, pady=2)

        # Birleştir butonu
        self.run_btn = ttk.Button(self.root, text="Birleştir", command=self._start)
        self.run_btn.pack(pady=6)

        # Log alanı
        log_frame = ttk.LabelFrame(self.root, text="İlerleme")
        log_frame.pack(fill="both", expand=True, **pad)
        log_sb = ttk.Scrollbar(log_frame)
        self.log_text = tk.Text(log_frame, height=10, state="disabled",
                                yscrollcommand=log_sb.set, wrap="word")
        log_sb.config(command=self.log_text.yview)
        log_sb.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        self.root.minsize(520, 480)

    # ── Olaylar ─────────────────────────────────

    def _on_type_change(self):
        if self.file_type.get() == "h5":
            self.conflict_frame.pack(fill="x", padx=8, pady=4,
                                     before=self.run_btn)
        else:
            self.conflict_frame.pack_forget()

    def _add_files(self):
        ext = self.file_type.get()
        paths = filedialog.askopenfilenames(
            title="Dosya Seç",
            filetypes=[(f"{ext.upper()} Dosyaları", f"*.{ext}"), ("Tüm Dosyalar", "*.*")]
        )
        existing = list(self.listbox.get(0, "end"))
        for p in paths:
            if p not in existing:
                self.listbox.insert("end", p)

    def _remove_selected(self):
        for idx in reversed(self.listbox.curselection()):
            self.listbox.delete(idx)

    def _browse_output(self):
        ext = self.file_type.get()
        path = filedialog.asksaveasfilename(
            title="Çıktı Dosyası",
            defaultextension=f".{ext}",
            filetypes=[(f"{ext.upper()} Dosyaları", f"*.{ext}")]
        )
        if path:
            self.out_var.set(path)

    # ── Çalıştırma ──────────────────────────────

    def _start(self):
        files = list(self.listbox.get(0, "end"))
        output = self.out_var.get().strip()

        if len(files) < 2:
            messagebox.showwarning("Uyarı", "En az 2 dosya eklemelisiniz.")
            return
        if not output:
            messagebox.showwarning("Uyarı", "Çıktı dosyası belirtilmedi.")
            return
        if os.path.exists(output):
            if not messagebox.askyesno("Üzerine Yaz?",
                                       f"{os.path.basename(output)} zaten var.\nÜzerine yazılsın mı?"):
                return

        self.run_btn.config(state="disabled")
        self._clear_log()
        threading.Thread(target=self._run, args=(files, output), daemon=True).start()

    def _run(self, files: list[str], output: str):
        old_stdout = sys.stdout
        sys.stdout = _PrintRedirector(self._log)
        try:
            if self.file_type.get() == "op2":
                combine_op2(files, output)
            else:
                combine_h5(files, output, conflict_mode=self.conflict_mode.get())
        except Exception as exc:
            self._log(f"\nHATA: {exc}\n")
        finally:
            sys.stdout = old_stdout
            self.root.after(0, lambda: self.run_btn.config(state="normal"))

    # ── Log yardımcıları ────────────────────────

    def _log(self, msg: str):
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg)
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")


if __name__ == '__main__':
    root = tk.Tk()
    app = LoadExtractionApp(root)
    root.mainloop()
