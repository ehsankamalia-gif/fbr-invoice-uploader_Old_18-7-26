import customtkinter as ctk
import webbrowser
from tkinter import messagebox

try:
    from app.services.fastreport_bridge import (
        is_fastreports_available,
        find_fastreports,
        open_designer,
    )

    _fr_available_fn = is_fastreports_available
    _fr_find_fn = find_fastreports
    _fr_designer_fn = open_designer
except Exception:
    _fr_available_fn = None
    _fr_find_fn = None
    _fr_designer_fn = None


class ReportsFrame(ctk.CTkFrame):
    BASE_URL = "http://127.0.0.1:9000"

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        container.grid_columnconfigure(0, weight=1)

        title_row = ctk.CTkFrame(container, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        title_row.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            title_row,
            text="Reporting & Dashboards",
            font=ctk.CTkFont(size=26, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        self.fr_status_label = ctk.CTkLabel(
            title_row,
            text="● Detecting FastReport…",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#6c757d",
        )
        self.fr_status_label.grid(row=0, column=1, sticky="e", padx=(10, 0))

        subtitle = ctk.CTkLabel(
            container,
            text=(
                "Reports are powered by FastReport Desktop as the primary renderer. "
                "The Reporting Portal provides interactive dashboards, template design, exports, and scheduling. "
                "If FastReport is not installed, legacy renderers (reportlab, openpyxl) are used automatically."
            ),
            wraplength=950,
            justify="left",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 18))

        buttons = ctk.CTkFrame(container, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="w")

        ctk.CTkButton(
            buttons,
            text="📊 Open Dashboard",
            command=lambda: self._open_url(f"{self.BASE_URL}/dashboard"),
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            buttons,
            text="🎨 FastReport Studio",
            command=lambda: self._open_url(f"{self.BASE_URL}/builder"),
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            buttons,
            text="⏰ Schedules",
            command=lambda: self._open_url(f"{self.BASE_URL}/schedules"),
        ).pack(side="left", padx=(0, 10))
        self.designer_btn = ctk.CTkButton(
            buttons,
            text="🛠️ Open Designer Directly",
            command=self._open_designer_directly,
            fg_color="#2c5282",
            hover_color="#2b4a74",
            state="disabled",
        )
        self.designer_btn.pack(side="left")

        help_box = ctk.CTkFrame(container)
        help_box.grid(row=3, column=0, sticky="ew", pady=(20, 0))
        help_box.grid_columnconfigure(0, weight=1)

        help_title = ctk.CTkLabel(
            help_box,
            text="Quick Tips",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        help_title.grid(row=0, column=0, sticky="w", padx=15, pady=(12, 6))

        help_text = ctk.CTkLabel(
            help_box,
            text=(
                "1) Use Dashboard filters for date ranges and invoice status.\n"
                "2) Open FastReport Studio to launch the visual Designer for .frx layouts.\n"
                "3) Scheduled reports try FastReport first; PDF/XLSX/CSV gracefully fall back if not installed.\n"
                "4) For invoice printing with FBR QR codes, use the main Invoices list — Print buttons (not this Reporting portal)."
            ),
            justify="left",
        )
        help_text.grid(row=1, column=0, sticky="w", padx=15, pady=(0, 12))

        self.after(250, self._refresh_fr_status)

    def _refresh_fr_status(self) -> None:
        fr_ok = False
        status_text = "● FastReport NOT INSTALLED"
        color = "#e67e22"
        info = ""
        try:
            if _fr_available_fn is not None:
                fr_ok = bool(_fr_available_fn())
            if fr_ok:
                status_text = "● FastReport ACTIVE"
                color = "#27ae60"
                if _fr_find_fn is not None:
                    info_bits = []
                    paths = _fr_find_fn()
                    if paths.builder:
                        info_bits.append("Builder: " + str(paths.builder).split("\\")[-1])
                    if paths.designer:
                        info_bits.append("Designer: " + str(paths.designer).split("\\")[-1])
                    if info_bits:
                        info = "  [" + " | ".join(info_bits) + "]"
                if self.designer_btn is not None:
                    self.designer_btn.configure(state="normal")
        except Exception:
            status_text = "● FastReport status unknown"
            color = "#6c757d"
        self.fr_status_label.configure(
            text=status_text + info,
            text_color=color,
        )

    def _open_designer_directly(self) -> None:
        try:
            if _fr_designer_fn is None:
                messagebox.showwarning(
                    "FastReport",
                    "FastReport bridge module not available. Open the Reporting Portal Studio page instead.",
                )
                return
            result = _fr_designer_fn(None)
            if not result.ok:
                messagebox.showwarning(
                    "FastReport Designer",
                    result.error_message or "Could not launch FastReport Designer.",
                )
        except Exception as e:
            messagebox.showerror("Error", f"Unable to open Designer: {e}")

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror(
                "Error",
                f"Unable to open reporting portal: {e}",
            )
