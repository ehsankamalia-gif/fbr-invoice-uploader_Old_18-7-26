import customtkinter as ctk
import webbrowser
from tkinter import messagebox


class ReportsFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        container = ctk.CTkFrame(self, fg_color="transparent")
        container.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        container.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(container, text="Reporting & Dashboards", font=ctk.CTkFont(size=26, weight="bold"))
        title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        subtitle = ctk.CTkLabel(
            container,
            text="Reports are handled by the Reporting Portal with interactive dashboards, templates, exports, and scheduling.",
            wraplength=900,
            justify="left",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(0, 18))

        buttons = ctk.CTkFrame(container, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="w")

        ctk.CTkButton(buttons, text="Open Dashboard", command=lambda: self._open_url("http://localhost:9000/dashboard")).pack(side="left", padx=(0, 10))
        ctk.CTkButton(buttons, text="Template Builder", command=lambda: self._open_url("http://localhost:9000/builder")).pack(side="left", padx=(0, 10))
        ctk.CTkButton(buttons, text="Schedules", command=lambda: self._open_url("http://localhost:9000/schedules")).pack(side="left")

        help_box = ctk.CTkFrame(container)
        help_box.grid(row=3, column=0, sticky="ew", pady=(20, 0))
        help_box.grid_columnconfigure(0, weight=1)

        help_title = ctk.CTkLabel(help_box, text="Quick Tips", font=ctk.CTkFont(size=16, weight="bold"))
        help_title.grid(row=0, column=0, sticky="w", padx=15, pady=(12, 6))

        help_text = ctk.CTkLabel(
            help_box,
            text="1) Use filters on the dashboard for date/status.\n2) Use Template Builder for drag-and-drop layouts.\n3) Use Schedules to auto-generate and email reports.",
            justify="left",
        )
        help_text.grid(row=1, column=0, sticky="w", padx=15, pady=(0, 12))

    def _open_url(self, url: str) -> None:
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("Error", f"Unable to open reporting portal: {e}")
