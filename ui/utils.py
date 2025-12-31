import os
import platform
import subprocess
import tkinter as tk
from tkinter import filedialog
from typing import Optional
import streamlit as st

def open_file_dialog(select_folder: bool = False) -> Optional[str]:
    """Opens a system-native file or folder selection dialog."""
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        root.lift()
        root.update_idletasks()
        path = filedialog.askdirectory() if select_folder else filedialog.askopenfilename()
        root.destroy()
        return path if path else None
    except Exception:
        return None

def open_in_file_manager(path: str):
    """
    Opens the file manager at the specified path.
    If path is a file, it highlights the file.
    If path is a directory, it opens the directory.
    """
    path = os.path.abspath(path)
    system = platform.system()

    try:
        if system == "Windows":
            path = os.path.normpath(path)
            if os.path.isfile(path):
                subprocess.run(['explorer', '/select,', path])
            else:
                subprocess.run(['explorer', path])
        elif system == "Darwin":  # macOS
            if os.path.isfile(path):
                subprocess.run(['open', '-R', path])
            else:
                subprocess.run(['open', path])
        else:  # Linux
            # xdg-open usually opens the directory containing the file
            dir_path = os.path.dirname(path) if os.path.isfile(path) else path
            subprocess.run(['xdg-open', dir_path])
    except Exception as e:
        st.error(f"Could not open file manager: {e}")

def open_file_in_default_app(path: str):
    """Opens the file in the system's default application for that file type."""
    try:
        path = os.path.abspath(path)
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":  # macOS
            subprocess.run(['open', path])
        else:  # Linux
            subprocess.run(['xdg-open', path])
    except Exception as e:
        st.error(f"Error opening file: {e}")
