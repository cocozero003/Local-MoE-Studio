"""Compact live performance dashboard for the Windows desktop chat."""
import tkinter as tk
from tkinter import ttk
from .backend import USER_DATA
from .performance import read_history

BG = '#F6F7F9'
MUTED = '#68707D'
TEXT = '#22252B'


def build_strip(app, parent, row=3):
    host = tk.Frame(parent, bg=BG, highlightbackground='#E7E9EC', highlightthickness=1)
    host.grid(row=row, column=0, sticky='ew', padx=48, pady=(0, 8))
    app.perf_panel = host
    upper = tk.Frame(host, bg=BG)
    upper.pack(fill='x', padx=13, pady=(6, 2))
    tk.Label(upper, text='PERFORMANCE', fg=TEXT, bg=BG,
             font=('Segoe UI', 9, 'bold')).pack(side='left')
    app.perf_status = tk.StringVar(value='Waiting for response')
    tk.Label(upper, textvariable=app.perf_status, fg=MUTED, bg=BG,
             font=('Segoe UI', 9)).pack(side='left', padx=(12, 0))
    ttk.Button(upper, text='History', command=lambda: show_history(app)).pack(side='right')
    cells = tk.Frame(host, bg=BG)
    cells.pack(fill='x', padx=12, pady=(2, 9))
    labels = [('speed','Generation'),('ttft','First token'),('tokens','Output tokens'),
              ('elapsed','Response time'),('vram','GPU VRAM'),('ram','System RAM')]
    app.perf_vars = {}
    for i, (key, title) in enumerate(labels):
        cells.grid_columnconfigure(i, weight=1, uniform='perf')
        frame = tk.Frame(cells, bg=BG)
        frame.grid(row=0, column=i, sticky='ew', padx=3)
        tk.Label(frame, text=title, fg=MUTED, bg=BG,
                 font=('Segoe UI', 8)).pack(anchor='w')
        var = tk.StringVar(value='--')
        app.perf_vars[key] = var
        tk.Label(frame, textvariable=var, fg=TEXT, bg=BG,
                 font=('Segoe UI', 10, 'bold')).pack(anchor='w')


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
        app.perf_status.set('Streaming; live chunks are not token counts')
    elif source == 'server':
        app.perf_status.set('Complete - server-reported timings')
    elif source == 'estimated':
        app.perf_status.set('Complete - token count / wall generation time')
    else:
        app.perf_status.set('Complete - token timings unavailable')


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
