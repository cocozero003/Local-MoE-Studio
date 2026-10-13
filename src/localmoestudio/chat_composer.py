"""Pinned desktop chat composer and keyboard/file controls.

The chat transcript owns a weighted grid row. The composer is a separate,
non-expanding grid row, so it remains visible as the window is resized.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path

BG = '#FBFBFC'
PANEL = '#F4F5F7'
TEXT = '#111827'
MUTED = '#6B7280'
LINE = '#E5E7EB'


def build_chat(self):
    """Chat transcript scrolls; the message composer stays on screen."""
    frame = self.views['chat']
    frame.grid_columnconfigure(0, weight=1)
    frame.grid_rowconfigure(2, weight=1)

    bar = tk.Frame(frame, bg=BG)
    bar.grid(row=0, column=0, sticky='ew', padx=52, pady=(28, 10))
    tk.Label(bar, text='Chat', bg=BG, fg=TEXT,
             font=('Segoe UI', 18, 'bold')).pack(side='left')

    model_bar = tk.Frame(frame, bg=BG)
    model_bar.grid(row=1, column=0, sticky='ew', padx=36)
    tk.Label(model_bar, text='Current model:', bg=BG, fg=MUTED,
             font=('Segoe UI', 9)).pack(side='left')
    self.model_name = tk.Label(model_bar, text='No model selected', bg=BG,
                               fg=TEXT, font=('Segoe UI', 10, 'bold'))
    self.model_name.pack(side='left', padx=9)

    center = tk.Frame(frame, bg=BG)
    center.grid(row=2, column=0, sticky='nsew', padx=72, pady=(14, 12))
    center.grid_rowconfigure(0, weight=1)
    center.grid_columnconfigure(0, weight=1)
    self.transcript = ScrolledText(center, wrap='word', state='disabled',
                                  relief='flat', bd=0, bg=BG, fg=TEXT,
                                  insertbackground=TEXT, font=('Segoe UI', 11),
                                  padx=22, pady=18, spacing1=4, spacing2=2, spacing3=12)
    self.transcript.grid(row=0, column=0, sticky='nsew')
    from .chat_renderer import configure
    configure(self)

    # Grid reserves the bottom row for the message composer.
    compose_shell = tk.Frame(frame, bg=PANEL, highlightbackground=LINE,
                             highlightthickness=1)
    compose_shell.grid(row=3, column=0, sticky='ew', padx=64, pady=(4, 18))
    self.compose_shell = compose_shell
    tk.Label(compose_shell, text='Message', bg=PANEL,
             fg=MUTED, font=('Segoe UI', 9)).pack(anchor='w', padx=15, pady=(11, 0))
    self.prompt = tk.Text(compose_shell, height=3, wrap='word', bg=PANEL,
                          fg=TEXT, relief='flat', bd=0,
                          font=('Segoe UI', 11), padx=14, pady=9,
                          insertbackground=TEXT, undo=True)
    self.prompt.pack(fill='x')
    self.prompt.bind('<Return>', self._composer_enter)
    self.prompt.bind('<Control-Return>', self._composer_ctrl_enter)

    opts = tk.Frame(compose_shell, bg=PANEL)
    opts.pack(fill='x', padx=12, pady=(0, 11))
    ttk.Button(opts, text='Attach text', command=self.attach_text_file).pack(side='left')
    self.chat_continue_button = ttk.Button(opts, text='Continue answer',
                                           command=self.continue_answer, state='disabled')
    self.chat_continue_button.pack(side='left', padx=(8, 0))
    tk.Label(opts, text='Enter to send / Shift+Enter for a new line',
             bg=PANEL, fg=MUTED, font=('Segoe UI', 9)).pack(side='left', padx=(10, 0))
    self.chat_send_button = ttk.Button(opts, text='Send',
                                       style='Primary.TButton', command=self.send_message)
    self.chat_send_button.pack(side='right')
    ttk.Entry(opts, textvariable=self.vars['max_tokens'], width=7).pack(side='right', padx=(5, 10))
    ttk.Checkbutton(opts, text='Auto-continue', variable=self.vars['auto_continue'],
                    command=self.save_settings).pack(side='left', padx=(12, 0))
    tk.Label(opts, text='Tokens/request', bg=PANEL, fg=MUTED,
             font=('Segoe UI', 9)).pack(side='right')
    self._welcome_chat()


def composer_enter(self, event):
    """Enter sends; Shift+Enter allows a new line."""
    if event.state & 0x0001:
        return None
    self.send_message()
    return 'break'


def composer_ctrl_enter(self, event):
    self.send_message()
    return 'break'


def attach_text_file(self):
    """Insert a small UTF-8 text file into the current prompt."""
    path = filedialog.askopenfilename(
        title='Attach a text document',
        filetypes=[('Text and source files', '*.txt *.md *.csv *.json *.log *.py'),
                   ('All files', '*.*')])
    if not path:
        return
    try:
        chosen = Path(path)
        if chosen.stat().st_size > 16000:
            raise ValueError('Please attach a text file smaller than 16 KB. '
                             'For large documents, use the Team Hub document library.')
        content = chosen.read_text(encoding='utf-8-sig')
        if not content.strip():
            raise ValueError('The selected file is empty.')
        self.prompt.insert('end', f'\n\nDocument: {chosen.name}\n{content}\n')
        self.prompt.focus_set()
    except (OSError, UnicodeError, ValueError) as exc:
        messagebox.showerror('Cannot attach file', str(exc))
