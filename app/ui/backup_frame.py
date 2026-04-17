import customtkinter as ctk
from tkinter import messagebox, filedialog
import threading
import os
from tkinter import simpledialog
from pathlib import Path
import json
from app.services.backup_service import backup_service, BackupConfig

class BackupFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Title
        self.grid_rowconfigure(1, weight=0) # Settings
        self.grid_rowconfigure(2, weight=0) # History Label
        self.grid_rowconfigure(3, weight=1) # History List

        # Title
        self.title_label = ctk.CTkLabel(self, text="Backup & Restore", font=ctk.CTkFont(size=24, weight="bold"))
        self.title_label.grid(row=0, column=0, padx=20, pady=20, sticky="w")

        # --- Settings Section ---
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="ew")
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)

        # Enabled Toggle
        self.enabled_var = ctk.BooleanVar(value=backup_service.config.enabled)
        self.enabled_switch = ctk.CTkSwitch(self.settings_frame, text="Enable Scheduled Backups", variable=self.enabled_var, command=self.save_settings)
        self.enabled_switch.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        # Interval
        ctk.CTkLabel(self.settings_frame, text="Interval:").grid(row=0, column=1, padx=10, sticky="e")
        self.interval_combo = ctk.CTkOptionMenu(self.settings_frame, values=["hourly", "daily", "weekly", "monthly"], command=self.save_settings)
        self.interval_combo.set(backup_service.config.interval)
        self.interval_combo.grid(row=0, column=2, padx=10, sticky="w")

        # Time
        ctk.CTkLabel(self.settings_frame, text="Time (HH:MM):").grid(row=0, column=3, padx=10, sticky="e")
        self.time_entry = ctk.CTkEntry(self.settings_frame, width=80)
        self.time_entry.insert(0, backup_service.config.time_str)
        self.time_entry.grid(row=0, column=4, padx=10, sticky="w")
        self.time_entry.bind("<FocusOut>", self.save_settings)

        # Backup Mode
        ctk.CTkLabel(self.settings_frame, text="Backup Type:").grid(row=1, column=0, padx=20, pady=10, sticky="w")
        self.backup_mode_combo = ctk.CTkOptionMenu(self.settings_frame, values=["full", "incremental", "differential"], command=self.save_settings)
        self.backup_mode_combo.set(getattr(backup_service.config, "backup_mode", "full") or "full")
        self.backup_mode_combo.grid(row=1, column=1, padx=10, sticky="w")

        # Retention
        ctk.CTkLabel(self.settings_frame, text="Retention (Days):").grid(row=1, column=2, padx=10, pady=10, sticky="e")
        self.retention_entry = ctk.CTkEntry(self.settings_frame, width=60)
        self.retention_entry.insert(0, str(backup_service.config.retention_days))
        self.retention_entry.grid(row=1, column=3, padx=10, sticky="w")
        self.retention_entry.bind("<FocusOut>", self.save_settings)

        # Encryption
        self.encrypt_var = ctk.BooleanVar(value=backup_service.config.encrypt)
        self.encrypt_switch = ctk.CTkSwitch(self.settings_frame, text="Encrypt Backups", variable=self.encrypt_var, command=self.save_settings)
        self.encrypt_switch.grid(row=1, column=4, padx=10, sticky="w")

        # Key Rotation
        ctk.CTkLabel(self.settings_frame, text="Key Rotation (Days):").grid(row=2, column=0, padx=20, pady=10, sticky="w")
        self.key_rotation_entry = ctk.CTkEntry(self.settings_frame, width=60)
        self.key_rotation_entry.insert(0, str(int(getattr(backup_service.config, "key_rotation_days", 90) or 90)))
        self.key_rotation_entry.grid(row=2, column=1, padx=10, sticky="w")
        self.key_rotation_entry.bind("<FocusOut>", self.save_settings)

        self.key_status_label = ctk.CTkLabel(self.settings_frame, text="", text_color="gray")
        self.key_status_label.grid(row=2, column=2, columnspan=2, padx=10, sticky="w")

        self.rotate_key_btn = ctk.CTkButton(self.settings_frame, text="Rotate Key Now", width=140, command=self.rotate_key_now)
        self.rotate_key_btn.grid(row=2, column=4, padx=10, sticky="w")

        # Tiered Retention
        self.tiered_retention_var = ctk.BooleanVar(value=bool(getattr(backup_service.config, "retention_policy_enabled", False)))
        self.tiered_retention_switch = ctk.CTkSwitch(self.settings_frame, text="Use Tiered Retention", variable=self.tiered_retention_var, command=self.save_settings)
        self.tiered_retention_switch.grid(row=3, column=0, padx=20, pady=10, sticky="w")

        self.tiered_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.tiered_frame.grid(row=3, column=1, columnspan=4, padx=10, pady=10, sticky="ew")
        for i in range(10):
            self.tiered_frame.grid_columnconfigure(i, weight=0)

        policy = getattr(backup_service.config, "retention_policy", None) or {}
        self.keep_hourly = ctk.CTkEntry(self.tiered_frame, width=45)
        self.keep_daily = ctk.CTkEntry(self.tiered_frame, width=45)
        self.keep_weekly = ctk.CTkEntry(self.tiered_frame, width=45)
        self.keep_monthly = ctk.CTkEntry(self.tiered_frame, width=45)
        self.keep_yearly = ctk.CTkEntry(self.tiered_frame, width=45)

        def set_keep(entry, value):
            entry.delete(0, "end")
            entry.insert(0, str(int(value or 0)))
            entry.bind("<FocusOut>", self.save_settings)

        ctk.CTkLabel(self.tiered_frame, text="Hourly:").grid(row=0, column=0, padx=5, sticky="e")
        self.keep_hourly.grid(row=0, column=1, padx=5, sticky="w")
        ctk.CTkLabel(self.tiered_frame, text="Daily:").grid(row=0, column=2, padx=5, sticky="e")
        self.keep_daily.grid(row=0, column=3, padx=5, sticky="w")
        ctk.CTkLabel(self.tiered_frame, text="Weekly:").grid(row=0, column=4, padx=5, sticky="e")
        self.keep_weekly.grid(row=0, column=5, padx=5, sticky="w")
        ctk.CTkLabel(self.tiered_frame, text="Monthly:").grid(row=0, column=6, padx=5, sticky="e")
        self.keep_monthly.grid(row=0, column=7, padx=5, sticky="w")
        ctk.CTkLabel(self.tiered_frame, text="Yearly:").grid(row=0, column=8, padx=5, sticky="e")
        self.keep_yearly.grid(row=0, column=9, padx=5, sticky="w")

        set_keep(self.keep_hourly, (policy.get("hourly") or {}).get("keep", 24))
        set_keep(self.keep_daily, (policy.get("daily") or {}).get("keep", 30))
        set_keep(self.keep_weekly, (policy.get("weekly") or {}).get("keep", 12))
        set_keep(self.keep_monthly, (policy.get("monthly") or {}).get("keep", 24))
        set_keep(self.keep_yearly, (policy.get("yearly") or {}).get("keep", 7))

        # Paths
        ctk.CTkLabel(self.settings_frame, text="Local Path:").grid(row=4, column=0, padx=20, pady=5, sticky="w")
        self.local_path_entry = ctk.CTkEntry(self.settings_frame)
        self.local_path_entry.insert(0, backup_service.config.local_path)
        self.local_path_entry.grid(row=4, column=1, padx=10, sticky="ew", columnspan=3)
        ctk.CTkButton(self.settings_frame, text="Browse", width=80, command=self.browse_local).grid(row=4, column=4, padx=10)

        ctk.CTkLabel(self.settings_frame, text="Cloud/Sync Path:").grid(row=5, column=0, padx=20, pady=5, sticky="w")
        self.cloud_path_entry = ctk.CTkEntry(self.settings_frame)
        self.cloud_path_entry.insert(0, backup_service.config.cloud_path)
        self.cloud_path_entry.grid(row=5, column=1, padx=10, sticky="ew", columnspan=3)
        ctk.CTkButton(self.settings_frame, text="Browse", width=80, command=self.browse_cloud).grid(row=5, column=4, padx=10)

        # Destinations
        ctk.CTkLabel(self.settings_frame, text="Destinations:").grid(row=6, column=0, padx=20, pady=10, sticky="w")
        self.destinations_frame = ctk.CTkScrollableFrame(self.settings_frame, height=120)
        self.destinations_frame.grid(row=6, column=1, columnspan=3, padx=10, pady=10, sticky="ew")
        self.destinations_frame.grid_columnconfigure(1, weight=1)
        self.dest_rows = []

        add_dest_btn = ctk.CTkButton(self.settings_frame, text="+ Add", width=80, command=self.add_destination)
        add_dest_btn.grid(row=6, column=4, padx=10, pady=10, sticky="w")

        self._load_destinations_ui()

        # Actions
        self.action_frame = ctk.CTkFrame(self.settings_frame, fg_color="transparent")
        self.action_frame.grid(row=7, column=0, columnspan=5, pady=20)

        self.backup_btn = ctk.CTkButton(self.action_frame, text="Backup Now", width=150, height=35,
                                      command=self.create_manual_backup, fg_color="green", hover_color="darkgreen",
                                      font=ctk.CTkFont(size=14, weight="bold"))
        self.backup_btn.pack(side="left", padx=10)

        self.verify_btn = ctk.CTkButton(self.action_frame, text="Verify & Heal", width=150, height=35,
                                      command=self.verify_and_heal, fg_color="#7f8c8d", hover_color="#5a6268",
                                      font=ctk.CTkFont(size=14, weight="bold"))
        self.verify_btn.pack(side="left", padx=10)

        self.manual_format_combo = ctk.CTkOptionMenu(self.action_frame, values=["Encrypted (.enc)", "Unencrypted (.zip)"])
        self.manual_format_combo.set("Encrypted (.enc)" if backup_service.config.encrypt else "Unencrypted (.zip)")
        self.manual_format_combo.pack(side="left", padx=10)

        self.integrity_btn = ctk.CTkButton(self.action_frame, text="DB Integrity Check", width=170, height=35,
                                      command=self.run_integrity_check, fg_color="#9b59b6", hover_color="#8e44ad",
                                      font=ctk.CTkFont(size=14, weight="bold"))
        self.integrity_btn.pack(side="left", padx=10)

        self.import_btn = ctk.CTkButton(self.action_frame, text="Import Backup", width=150, height=35,
                                      command=self.import_backup, fg_color="#3498DB", hover_color="#2980B9",
                                      font=ctk.CTkFont(size=14, weight="bold"))
        self.import_btn.pack(side="left", padx=10)

        ctk.CTkLabel(self.action_frame, text="Auto-saves on change", text_color="gray").pack(side="left", padx=10)

        self.status_label = ctk.CTkLabel(self.action_frame, text="", text_color="gray")
        self.status_label.pack(side="right", padx=10)

        # --- History Section ---
        self.history_label = ctk.CTkLabel(self, text="Backup History", font=ctk.CTkFont(size=18, weight="bold"))
        self.history_label.grid(row=2, column=0, padx=20, pady=(20, 5), sticky="w")

        self.history_frame = ctk.CTkScrollableFrame(self)
        self.history_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.history_frame.grid_columnconfigure(0, weight=1)

        self.refresh_history()
        self._refresh_key_status()

    def _refresh_key_status(self):
        try:
            st = backup_service.get_encryption_status()
            if not st.get("encrypt"):
                self.key_status_label.configure(text="Encryption disabled", text_color="gray")
                return
            key_id = st.get("active_key_id") or "-"
            created = st.get("active_key_created_at") or ""
            self.key_status_label.configure(text=f"Active Key: {key_id} {created}".strip(), text_color="gray")
        except Exception:
            self.key_status_label.configure(text="", text_color="gray")

    def rotate_key_now(self):
        if not messagebox.askyesno("Rotate Encryption Key", "Rotate encryption key now? Existing backups will remain decryptable."):
            return
        res = backup_service.rotate_encryption_key_now()
        if res.get("success"):
            self._refresh_key_status()
            messagebox.showinfo("Key Rotation", res.get("message", "Key rotated."), parent=self.winfo_toplevel())
        else:
            messagebox.showerror("Key Rotation Failed", res.get("message", "Failed."), parent=self.winfo_toplevel())

    def run_integrity_check(self):
        self.integrity_btn.configure(state="disabled", text="Checking...")
        self.status_label.configure(text="Checking DB integrity...", text_color="gray")

        def run():
            ok = backup_service.verify_db_integrity()
            def finish():
                self.integrity_btn.configure(state="normal", text="DB Integrity Check")
                if ok:
                    self.status_label.configure(text="DB OK", text_color="green")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showinfo("Integrity Check", "Database integrity OK.", parent=self.winfo_toplevel())
                else:
                    self.status_label.configure(text="DB Integrity FAIL", text_color="red")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showerror("Integrity Check", "Database integrity failed.", parent=self.winfo_toplevel())
            self.after(0, finish)
        threading.Thread(target=run, daemon=True).start()

    def _load_destinations_ui(self):
        for w in self.destinations_frame.winfo_children():
            w.destroy()
        self.dest_rows = []

        dests = getattr(backup_service.config, "destinations", None) or []
        if not isinstance(dests, list):
            dests = []
        for d in dests:
            if isinstance(d, dict):
                self._add_destination_row(d.get("type", "network_share"), d.get("path", ""), bool(d.get("enabled", True)))

    def _add_destination_row(self, dest_type: str, path: str, enabled: bool):
        row = ctk.CTkFrame(self.destinations_frame)
        row.pack(fill="x", padx=5, pady=4)
        row.grid_columnconfigure(1, weight=1)

        enabled_var = ctk.BooleanVar(value=enabled)
        enabled_switch = ctk.CTkSwitch(row, text="", variable=enabled_var, command=self.save_settings)
        enabled_switch.grid(row=0, column=0, padx=(10, 5), pady=5, sticky="w")

        type_menu = ctk.CTkOptionMenu(row, values=["network_share", "local"], width=120, command=lambda _v: self.save_settings())
        type_menu.set((dest_type or "network_share").lower() if (dest_type or "").lower() in ("network_share", "local") else "network_share")
        type_menu.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        path_entry = ctk.CTkEntry(row)
        path_entry.insert(0, str(path or ""))
        path_entry.grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        path_entry.bind("<FocusOut>", self.save_settings)

        def browse():
            if type_menu.get() == "network_share":
                p = simpledialog.askstring("Network Share", "Enter network share path (e.g., \\\\SERVER\\Share\\Backups):", parent=self.winfo_toplevel())
                if p:
                    path_entry.delete(0, "end")
                    path_entry.insert(0, p.strip())
                    self.save_settings()
            else:
                p = filedialog.askdirectory()
                if p:
                    path_entry.delete(0, "end")
                    path_entry.insert(0, p)
                    self.save_settings()

        browse_btn = ctk.CTkButton(row, text="Browse", width=70, command=browse)
        browse_btn.grid(row=0, column=3, padx=5, pady=5)

        def remove():
            row.destroy()
            self.dest_rows = [r for r in self.dest_rows if r.get("row") != row]
            self.save_settings()

        remove_btn = ctk.CTkButton(row, text="Remove", width=70, fg_color="red", hover_color="darkred", command=remove)
        remove_btn.grid(row=0, column=4, padx=(5, 10), pady=5)

        self.dest_rows.append({"row": row, "enabled_var": enabled_var, "type_menu": type_menu, "path_entry": path_entry})

    def add_destination(self):
        self._add_destination_row("network_share", "", True)
        self.save_settings()

    def verify_and_heal(self):
        self.verify_btn.configure(state="disabled", text="Verifying...")
        self.status_label.configure(text="Verifying backups...", text_color="gray")

        def run():
            res = backup_service.verify_and_heal_recent(limit=25)
            def finish():
                self.verify_btn.configure(state="normal", text="Verify & Heal")
                if res.get("success"):
                    self.status_label.configure(text="Verification OK", text_color="green")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showinfo("Verification", f"Checked: {res.get('checked')}, OK: {res.get('ok')}, Failed: {res.get('failed')}", parent=self.winfo_toplevel())
                else:
                    self.status_label.configure(text="Verification issues", text_color="red")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showwarning("Verification", f"Checked: {res.get('checked')}, OK: {res.get('ok')}, Failed: {res.get('failed')}", parent=self.winfo_toplevel())
            self.after(0, finish)

        threading.Thread(target=run, daemon=True).start()

    def browse_local(self):
        path = filedialog.askdirectory()
        if path:
            self.local_path_entry.delete(0, "end")
            self.local_path_entry.insert(0, path)
            self.save_settings()

    def browse_cloud(self):
        path = filedialog.askdirectory()
        if path:
            self.cloud_path_entry.delete(0, "end")
            self.cloud_path_entry.insert(0, path)
            self.save_settings()

    def save_settings(self, event=None):
        try:
            config = backup_service.config
            config.enabled = self.enabled_var.get()
            config.interval = self.interval_combo.get()
            config.time_str = self.time_entry.get()
            config.local_path = self.local_path_entry.get()
            config.cloud_path = self.cloud_path_entry.get()
            config.retention_days = int(self.retention_entry.get() or 0)
            config.encrypt = self.encrypt_var.get()
            config.backup_mode = self.backup_mode_combo.get()
            config.key_rotation_days = int(self.key_rotation_entry.get() or 90)

            config.retention_policy_enabled = self.tiered_retention_var.get()
            try:
                config.retention_policy = {
                    "hourly": {"keep": int(self.keep_hourly.get() or 0)},
                    "daily": {"keep": int(self.keep_daily.get() or 0)},
                    "weekly": {"keep": int(self.keep_weekly.get() or 0)},
                    "monthly": {"keep": int(self.keep_monthly.get() or 0)},
                    "yearly": {"keep": int(self.keep_yearly.get() or 0)},
                }
            except Exception:
                config.retention_policy = getattr(config, "retention_policy", None) or {}

            destinations = []
            seen = set()
            for r in getattr(self, "dest_rows", []) or []:
                path = (r["path_entry"].get() or "").strip()
                if not path:
                    continue
                key = path.lower()
                if key in seen:
                    continue
                seen.add(key)
                destinations.append({
                    "type": (r["type_menu"].get() or "network_share").strip().lower(),
                    "path": path,
                    "enabled": bool(r["enabled_var"].get())
                })
            config.destinations = destinations
            
            backup_service.save_config()
            self._refresh_key_status()
            
            if config.enabled:
                backup_service.start_scheduler()
            else:
                backup_service.stop_scheduler()
                
        except Exception as e:
            messagebox.showerror("Error", f"Invalid settings: {e}")

    def import_backup(self):
        path = filedialog.askopenfilename(
            title="Select Backup File",
            filetypes=[("Backup Files", "*.zip *.enc"), ("All Files", "*.*")]
        )
        if path:
            self.confirm_restore(path)

    def create_manual_backup(self):
        self.backup_btn.configure(state="disabled", text="Backing up...")
        self.status_label.configure(text="Backing up...", text_color="gray")
        
        def run():
            fmt = "enc" if "enc" in (self.manual_format_combo.get() or "").lower() else "zip"
            res = backup_service.create_backup(is_manual=True, output_format=fmt)
            self.after(0, lambda: self.finish_backup(res))
            
        threading.Thread(target=run, daemon=True).start()

    def finish_backup(self, res):
        self.backup_btn.configure(state="normal", text="Backup Now")
        if res["success"]:
            self.status_label.configure(text="Backup successful", text_color="green")
            self.after(5000, lambda: self.status_label.configure(text=""))
            messagebox.showinfo("Success", res["message"], parent=self.winfo_toplevel())
            self.refresh_history()
        else:
            self.status_label.configure(text="Backup failed", text_color="red")
            self.after(5000, lambda: self.status_label.configure(text=""))
            messagebox.showerror("Error", res["message"], parent=self.winfo_toplevel())

    def refresh_history(self):
        # Clear old widgets
        for widget in self.history_frame.winfo_children():
            widget.destroy()

        backups = backup_service.list_backups()
        
        if not backups:
            ctk.CTkLabel(self.history_frame, text="No backups found.").pack(pady=20)
            return

        for idx, backup in enumerate(backups):
            row = ctk.CTkFrame(self.history_frame)
            row.pack(fill="x", padx=5, pady=2)
            
            # Icon/Name
            ctk.CTkLabel(row, text="📦").pack(side="left", padx=10)
            ctk.CTkLabel(row, text=backup["name"], font=ctk.CTkFont(weight="bold")).pack(side="left", padx=10)
            
            # Details
            info = f"{backup['date']} | {backup['size_mb']} MB"
            btype = ""
            try:
                meta = backup_service.get_backup_public_info(backup["path"])
                btype = str(meta.get("backup_type") or "").upper()
            except Exception:
                btype = ""
            extra = f" | {btype}" if btype else ""
            ctk.CTkLabel(row, text=info + extra, text_color="gray").pack(side="left", padx=10)
            
            # Actions
            ctk.CTkButton(row, text="Details", width=60, fg_color="#7f8c8d", hover_color="#5a6268",
                          command=lambda p=backup["path"]: self.show_backup_details(p)).pack(side="right", padx=5, pady=5)

            ctk.CTkButton(row, text="Verify", width=60, fg_color="#9b59b6", hover_color="#8e44ad",
                          command=lambda p=backup["path"]: self.verify_single(p)).pack(side="right", padx=5, pady=5)

            ctk.CTkButton(row, text="Restore", width=60, fg_color="orange", hover_color="darkorange",
                          command=lambda p=backup["path"]: self.confirm_restore(p)).pack(side="right", padx=5, pady=5)
            
            ctk.CTkButton(row, text="Delete", width=60, fg_color="red", hover_color="darkred",
                          command=lambda p=backup["path"]: self.delete_backup(p)).pack(side="right", padx=5, pady=5)

            ctk.CTkButton(row, text="Open", width=60, fg_color="#3498DB", hover_color="#2980B9",
                          command=lambda p=backup["path"]: self.open_in_folder(p)).pack(side="right", padx=5, pady=5)

    def open_in_folder(self, path: str):
        try:
            folder = str(Path(path).parent)
            if os.name == "nt":
                os.startfile(folder)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def verify_single(self, path: str):
        self.status_label.configure(text="Verifying selected backup...", text_color="gray")
        def run():
            res = backup_service.verify_and_heal_backup(path)
            def finish():
                if res.get("success"):
                    self.status_label.configure(text="Backup OK", text_color="green")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showinfo("Verify", "Verification completed successfully.", parent=self.winfo_toplevel())
                else:
                    self.status_label.configure(text="Backup issues", text_color="red")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showwarning("Verify", res.get("message", "Verification failed."), parent=self.winfo_toplevel())
            self.after(0, finish)
        threading.Thread(target=run, daemon=True).start()

    def show_backup_details(self, path: str):
        p = Path(path)
        info = {
            "backup_path": str(p),
            "exists": p.exists(),
            "size_bytes": int(p.stat().st_size) if p.exists() else 0,
        }
        try:
            info["metadata"] = backup_service.get_backup_public_info(str(p)) or {}
        except Exception as e:
            info["metadata_error"] = str(e)

        win = ctk.CTkToplevel(self)
        win.title("Backup Details")
        win.geometry("800x500")
        win.grab_set()

        title = ctk.CTkLabel(win, text=f"Backup Details: {p.name}", font=ctk.CTkFont(size=18, weight="bold"))
        title.pack(anchor="w", padx=20, pady=(20, 10))

        textbox = ctk.CTkTextbox(win)
        textbox.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        textbox.insert("1.0", json.dumps(info, indent=2, ensure_ascii=False))
        textbox.configure(state="disabled")

    def _precheck_restore_chain(self, path: str) -> dict:
        p = Path(path)
        missing = []
        chain = []
        seen = set()
        backup_dir = p.parent

        def read_meta(file_path: Path) -> dict:
            return backup_service.get_backup_public_info(str(file_path)) or {}

        cur_path = p
        while True:
            if cur_path.name in seen:
                missing.append(f"Cycle detected in backup chain at: {cur_path.name}")
                break
            seen.add(cur_path.name)
            chain.append(cur_path.name)

            meta = read_meta(cur_path)
            cur_type = str(meta.get("backup_type") or "full").strip().lower()
            if cur_type == "full":
                break

            if cur_type == "incremental":
                dep_name = str(meta.get("parent_backup_filename") or "")
            elif cur_type == "differential":
                dep_name = str(meta.get("base_backup_filename") or "")
            else:
                missing.append(f"Unsupported backup type: {cur_type}")
                break

            if not dep_name:
                missing.append(f"Missing dependency reference in {cur_path.name}.")
                break

            dep_path = backup_dir / dep_name
            if not dep_path.exists():
                missing.append(f"Missing dependency backup file: {dep_path.name}")
                break

            cur_path = dep_path

        top_type = ""
        try:
            top_type = str(read_meta(p).get("backup_type") or "").strip().lower()
        except Exception:
            top_type = ""

        warning = ""
        if not top_type:
            warning = "Backup type could not be determined from the file. Restore may still work for FULL backups."

        return {"ok": len(missing) == 0, "warning": warning, "backup_type": top_type, "missing": missing, "chain": chain}

    def confirm_restore(self, path):
        pre = self._precheck_restore_chain(path)
        if not pre.get("ok"):
            detail = "\n".join(pre.get("missing") or [])
            messagebox.showerror(
                "Restore Blocked - Missing Backup Chain",
                f"Cannot restore this backup because required chain files are missing or invalid.\n\n{detail}",
                parent=self.winfo_toplevel(),
            )
            return

        warn = (pre.get("warning") or "").strip()
        if warn:
            if not messagebox.askyesno("Restore Warning", warn + "\n\nDo you want to continue anyway?", parent=self.winfo_toplevel()):
                return

        if messagebox.askyesno("Confirm Restore", "Restoring will OVERWRITE current data.\nAre you sure?"):
            self.run_restore(path)

    def run_restore(self, path):
        self.status_label.configure(text="Restoring...", text_color="gray")
        def run():
            res = backup_service.restore_backup(path)
            def notify():
                if res.get("success"):
                    self.status_label.configure(text="Restore successful", text_color="green")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showinfo("Restore", res.get("message", "Restore successful."), parent=self.winfo_toplevel())
                else:
                    self.status_label.configure(text="Restore failed", text_color="red")
                    self.after(5000, lambda: self.status_label.configure(text=""))
                    messagebox.showerror("Restore Failed", res.get("message", "Restore failed."), parent=self.winfo_toplevel())
            self.after(0, notify)
        threading.Thread(target=run, daemon=True).start()

    def delete_backup(self, path):
        if messagebox.askyesno("Confirm Delete", "Delete this backup permanently?"):
            try:
                if os.path.exists(path):
                    os.remove(path)
                self.refresh_history()
            except Exception as e:
                messagebox.showerror("Error", str(e))
