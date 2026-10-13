"""Compact, pinned sidebar performance metrics for the local llama.cpp model."""
import tkinter as tk
from tkinter import ttk
from .backend import USER_DATA
from .performance import read_history

BG = '#F7F7F8'
MUTED = '#6B7280'
TEXT = '#111827'


def build_sidebar(app, sidebar):
    """Keep generation timings above dedicated GPU and system RAM usage."""
    host = tk.Frame(sidebar, bg=BG)
    host.pack(side='bottom', fill='x', padx=12, pady=(4, 10))
    app.perf_panel = host

    header = tk.Frame(host, bg=BG)
    header.pack(fill='x', pady=(0, 5))
    tk.Label(header, text='PERFORMANCE', bg=BG, fg=MUTED,
             font=('Segoe UI', 9, 'bold')).pack(side='left')
    ttk.Button(header, text='History', command=lambda: show_history(app)).pack(side='right')
    app.perf_status = tk.StringVar(value='Waiting for a response')
    tk.Label(host, textvariable=app.perf_status, bg=BG, fg=MUTED,
             font=('Segoe UI', 8), anchor='w', justify='left',
             wraplength=184).pack(fill='x', pady=(0, 7))

    grid = tk.Frame(host, bg=BG)
    grid.pack(fill='x')
    app.perf_vars = {}
    for i, (key, title) in enumerate((
        ('speed', 'Generation'), ('ttft', 'First token'),
        ('tokens', 'Output tokens'), ('elapsed', 'Response time'),
    )):
        grid.columnconfigure(i % 2, weight=1, uniform='perf')
        cell = tk.Frame(grid, bg=BG)
        cell.grid(row=i // 2, column=i % 2, sticky='ew', pady=(0, 7))
        tk.Label(cell, text=title, bg=BG, fg=MUTED,
                 font=('Segoe UI', 8)).pack(anchor='w')
        var = tk.StringVar(value='--')
        app.perf_vars[key] = var
        tk.Label(cell, textvariable=var, bg=BG, fg=TEXT,
                 font=('Segoe UI', 9, 'bold'), anchor='w',
                 justify='left', wraplength=90).pack(anchor='w')

    ttk.Separator(host).pack(fill='x', pady=(1, 8))
    hardware = tk.Frame(host, bg=BG)
    hardware.pack(fill='x')
    for i, (key, title) in enumerate((('vram', 'GPU VRAM'), ('ram', 'System RAM'))):
        hardware.columnconfigure(i, weight=1, uniform='hardware')
        cell = tk.Frame(hardware, bg=BG)
        cell.grid(row=0, column=i, sticky='ew')
        tk.Label(cell, text=title, bg=BG, fg=MUTED,
                 font=('Segoe UI', 8)).pack(anchor='w')
        var = tk.StringVar(value='--')
        app.perf_vars[key] = var
        tk.Label(cell, textvariable=var, bg=BG, fg=TEXT,
                 font=('Segoe UI', 9), justify='left',
                 wraplength=90).pack(anchor='w')


def update_metrics(app, sample):
    if not hasattr(app, 'perf_vars'):
        return
    v = app.perf_vars
    speed = sample.get('generation_tok_s')
    source = sample.get('source')
    if speed is not None:
        v['speed'].set(f'{speed:.2f} tok/s' + (' (est.)' if source == 'estimated' else ''))
    elif sample.get('active') and sample.get('chunks_per_second') is not None:
        v['speed'].set(f"{sample['chunks_per_second']:.1f} chunks/s")
    else:
        v['speed'].set('--')
    ttft = sample.get('ttft_s')
    v['ttft'].set(f'{ttft:.2f} s' if ttft is not None else '--')
    tokens = sample.get('completion_tokens')
    v['tokens'].set(str(tokens) if tokens is not None else '--')
    v['elapsed'].set(f"{sample.get('elapsed_s', 0):.1f} s")
    if sample.get('error'):
        app.perf_status.set('Request failed')
    elif sample.get('active'):
        app.perf_status.set('Streaming; chunks are not tokens')
    elif source == 'server':
        app.perf_status.set('Measured by llama.cpp')
    elif source == 'estimated':
        app.perf_status.set('Estimated generation speed')
    else:
        app.perf_status.set('Token timings unavailable')


def update_hardware(app, sample):
    if not hasattr(app, 'perf_vars'):
        return
    used, total = sample.get('gpu_used_mib'), sample.get('gpu_total_mib')
    app.perf_vars['vram'].set(f'{used / 1024:.1f}/{total / 1024:.1f} GiB' if total else 'Unavailable')
    used, total = sample.get('ram_used_gib'), sample.get('ram_total_gib')
    app.perf_vars['ram'].set(f'{used:.1f}/{total:.1f} GiB' if total else 'Unavailable')


def show_history(app):
    window = tk.Toplevel(app)
    window.title('Local performance history')
    window.geometry('900x420')
    tk.Label(window, text='Recent local inference runs', font=('Segoe UI', 14, 'bold')).pack(anchor='w', padx=15, pady=12)
    columns = ('model','tokens','speed','ttft','duration','source')
    tree = ttk.Treeview(window, columns=columns, show='headings')
    for key, caption, width in [('model','Model',290),('tokens','Tokens',80),
                                ('speed','tok/s',85),('ttft','First token (s)',125),
                                ('duration','Duration (s)',115),('source','Timing source',130)]:
        tree.heading(key, text=caption)
        tree.column(key, width=width, anchor='w')
    tree.pack(fill='both', expand=True, padx=15, pady=(0,15))
    for run in read_history(USER_DATA / 'performance_history.jsonl', limit=80):
        tree.insert('', 'end', values=(
            str(run.get('model') or '').split('\\')[-1],
            run.get('completion_tokens') if run.get('completion_tokens') is not None else '--',
            run.get('generation_tok_s') if run.get('generation_tok_s') is not None else '--',
            run.get('ttft_s') if run.get('ttft_s') is not None else '--',
            run.get('elapsed_s') if run.get('elapsed_s') is not None else '--',
            run.get('source') or '--'))
