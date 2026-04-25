# Script Developer: Gabriel Mihai Sandu
# GitHub Profile: https://github.com/Gabrieliam42

import ctypes
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import traceback
from ctypes import wintypes
from pathlib import Path


PREFERRED_MODELS = ()
APP_NAME = "Ollama Models"
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 800
DARK_ANTHRACITE_BLUE = "#151515"
DARK_ANTHRACITE_PANEL = "#0f0f0f"
DARK_ANTHRACITE_BORDER = "#2c2c2c"
DARK_BUTTON = "#252525"
DARK_BUTTON_ACTIVE = "#383838"
DARK_TEXT = "#f3f6f8"
DARK_MUTED_TEXT = "#c8d0d8"
BRIGHT_DANGER = "#d32020"
BRIGHT_DANGER_ACTIVE = "#f04444"
MODEL_BADGES = (
    "tools",
    "thinking",
    "vision",
    "embedding",
    "completion",
    "audio",
    "cloud",
)
CATEGORY_SORT_PRIORITY = ("tools", "thinking", "vision", "embedding", "completion")
BADGE_STYLES = {
    "tools": {"background": "#1f7a4d", "foreground": "#ffffff"},
    "thinking": {"background": "#5f4bb6", "foreground": "#ffffff"},
    "vision": {"background": "#2468a8", "foreground": "#ffffff"},
    "embedding": {"background": "#b46a16", "foreground": "#101010"},
    "completion": {"background": "#575757", "foreground": "#ffffff"},
    "cloud": {"background": "#168a96", "foreground": "#ffffff"},
    "audio": {"background": "#a13f73", "foreground": "#ffffff"},
}


def get_app_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent


def log_message(message):
    try:
        log_dir = get_app_base_dir() / ".cache"
        log_dir.mkdir(parents=True, exist_ok=True)
        with (log_dir / "Ollama.Tools_LLMs.log").open(
            "a", encoding="utf-8", errors="replace"
        ) as log_file:
            log_file.write(f"{message}\n")
    except Exception:
        pass


def _hex_color_to_colorref(color):
    color = color.lstrip("#")
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return red | (green << 8) | (blue << 16)


def apply_dark_title_bar(window):
    if os.name != "nt":
        return

    try:
        window.update_idletasks()
        hwnd_value = int(window.winfo_id())
        hwnd_values = [hwnd_value]
        get_parent = ctypes.windll.user32.GetParent
        get_parent.argtypes = [wintypes.HWND]
        get_parent.restype = wintypes.HWND
        parent_hwnd = get_parent(wintypes.HWND(hwnd_value))
        if parent_hwnd and parent_hwnd not in hwnd_values:
            hwnd_values.append(parent_hwnd)

        for hwnd_value in hwnd_values:
            hwnd = wintypes.HWND(hwnd_value)
            dark_value = ctypes.c_int(1)
            for attribute_id in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute_id,
                    ctypes.byref(dark_value),
                    ctypes.sizeof(dark_value),
                )
                if result == 0:
                    break

            for attribute_id, color in (
                (34, DARK_ANTHRACITE_BLUE),
                (35, DARK_ANTHRACITE_BLUE),
                (36, DARK_TEXT),
            ):
                color_value = ctypes.c_int(_hex_color_to_colorref(color))
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd,
                    attribute_id,
                    ctypes.byref(color_value),
                    ctypes.sizeof(color_value),
                )
    except Exception:
        pass


def schedule_dark_title_bar(window):
    apply_dark_title_bar(window)
    for delay_ms in (0, 50, 250, 1000):
        window.after(delay_ms, lambda target=window: apply_dark_title_bar(target))


