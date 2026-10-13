"""Local MoE Studio: Windows model browser, downloader, and llama.cpp chat.
Uses Python standard library only. Backend is the upstream llama.cpp llama-server.
"""
import os
import queue
import shutil
import subprocess
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .backend import Application as Core
from .model_hub import CATALOG, human_size, list_gguf_files, validate_repo, download_file
from .engine_installer import install_engine
from .backend import USER_DATA
from .sessions import SessionStore
from .profiles import PROFILES, apply_profile, infer_profile, recommendation

BG = '#FFFFFF'
SIDE = '#F8F8F8'
PANEL = '#F4F4F4'
TEXT = '#222222'
MUTED = '#747474'
LINE = '#E5E5E5'

# Reuse the established, tested desktop layout and local llama.cpp runner from v2.
# Only the model browser, downloading and convenience workflows are new in v3.
from .gui_v2 import LocalMoEStudio as PriorUI

class LocalMoEStudio(PriorUI):
    def __init__(self):
        self.hub_events = queue.Queue()
        self.cancel_download = threading.Event()
        self.is_downloading = False
        self.engine_cancel = threading.Event()
        self.engine_installing = False
        self.session_store = SessionStore(USER_DATA / 'sessions')
        self.active_session = None
        super().__init__()
        self.active_session = self.session_store.create()
        self._refresh_sessions()
        self.after(300, self._check_engine_installed)
        self.after(140, self._drain_hub_events)

    def make_ui(self):
        super().make_ui()
        self.title('Local MoE Studio 5 — Private AI')
        self.hardware_label = tk.Label(self.sidebar, text='RAM / GPU: checking...',
                                       font=('Segoe UI', 9), fg=MUTED, bg=SIDE, justify='left')
        self.hardware_label.pack(side='bottom', anchor='w', padx=19, pady=(0, 8))
        self.after(1600, self._schedule_hardware)
        self.navigate('models')
        self._create_profiles_bar()
        self._create_session_panel()

    def build_models(self):
        f = self.views['models']
        shell = tk.Frame(f, bg=BG)
        shell.pack(fill='both', expand=True, padx=39, pady=25)
        tk.Label(shell, text='Models', bg=BG, fg=TEXT, font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        tk.Label(shell, text='First install the inference engine, then download a GGUF model and start chatting.',
                 bg=BG, fg=MUTED, font=('Segoe UI', 10)).pack(anchor='w', pady=(5, 10))
        engine = tk.Frame(shell, bg=PANEL, padx=12, pady=10)
        engine.pack(fill='x', pady=(0, 15))
        top = tk.Frame(engine, bg=PANEL)
        top.pack(fill='x')
        tk.Label(top, text='1. Install llama.cpp engine', bg=PANEL, fg=TEXT,
                 font=('Segoe UI', 11, 'bold')).pack(side='left')
        self.engine_mode = tk.StringVar(value='cuda12')
        ttk.Combobox(top, textvariable=self.engine_mode, state='readonly', width=16,
                     values=['cuda12', 'cuda13', 'cpu']).pack(side='left', padx=10)
        self.install_btn = ttk.Button(top, text='Install / Update llama.cpp', style='Primary.TButton',
                                      command=self.start_engine_install)
        self.install_btn.pack(side='left')
        ttk.Button(top, text='Cancel', command=self.cancel_engine_install).pack(side='left', padx=5)
        self.engine_state = tk.StringVar(value='Checking installed engine...')
        tk.Label(engine, textvariable=self.engine_state, bg=PANEL, fg=MUTED, anchor='w',
                 justify='left').pack(fill='x', pady=(8, 3))
        self.engine_bar = ttk.Progressbar(engine, maximum=100)
        self.engine_bar.pack(fill='x')
        tk.Label(engine, text='CUDA 12 is recommended for most NVIDIA Windows PCs. Downloads official GitHub release binaries and matching CUDA DLLs.',
                 bg=PANEL, fg=MUTED, anchor='w', wraplength=800, justify='left').pack(fill='x',pady=(6,0))
        tk.Label(shell, text='2. Choose a GGUF model', bg=BG, fg=TEXT,
                 font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0, 8))

        row = tk.Frame(shell, bg=BG)
        row.pack(fill='x', pady=(0, 8))
        tk.Label(row, text='Suggested model', bg=BG, fg=TEXT).pack(side='left')
        self.catalog_name = tk.StringVar(value=CATALOG[0][0])
        combo = ttk.Combobox(row, textvariable=self.catalog_name,
                             values=[c[0] for c in CATALOG], state='readonly', width=32)
        combo.pack(side='left', padx=12)
        combo.bind('<<ComboboxSelected>>', self._pick_catalog)
        tk.Label(shell, text='Hugging Face repository (owner/model)', bg=BG, fg=TEXT).pack(anchor='w', pady=(6, 3))
        repo_row = tk.Frame(shell, bg=BG)
        repo_row.pack(fill='x')
        self.repo_var = tk.StringVar(value=CATALOG[0][1])
        ttk.Entry(repo_row, textvariable=self.repo_var).pack(side='left', fill='x', expand=True)
        self.search_btn = ttk.Button(repo_row, text='Find GGUF files', command=self.search_repo)
        self.search_btn.pack(side='left', padx=(8,0))
        self.repo_desc = tk.Label(shell, text=CATALOG[0][2], bg=BG, fg=MUTED, anchor='w')
        self.repo_desc.pack(fill='x', pady=(4, 12))

        center = tk.Frame(shell, bg=BG)
        center.pack(fill='both', expand=True)
        tk.Label(center, text='Available quantizations / GGUF files', font=('Segoe UI', 11, 'bold'),
                 bg=BG, fg=TEXT).pack(anchor='w', pady=(2, 6))
        tv_frame = tk.Frame(center, bg=BG)
        tv_frame.pack(fill='both', expand=True)
        self.hub_tree = ttk.Treeview(tv_frame, columns=('size',), show='tree headings', height=10)
        self.hub_tree.heading('#0', text='GGUF file')
        self.hub_tree.heading('size', text='Download size')
        self.hub_tree.column('#0', width=510, stretch=True)
        self.hub_tree.column('size', width=130, stretch=False)
        scroll = ttk.Scrollbar(tv_frame, orient='vertical', command=self.hub_tree.yview)
        self.hub_tree.configure(yscrollcommand=scroll.set)
        self.hub_tree.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        self.hub_tree.bind('<Double-1>', lambda e: self.start_download())
        self.available = {}

        download_row = tk.Frame(shell, bg=BG)
        download_row.pack(fill='x', pady=(13, 8))
        self.download_btn = ttk.Button(download_row, text='Download selected model',
                                       style='Primary.TButton', command=self.start_download)
        self.download_btn.pack(side='left')
        ttk.Button(download_row, text='Cancel', command=self.cancel_current_download).pack(side='left', padx=8)
        ttk.Button(download_row, text='Open models folder', command=self.open_model_folder).pack(side='right')
        self.download_bar = ttk.Progressbar(shell, mode='determinate', maximum=100)
        self.download_bar.pack(fill='x')
        self.download_text = tk.StringVar(value='Choose a model and click Find GGUF files.')
        tk.Label(shell, textvariable=self.download_text, bg=BG, fg=MUTED, anchor='w').pack(fill='x',pady=(5, 8))

        installed = tk.Frame(shell, bg=BG)
        installed.pack(fill='x', pady=(4,0))
        tk.Label(installed, text='Selected local model', bg=BG, fg=TEXT).pack(anchor='w')
        localrow = tk.Frame(installed, bg=BG)
        localrow.pack(fill='x', pady=5)
        ttk.Entry(localrow, textvariable=self.vars['model']).pack(side='left', fill='x', expand=True)
        ttk.Button(localrow, text='Browse', command=self.browse_model).pack(side='left', padx=6)
        ttk.Button(localrow, text='Load settings', command=lambda:self.navigate('settings')).pack(side='left')
        ttk.Button(localrow, text='Start model', style='Primary.TButton', command=self._start_from_hub).pack(side='left',padx=(6,0))

    def _check_engine_installed(self):
        local = USER_DATA / 'engine' / 'llama.cpp-cuda12' / 'llama-server.exe'
        if local.is_file() and not Path(self.vars['server'].get()).is_file():
            self.vars['server'].set(str(local))
            self.save_settings()
        path=Path(self.vars['server'].get())
        self.engine_state.set('Installed: '+str(path) if path.is_file() else 'Not installed. Click Install / Update llama.cpp.')

    def start_engine_install(self):
        if self.engine_installing:
            return
        if self.process and self.process.poll() is None:
            messagebox.showwarning('Stop model first', 'Stop the running inference server before updating llama.cpp.')
            return
        mode=self.engine_mode.get()
        backend='NVIDIA CUDA 12' if mode=='cuda12' else ('NVIDIA CUDA 13' if mode=='cuda13' else 'CPU-only')
        if not messagebox.askyesno('Install official llama.cpp',
             f'Download the latest available {backend} Windows release from ggml-org/llama.cpp?\n\n'
             'The NVIDIA build may require several hundred MB of downloads and adequate disk space.\n'
             'Existing model files are not affected.'):
            return
        self.engine_cancel.clear()
        self.engine_installing=True
        self.install_btn.configure(state='disabled')
        self.engine_state.set('Checking official GitHub releases...')
        def work():
            try:
                result=install_engine(USER_DATA/'engine',mode,
                    lambda name,n,total:self.hub_events.put(('engine_progress',(name,n,total))),
                    self.engine_cancel)
                self.hub_events.put(('engine_done',result))
            except Exception as exc:
                self.hub_events.put(('engine_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def cancel_engine_install(self):
        if self.engine_installing:
            self.engine_cancel.set()
            self.engine_state.set('Cancelling download or extraction...')

    def _pick_catalog(self, event=None):
        for name, repo, description in CATALOG:
            if name == self.catalog_name.get():
                self.repo_var.set(repo)
                self.repo_desc.configure(text=description)
                break

    def search_repo(self):
        try:
            repo = validate_repo(self.repo_var.get().strip())
        except ValueError as exc:
            messagebox.showerror('Repository', str(exc)); return
        self.search_btn.configure(state='disabled')
        self.download_text.set('Loading model files...')
        self.hub_tree.delete(*self.hub_tree.get_children())
        self.available = {}
        def work():
            try:
                files = list_gguf_files(repo)
                self.hub_events.put(('search_done', (repo, files)))
            except Exception as exc:
                self.hub_events.put(('search_error', str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def get_model_dir(self):
        return USER_DATA / 'models'

    def open_model_folder(self):
        folder = self.get_model_dir()
        folder.mkdir(exist_ok=True)
        if os.name == 'nt':
            os.startfile(str(folder))
        else:
            webbrowser.open(folder.as_uri())

    def start_download(self):
        if self.is_downloading:
            messagebox.showinfo('Download underway', 'Wait for this download, or cancel it.'); return
        selection = self.hub_tree.selection()
        if not selection:
            messagebox.showinfo('Choose a file', 'Select one GGUF quantization first.'); return
        file_path = self.hub_tree.item(selection[0], 'text')
        repo = self.listed_repo
        size = self.available.get(file_path,0)
        if '-00001-of-' in file_path or ('-of-' in file_path and '.gguf' in file_path):
            if not messagebox.askyesno('Multi-part GGUF', 'This looks like a sharded GGUF. Downloading one shard alone is insufficient. Continue anyway?'):
                return
        if size and shutil.disk_usage(self.get_model_dir().parent).free < size * 1.05:
            messagebox.showerror('Disk space', 'Not enough free disk space for this GGUF file.'); return
        if not messagebox.askyesno('Download model', f'Download {file_path}\n\nSize: {human_size(size)}\n\nFrom: {repo}\n\nThis uses your internet connection and saves model files locally.'):
            return
        self.cancel_download.clear()
        self.is_downloading = True
        self.download_btn.configure(state='disabled')
        self.download_text.set('Starting download...')
        def work():
            try:
                dest = download_file(repo,file_path,self.get_model_dir(),
                                     lambda *data:self.hub_events.put(('download_progress',data)),
                                     self.cancel_download)
                self.hub_events.put(('download_finished', str(dest) if dest else None))
            except Exception as exc:
                self.hub_events.put(('download_error', str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def cancel_current_download(self):
        if self.is_downloading:
            self.cancel_download.set()
            self.download_text.set('Cancelling after current data chunk...')

    def _start_from_hub(self):
        if not Path(self.vars['server'].get().strip()).is_file():
            self.navigate('settings')
            messagebox.showinfo('Install engine', 'Use Install / Update llama.cpp at the top of the Models page first.')
            return
        if not self.vars['model'].get().strip():
            messagebox.showinfo('Choose GGUF','Download or browse to a local GGUF model first.')
            return
        self.start_server()
        self.navigate('chat')

    def _schedule_hardware(self):
        def work():
            result = []
            try:
                output = subprocess.check_output(['nvidia-smi', '--query-gpu=memory.used,memory.total',
                     '--format=csv,noheader,nounits'], stderr=subprocess.DEVNULL,timeout=4,
                     encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).strip().splitlines()[0]
                used, total = [x.strip() for x in output.split(',')[:2]]
                result.append(f'GPU: {used}/{total} MiB')
            except Exception:
                result.append('GPU: nvidia-smi unavailable')
            try:
                if os.name == 'nt':
                    import ctypes
                    class MEMORYSTATUSEX(ctypes.Structure):
                        _fields_ = [('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),
                                   ('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),
                                   ('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),
                                   ('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),
                                   ('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
                    mem=MEMORYSTATUSEX(); mem.dwLength=ctypes.sizeof(mem)
                    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
                        result.append(f'RAM: {(mem.ullTotalPhys-mem.ullAvailPhys)/2**30:.1f}/{mem.ullTotalPhys/2**30:.0f} GiB')
            except Exception:
                pass
            self.hub_events.put(('hardware', '\n'.join(result)))
        threading.Thread(target=work,daemon=True).start()
        self.after(8000,self._schedule_hardware)

    # Intercept hardware events in one queue without touching Tk from worker threads.
    def _drain_hub_events(self):
        try:
            while True:
                typ, data = self.hub_events.get_nowait()
                if typ == 'engine_progress':
                    name, n, total=data
                    self.engine_state.set(name + (f' — {human_size(n)} / {human_size(total)}' if total else ''))
                    self.engine_bar['value'] = min(100, n/total*100) if total else 0
                elif typ == 'engine_done':
                    self.engine_installing=False
                    self.install_btn.configure(state='normal')
                    path,tag,verified=data
                    self.vars['server'].set(path)
                    self.save_settings()
                    self.engine_state.set('Installed llama.cpp '+tag+' — '+path)
                    self.engine_bar['value']=100
                    messagebox.showinfo('Engine installed', 'llama.cpp installed and selected. Now choose a model below.\n\nSHA-256 checked for '+str(verified)+' asset(s) where GitHub provided digests.')
                elif typ == 'engine_error':
                    self.engine_installing=False
                    self.install_btn.configure(state='normal')
                    self.engine_state.set('Engine installation failed: '+data)
                    messagebox.showerror('Installation error', data)
                elif typ == 'hardware':
                    self.hardware_label.configure(text=data)
                elif typ == 'search_done':
                    repo, files = data
                    self.listed_repo = repo
                    self.available = {f['path']:f['size'] for f in files}
                    self.hub_tree.delete(*self.hub_tree.get_children())
                    for ix, item in enumerate(files):
                        self.hub_tree.insert('', 'end',iid=str(ix),text=item['path'],values=(human_size(item['size']),))
                    self.search_btn.configure(state='normal')
                    self.download_text.set(f'{len(files)} GGUF file(s) found. Select a single-file quantization to download.')
                elif typ == 'search_error':
                    self.search_btn.configure(state='normal')
                    self.download_text.set('Model listing failed: ' + data)
                elif typ == 'download_progress':
                    _, n, total = data
                    self.download_bar['value'] = min(100,100*n/total) if total else 0
                    self.download_text.set(f'Downloaded {human_size(n)} / {human_size(total)}' if total else f'Downloaded {human_size(n)}')
                elif typ == 'download_finished':
                    self.is_downloading = False
                    self.download_btn.configure(state='normal')
                    if data:
                        self.vars['model'].set(data)
                        self.save_settings()
                        self.download_bar['value'] = 100
                        self.download_text.set('Ready: '+Path(data).name)
                        messagebox.showinfo('Download complete','GGUF saved and selected. Open Settings to configure MoE offloading, then click Start model.')
                    else:
                        self.download_text.set('Download paused. Select the same model again to resume.')
                elif typ == 'download_error':
                    self.is_downloading = False
                    self.download_btn.configure(state='normal')
                    self.download_text.set('Download failed: ' + data + ' (partial file kept for resume)')
        except queue.Empty:
            pass
        self.after(140,self._drain_hub_events)


    def _create_profiles_bar(self):
        view = self.views['settings']
        bar = tk.Frame(view, bg='#F4F4F4', padx=12, pady=9)
        bar.pack(side='bottom', fill='x')
        tk.Label(bar, text='Easy setup:', bg='#F4F4F4', fg='#222222',
                 font=('Segoe UI', 10, 'bold')).pack(side='left', padx=(0, 8))
        self.profile_choice = tk.StringVar(value='Large MoE (low VRAM)')
        ttk.Combobox(bar, textvariable=self.profile_choice, state='readonly', width=27,
                     values=list(PROFILES)).pack(side='left', padx=6)
        ttk.Button(bar, text='Apply recommended settings', command=self._apply_easy_profile).pack(side='left', padx=5)
        ttk.Button(bar, text='Check model fit', command=self._recommend_model).pack(side='left')

    def _apply_easy_profile(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('Model running', 'Stop the server before changing model memory settings.')
            return
        profile = self.profile_choice.get()
        apply_profile(self.vars, profile)
        self.save_settings()
        messagebox.showinfo('Profile applied', PROFILES[profile]['description'] +
            '\n\nAdvanced settings remain editable. Load your model from the Models tab.')

    def _recommend_model(self):
        path = self.vars['model'].get().strip()
        name = Path(path).name
        if not Path(path).is_file():
            messagebox.showinfo('Choose a model', 'Download or select a GGUF file in Models first.')
            return
        size = Path(path).stat().st_size
        advice = recommendation(name, size, self.vars['moe'].get())
        messagebox.showinfo('Model fit estimate', advice)

    def _create_session_panel(self):
        panel = tk.Frame(self.sidebar, bg='#F8F8F8')
        panel.pack(fill='x', padx=12, pady=(13, 3))
        tk.Label(panel, text='SAVED CONVERSATIONS', bg='#F8F8F8', fg='#747474',
                 font=('Segoe UI', 9, 'bold')).pack(anchor='w')
        self.session_list = tk.Listbox(panel, height=7, relief='flat',
                       activestyle='none', bg='#F8F8F8', fg='#222222',
                       font=('Segoe UI', 9), selectmode='browse', exportselection=False)
        self.session_list.pack(fill='x', pady=4)
        self.session_list.bind('<<ListboxSelect>>', lambda event: self._open_session())
        actions = tk.Frame(panel, bg='#F8F8F8')
        actions.pack(fill='x')
        ttk.Button(actions, text='New', command=self.new_chat).pack(side='left')
        ttk.Button(actions, text='Delete', command=self._delete_session).pack(side='left', padx=4)
        self._session_ids = []

    def _refresh_sessions(self):
        if not hasattr(self, 'session_list'):
            return
        self.session_list.delete(0, 'end')
        data = self.session_store.list_all()
        self._session_ids = [item['id'] for item in data]
        for item in data:
            self.session_list.insert('end', item.get('title', 'New chat')[:26])

    def _open_session(self):
        if self.busy:
            return
        selected = self.session_list.curselection()
        if not selected:
            return
        self.active_session = self._session_ids[selected[0]]
        record = self.session_store.read(self.active_session)
        self.history = record.get('messages', [])
        self.transcript.configure(state='normal')
        self.transcript.delete('1.0', 'end')
        for msg in self.history:
            title = 'YOU' if msg.get('role') == 'user' else 'ASSISTANT'
            self.transcript.insert('end', '\n'+title+'\n'+str(msg.get('content',''))+'\n')
        self.transcript.configure(state='disabled')
        self.navigate('chat')

    def _delete_session(self):
        if self.busy:
            return
        selected = self.session_list.curselection()
        if not selected:
            return
        sid = self._session_ids[selected[0]]
        if not messagebox.askyesno('Delete conversation', 'Permanently delete this local conversation?'):
            return
        self.session_store.delete(sid)
        if sid == self.active_session:
            self.active_session = self.session_store.create()
            super().new_chat()
        self._refresh_sessions()

    def new_chat(self):
        if self.busy:
            return
        self.active_session = self.session_store.create()
        super().new_chat()
        self._refresh_sessions()

    def drain_events(self):
        # Preserve backend streaming, while saving fully completed user/assistant pairs.
        pending = []
        try:
            while True:
                event = self.events.get_nowait()
                pending.append(event)
        except queue.Empty:
            pass
        for typ, data in pending:
            if typ == 'chat_done':
                try:
                    self.session_store.append_pair(self.active_session, data[0], data[1])
                except Exception as exc:
                    self.status.set('Could not save conversation: ' + str(exc))
        for event in pending:
            self.events.put(event)
        if pending:
            self.after_idle(self._refresh_sessions)
        super().drain_events()

def main():
    LocalMoEStudio().mainloop()


if __name__ == '__main__':
    main()