def _candidate_paths():
    configured_path = os.environ.get("OLLAMA_EXE")
    if configured_path:
        yield Path(os.path.expandvars(configured_path)).expanduser()

    base_dir = get_app_base_dir()

    yield base_dir / "ollama.exe"
    yield base_dir / "Ollama" / "ollama.exe"

    resolved_from_path = shutil.which("ollama.exe") or shutil.which("ollama")
    if resolved_from_path:
        yield Path(resolved_from_path)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        yield Path(local_app_data) / "Programs" / "Ollama" / "ollama.exe"

    program_files = os.environ.get("ProgramFiles")
    if program_files:
        yield Path(program_files) / "Ollama" / "ollama.exe"

    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if program_files_x86:
        yield Path(program_files_x86) / "Ollama" / "ollama.exe"


def resolve_ollama_executable():
    for candidate in _candidate_paths():
        if candidate.is_file():
            return str(candidate)

    raise FileNotFoundError(
        "Could not locate ollama.exe. Set OLLAMA_EXE, place ollama.exe next to "
        "this script, add it to PATH, or install Ollama in a standard Windows location."
    )


def isolate_tk_environment():
    # PyInstaller injects Tcl/Tk env vars for the bundled runtime.
    if getattr(sys, "frozen", False):
        return

    for variable_name in ("TCL_LIBRARY", "TK_LIBRARY", "TCLLIBPATH"):
        os.environ.pop(variable_name, None)


def should_replace_model(existing_model, candidate_model, preferred_order):
    existing_is_latest = existing_model["name"].endswith(":latest")
    candidate_is_latest = candidate_model["name"].endswith(":latest")
    if candidate_is_latest != existing_is_latest:
        return candidate_is_latest

    existing_priority = preferred_order.get(existing_model["name"], len(preferred_order))
    candidate_priority = preferred_order.get(
        candidate_model["name"], len(preferred_order)
    )
    if candidate_priority != existing_priority:
        return candidate_priority < existing_priority

    return False


def run_ollama_command(command):
    run_kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": True,
    }

    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        run_kwargs["startupinfo"] = startupinfo
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    return subprocess.run(command, **run_kwargs)


def parse_model_capabilities(show_output):
    capabilities = set()
    in_capabilities = False
    for line in show_output.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue

        lower_line = stripped_line.casefold()
        if line.startswith("  ") and not line.startswith("    "):
            if lower_line == "capabilities":
                in_capabilities = True
                continue

            if in_capabilities:
                break

        if in_capabilities:
            capability_name = lower_line.split()[0]
            if capability_name in MODEL_BADGES:
                capabilities.add(capability_name)

    return tuple(badge for badge in MODEL_BADGES if badge in capabilities)


def normalize_model_badges(model_name, detected_badges):
    badges = set(detected_badges)
    if re.search(r"(^|[:/_\-.])cloud($|[:/_\-.])", model_name.casefold()):
        badges.add("cloud")

    return tuple(badge for badge in MODEL_BADGES if badge in badges)


def get_model_badges(ollama_executable, model_name):
    result = run_ollama_command([ollama_executable, "show", model_name, "-v"])
    return normalize_model_badges(
        model_name,
        parse_model_capabilities(result.stdout),
    )


def model_supports_tools(ollama_executable, model_name):
    return "tools" in get_model_badges(ollama_executable, model_name)


def delete_ollama_model(ollama_executable, model_name):
    return run_ollama_command([ollama_executable, "rm", model_name])


def get_available_models(ollama_executable):
    result = run_ollama_command([ollama_executable, "list"])

    preferred_order = {
        model_name: index for index, model_name in enumerate(PREFERRED_MODELS)
    }
    models = []
    seen_names = set()
    for line in result.stdout.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            continue

        columns = re.split(r"\s{2,}", stripped_line)
        if not columns or columns[0] == "NAME":
            continue

        model_name = columns[0]
        if model_name in seen_names:
            continue

        try:
            model_badges = get_model_badges(ollama_executable, model_name)
        except Exception:
            log_message(
                f"Failed to inspect Ollama model capabilities: {model_name}\n"
                f"{traceback.format_exc()}"
            )
            model_badges = ()

        model_id = columns[1] if len(columns) >= 2 else ""
        model_size = columns[2] if len(columns) >= 3 else ""
        badge_text = " ".join(f"[{badge}]" for badge in model_badges)
        model_entry = {
            "id": model_id,
            "name": model_name,
            "size": model_size,
            "badges": model_badges,
            "display": "  ".join(
                part
                for part in (
                    model_name,
                    f"[{model_size}]" if model_size else "",
                    badge_text,
                )
                if part
            ),
        }

        models.append(model_entry)
        seen_names.add(model_name)

    if not models:
        raise RuntimeError("No Ollama models were found.")

    models.sort(
        key=lambda model: (
            0 if model["name"] in preferred_order else 1,
            preferred_order.get(model["name"], 0),
        )
    )

    return models


def get_model_size_bytes(model_entry):
    size_text = model_entry["size"]
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kmgt]?b)\s*", size_text, re.I)
    if not match:
        return -1

    unit_multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024**2,
        "GB": 1024**3,
        "TB": 1024**4,
    }
    size_value = float(match.group(1))
    size_unit = match.group(2).upper()
    return size_value * unit_multipliers.get(size_unit, -1)


def sort_models_by_name(model_entries):
    return sorted(model_entries, key=lambda model: model["name"].casefold())


def sort_models_by_size(model_entries):
    return sorted(
        model_entries,
        key=lambda model: (-get_model_size_bytes(model), model["name"].casefold()),
    )


def sort_models_by_category(model_entries):
    def category_key(model_entry):
        model_badges = set(model_entry["badges"])
        badge_priority = tuple(
            0 if badge_name in model_badges else 1
            for badge_name in CATEGORY_SORT_PRIORITY
        )
        if "cloud" in model_badges:
            category_group = 3
        elif "audio" in model_badges:
            category_group = 2
        elif model_badges:
            category_group = 0
        else:
            category_group = 1

        return (category_group, *badge_priority, model_entry["name"].casefold())

    return sorted(model_entries, key=category_key)


def write_models_text(model_entries):
    output_path = Path.cwd() / "Ollama_LLMs_Manager.txt"
    output_text = "\n".join(model_entry["display"] for model_entry in model_entries)
    if output_text:
        output_text += "\n"

    output_path.write_text(output_text, encoding="utf-8")
    log_message(f"Wrote model list: {output_path}")


def show_models_window():
    isolate_tk_environment()

    import tkinter as tk
    from tkinter import messagebox

    class DarkVerticalScrollbar(tk.Canvas):
        def __init__(self, master, **kwargs):
            super().__init__(
                master,
                bg=DARK_ANTHRACITE_PANEL,
                bd=0,
                highlightthickness=0,
                relief="flat",
                width=16,
                **kwargs,
            )
            self._command = None
            self._first = 0.0
            self._last = 1.0
            self._drag_offset = 0
            self._thumb_id = self.create_rectangle(
                3,
                2,
                13,
                30,
                fill=DARK_BUTTON_ACTIVE,
                outline=DARK_BUTTON_ACTIVE,
            )
            self.bind("<Configure>", lambda event: self._draw_thumb())
            self.bind("<Button-1>", self._on_click)
            self.bind("<B1-Motion>", self._on_drag)
            self.bind("<ButtonRelease-1>", self._on_release)

        def configure(self, cnf=None, **kwargs):
            if cnf and isinstance(cnf, dict):
                kwargs.update(cnf)
                cnf = None

            command = kwargs.pop("command", None)
            if command is not None:
                self._command = command

            if kwargs:
                return super().configure(cnf, **kwargs)

            return None

        config = configure

        def set(self, first, last):
            self._first = max(0.0, min(float(first), 1.0))
            self._last = max(self._first, min(float(last), 1.0))
            self._draw_thumb()

        def _thumb_bounds(self):
            height = max(self.winfo_height(), 1)
            if self._last >= 1.0 and self._first <= 0.0:
                return 2, height - 2

            thumb_height = max(int((self._last - self._first) * height), 28)
            available_height = max(height - thumb_height - 4, 1)
            top = int(2 + self._first * available_height)
            bottom = min(top + thumb_height, height - 2)
            return top, bottom

        def _draw_thumb(self):
            top, bottom = self._thumb_bounds()
            self.coords(self._thumb_id, 3, top, 13, bottom)
            self.itemconfig(
                self._thumb_id,
                fill=DARK_BUTTON_ACTIVE,
                outline=DARK_BUTTON_ACTIVE,
            )

        def _scroll_to_pointer(self, pointer_y):
            if self._command is None:
                return

            height = max(self.winfo_height(), 1)
            top, bottom = self._thumb_bounds()
            thumb_height = bottom - top
            available_height = max(height - thumb_height - 4, 1)
            fraction = (pointer_y - self._drag_offset - 2) / available_height
            self._command("moveto", max(0.0, min(fraction, 1.0)))

        def _on_click(self, event):
            top, bottom = self._thumb_bounds()
            if top <= event.y <= bottom:
                self._drag_offset = event.y - top
            else:
                self._drag_offset = max((bottom - top) // 2, 0)
                self._scroll_to_pointer(event.y)

            return "break"

        def _on_drag(self, event):
            self._scroll_to_pointer(event.y)
            return "break"

        def _on_release(self, event):
            self._drag_offset = 0
            return "break"

    root = tk.Tk()
    root.title(APP_NAME)
    root.configure(bg=DARK_ANTHRACITE_BLUE)
    root.resizable(True, True)

    result_queue = queue.Queue()
    message_var = tk.StringVar(value="Scanning Ollama models...")
    current_models = []
    selected_model_index = [None]

    def close(event=None):
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.bind("<Return>", close)
    root.bind("<Escape>", close)

    frame = tk.Frame(root, bg=DARK_ANTHRACITE_BLUE, padx=18, pady=18)
    frame.pack(fill="both", expand=True)

    header_frame = tk.Frame(frame, bg=DARK_ANTHRACITE_BLUE)
    header_frame.pack(fill="x")

    tk.Label(
        header_frame,
        textvariable=message_var,
        bg=DARK_ANTHRACITE_BLUE,
        fg=DARK_TEXT,
        justify="left",
        wraplength=420,
    ).pack(side="left", fill="x", expand=True, anchor="w")

    sort_button_frame = tk.Frame(header_frame, bg=DARK_ANTHRACITE_BLUE)
    sort_button_frame.pack(side="right")

    list_frame = tk.Frame(
        frame,
        bg=DARK_ANTHRACITE_PANEL,
        highlightthickness=1,
        highlightbackground=DARK_ANTHRACITE_BORDER,
        highlightcolor=DARK_ANTHRACITE_BORDER,
    )
    list_frame.pack(fill="both", expand=True, pady=(12, 16))

    scrollbar = DarkVerticalScrollbar(list_frame)
    scrollbar.pack(side="right", fill="y")

    model_text = tk.Text(
        list_frame,
        bg=DARK_ANTHRACITE_PANEL,
        fg=DARK_TEXT,
        highlightthickness=0,
        relief="flat",
        font=("Consolas", 10),
        width=60,
        height=10,
        wrap="none",
        cursor="arrow",
        padx=8,
        pady=8,
        spacing1=1,
        spacing3=3,
        yscrollcommand=scrollbar.set,
    )
    model_text.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=model_text.yview)

    model_text.tag_configure("model_name", foreground=DARK_TEXT)
    model_text.tag_configure("model_size", foreground=DARK_MUTED_TEXT)
    model_text.tag_configure("selected", background="#2f3c49")
    for badge_name, style in BADGE_STYLES.items():
        model_text.tag_configure(
            f"badge_{badge_name}",
            background=style["background"],
            foreground=style["foreground"],
        )
        model_text.tag_raise(f"badge_{badge_name}", "selected")

    model_text.insert("end", "Scanning...")
    model_text.config(state="disabled")

    button_frame = tk.Frame(frame, bg=DARK_ANTHRACITE_BLUE)
    button_frame.pack(fill="x")

    delete_button = tk.Button(
        button_frame,
        text="Delete Selected LLM",
        command=lambda: delete_selected_model(),
        bg=BRIGHT_DANGER,
        fg="#ffffff",
        activebackground=BRIGHT_DANGER_ACTIVE,
        activeforeground="#ffffff",
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    delete_button.pack(side="left")

    sort_name_button = tk.Button(
        sort_button_frame,
        text="Sort by Name",
        command=lambda: sort_current_models("name"),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    sort_name_button.pack(side="left", padx=(0, 8))

    sort_size_button = tk.Button(
        sort_button_frame,
        text="Sort by Size",
        command=lambda: sort_current_models("size"),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    sort_size_button.pack(side="left")

    sort_category_button = tk.Button(
        sort_button_frame,
        text="Sort by Category",
        command=lambda: sort_current_models("category"),
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=14,
        pady=6,
        state="disabled",
    )
    sort_category_button.pack(side="left", padx=(8, 0))

    tk.Button(
        button_frame,
        text="Close",
        command=close,
        bg=DARK_BUTTON,
        fg=DARK_TEXT,
        activebackground=DARK_BUTTON_ACTIVE,
        activeforeground=DARK_TEXT,
        relief="flat",
        bd=0,
        padx=18,
        pady=6,
    ).pack(side="right")

    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    position_x = (screen_width - WINDOW_WIDTH) // 2
    position_y = (screen_height - WINDOW_HEIGHT) // 2
    root.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}+{position_x}+{position_y}")
    schedule_dark_title_bar(root)
    model_text.focus_set()

    def set_model_text_state(state):
        model_text.config(state=state)

    def clear_model_text():
        set_model_text_state("normal")
        model_text.delete("1.0", "end")

    def finish_model_text_update():
        set_model_text_state("disabled")

    def insert_model_entry(model_entry):
        model_text.insert("end", model_entry["name"], ("model_name",))
        if model_entry["size"]:
            model_text.insert("end", f"  [{model_entry['size']}]", ("model_size",))

        for badge_name in model_entry["badges"]:
            model_text.insert("end", "  ")
            model_text.insert(
                "end",
                f" {badge_name} ",
                (f"badge_{badge_name}",),
            )

        model_text.insert("end", "\n")

    def select_model(index):
        model_text.tag_remove("selected", "1.0", "end")
        selected_model_index[0] = None
        if index is None or index < 0 or index >= len(current_models):
            return "break"

        selected_model_index[0] = index
        line_start = f"{index + 1}.0"
        line_end = f"{index + 1}.end"
        model_text.tag_add("selected", line_start, line_end)
        model_text.mark_set("insert", line_start)
        model_text.see(line_start)
        return "break"

    def get_model_index_at_event(event):
        text_index = model_text.index(f"@{event.x},{event.y}")
        line_number = int(text_index.split(".", maxsplit=1)[0])
        model_index = line_number - 1
        if 0 <= model_index < len(current_models):
            return model_index

        return None

    def select_clicked_model(event):
        model_text.focus_set()
        return select_model(get_model_index_at_event(event))

    def move_selected_model(offset):
        if not current_models:
            return "break"

        current_index = selected_model_index[0]
        if current_index is None:
            current_index = 0
        else:
            current_index = min(
                max(current_index + offset, 0),
                len(current_models) - 1,
            )

        return select_model(current_index)

    def select_first_model(event=None):
        if current_models:
            return select_model(0)

        return "break"

    def select_last_model(event=None):
        if current_models:
            return select_model(len(current_models) - 1)

        return "break"

    model_text.bind("<Button-1>", select_clicked_model)
    model_text.bind("<Up>", lambda event: move_selected_model(-1))
    model_text.bind("<Down>", lambda event: move_selected_model(1))
    model_text.bind("<Home>", select_first_model)
    model_text.bind("<End>", select_last_model)
    model_text.bind("<Delete>", lambda event: (delete_selected_model(), "break")[1])

    def populate_models(model_entries):
        current_models[:] = model_entries
        selected_model_index[0] = None
        message_var.set(f"{len(model_entries)} Ollama model(s) found.")
        clear_model_text()

        for model_entry in model_entries:
            insert_model_entry(model_entry)

        finish_model_text_update()

        if model_entries:
            select_model(0)

    def sort_current_models(sort_kind):
        if not current_models:
            messagebox.showwarning(APP_NAME, "No Ollama models are available to sort.")
            return

        if sort_kind == "name":
            sorted_models = sort_models_by_name(current_models)
            sort_message = "sorted by name"
        elif sort_kind == "size":
            sorted_models = sort_models_by_size(current_models)
            sort_message = "sorted by size"
        else:
            sorted_models = sort_models_by_category(current_models)
            sort_message = "sorted by category"

        populate_models(sorted_models)
        write_models_text(current_models)
        message_var.set(f"{len(current_models)} Ollama model(s) found, {sort_message}.")

    def set_controls_state(state):
        delete_button.config(state=state)
        sort_name_button.config(state=state)
        sort_size_button.config(state=state)
        sort_category_button.config(state=state)

    def set_busy(message):
        message_var.set(message)
        set_controls_state("disabled")

    def set_ready():
        set_controls_state("normal" if current_models else "disabled")

    def scan_models():
        try:
            log_message("Starting Ollama model scan.")
            ollama_executable = resolve_ollama_executable()
            log_message(f"Using Ollama executable: {ollama_executable}")
            model_entries = get_available_models(ollama_executable)
            model_entries = sort_models_by_category(model_entries)
            write_models_text(model_entries)
            log_message(f"Found {len(model_entries)} model(s).")
            result_queue.put(("models", model_entries))
        except Exception as exc:
            log_message(traceback.format_exc())
            result_queue.put(("error", str(exc)))

    def ask_delete_confirmation(model_name):
        result = {"confirmed": False}
        dialog = tk.Toplevel(root)
        dialog.title(APP_NAME)
        dialog.configure(bg=DARK_ANTHRACITE_BLUE)
        dialog.resizable(False, False)
        dialog.transient(root)
        dialog.grab_set()

        def cancel(event=None):
            result["confirmed"] = False
            dialog.destroy()

        def confirm(event=None):
            result["confirmed"] = True
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", cancel)
        dialog.bind("<Escape>", cancel)

        content_frame = tk.Frame(
            dialog,
            bg=DARK_ANTHRACITE_BLUE,
            padx=22,
            pady=18,
        )
        content_frame.pack(fill="both", expand=True)

        tk.Label(
            content_frame,
            text="Delete this Ollama model?",
            bg=DARK_ANTHRACITE_BLUE,
            fg=DARK_TEXT,
            font=("Segoe UI", 11, "bold"),
            justify="left",
        ).pack(anchor="w")

        tk.Label(
            content_frame,
            text=model_name,
            bg=DARK_ANTHRACITE_BLUE,
            fg=DARK_TEXT,
            font=("Consolas", 10),
            justify="left",
            wraplength=520,
        ).pack(fill="x", anchor="w", pady=(12, 0))

        tk.Label(
            content_frame,
            text=f"This will run: ollama rm {model_name}",
            bg=DARK_ANTHRACITE_BLUE,
            fg=DARK_MUTED_TEXT,
            justify="left",
            wraplength=520,
        ).pack(fill="x", anchor="w", pady=(10, 0))

        dialog_button_frame = tk.Frame(content_frame, bg=DARK_ANTHRACITE_BLUE)
        dialog_button_frame.pack(fill="x", pady=(18, 0))

        cancel_button = tk.Button(
            dialog_button_frame,
            text="Cancel",
            command=cancel,
            bg=DARK_BUTTON,
            fg=DARK_TEXT,
            activebackground=DARK_BUTTON_ACTIVE,
            activeforeground=DARK_TEXT,
            relief="flat",
            bd=0,
            padx=18,
            pady=7,
        )
        cancel_button.pack(side="right")

        tk.Button(
            dialog_button_frame,
            text="Delete",
            command=confirm,
            bg=BRIGHT_DANGER,
            fg="#ffffff",
            activebackground=BRIGHT_DANGER_ACTIVE,
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
            padx=18,
            pady=7,
        ).pack(side="right", padx=(0, 10))

        dialog.update_idletasks()
        root_x = root.winfo_rootx()
        root_y = root.winfo_rooty()
        root_width = root.winfo_width()
        root_height = root.winfo_height()
        dialog_width = dialog.winfo_width()
        dialog_height = dialog.winfo_height()
        position_x = root_x + (root_width - dialog_width) // 2
        position_y = root_y + (root_height - dialog_height) // 2
        dialog.geometry(f"+{position_x}+{position_y}")
        schedule_dark_title_bar(dialog)
        cancel_button.focus_set()
        root.wait_window(dialog)
        return result["confirmed"]

    def delete_selected_model():
        selected_index = selected_model_index[0]
        if selected_index is None or not current_models:
            messagebox.showwarning(APP_NAME, "Select an Ollama model to delete.")
            return

        if selected_index >= len(current_models):
            messagebox.showwarning(APP_NAME, "Select an Ollama model to delete.")
            return

        model_name = current_models[selected_index]["name"]
        confirmed = ask_delete_confirmation(model_name)
        if not confirmed:
            return

        set_busy(f"Deleting {model_name}...")

        def delete_model():
            try:
                ollama_executable = resolve_ollama_executable()
                log_message(f"Deleting Ollama model: {model_name}")
                delete_ollama_model(ollama_executable, model_name)
                log_message("Rescanning Ollama models after delete.")
                try:
                    model_entries = get_available_models(ollama_executable)
                except RuntimeError as exc:
                    if str(exc) != "No Ollama models were found.":
                        raise
                    model_entries = []
                model_entries = sort_models_by_category(model_entries)
                write_models_text(model_entries)
                log_message(f"Deleted Ollama model: {model_name}")
                result_queue.put(("deleted", (model_name, model_entries)))
            except Exception as exc:
                log_message(traceback.format_exc())
                result_queue.put(("delete_error", str(exc)))

        threading.Thread(target=delete_model, daemon=True).start()

    def schedule_poll_results():
        if root.winfo_exists():
            root.after(100, poll_results)

    def poll_results():
        try:
            result_type, payload = result_queue.get_nowait()
        except queue.Empty:
            schedule_poll_results()
            return

        try:
            if result_type == "models":
                populate_models(payload)
                set_ready()
            elif result_type == "deleted":
                model_name, model_entries = payload
                populate_models(model_entries)
                set_ready()
                messagebox.showinfo(APP_NAME, f"Deleted Ollama model:\n\n{model_name}")
            elif result_type == "delete_error":
                set_ready()
                messagebox.showerror(APP_NAME, payload)
            else:
                message_var.set("Failed to scan Ollama models.")
                set_ready()
                selected_model_index[0] = None
                clear_model_text()
                model_text.insert("end", payload)
                finish_model_text_update()
                messagebox.showerror(APP_NAME, payload)
        finally:
            schedule_poll_results()

    threading.Thread(target=scan_models, daemon=True).start()
    root.after(100, poll_results)
    root.mainloop()


def show_error(message):
    try:
        isolate_tk_environment()

        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, message)
        root.destroy()
    except Exception:
        print(f"Error: {message}", file=sys.stderr)


def main():
    try:
        log_message("Starting application.")
        show_models_window()
    except Exception as exc:
        log_message(traceback.format_exc())
        show_error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
