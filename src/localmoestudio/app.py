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
from .model_hub import (
    CATALOG, FAMILIES, seed_catalog, discover_models, search_hub_models, load_catalog_cache,
    save_catalog_cache, human_size, list_gguf_files, validate_repo, download_file,
)
from .engine_installer import install_engine
from .backend import USER_DATA
from .sessions import SessionStore
from .local_library import list_installed_models
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
        self.catalog_cache_path = USER_DATA / 'model_catalog.json'
        self.catalog_models, self.catalog_cache_date = load_catalog_cache(self.catalog_cache_path)
        if not self.catalog_models:
            self.catalog_models = [m for m in seed_catalog() if m]
        self.catalog_loading = False
        self.session_store = SessionStore(USER_DATA / 'sessions')
        self.active_session = None
        super().__init__()
        self.active_session = self.session_store.create()
        self._refresh_sessions()
        self.after(300, self._check_engine_installed)
        self.after(350, self.refresh_installed_models)
        self.after(140, self._drain_hub_events)
        if self.vars['auto_refresh_catalog'].get():
            self.after(700, self.refresh_catalog)  # Metadata only; never model weights.

    def make_ui(self):
        super().make_ui()
        self.title('Local MoE Studio — Private AI')
        self.hardware_label = tk.Label(self.sidebar, text='RAM / GPU: checking...',
                                       font=('Segoe UI', 9), fg=MUTED, bg=SIDE, justify='left')
        self.hardware_label.pack(side='bottom', anchor='w', padx=19, pady=(0, 8))
        self.after(1600, self._schedule_hardware)
        self.navigate('models')
        self._create_profiles_bar()
        self._create_session_panel()
        self.team_hub_server = None
        self._create_team_hub_launcher()

    def _create_team_hub_launcher(self):
        panel = tk.Frame(self.sidebar, bg=SIDE)
        panel.pack(fill='x', padx=10, pady=(12, 4))
        tk.Label(panel, text='TEAM MODE', bg=SIDE, fg=MUTED,
                 font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(0, 6))
        ttk.Button(panel, text='Open Team Hub',
                   command=self._open_team_hub).pack(fill='x')
        self.share_lan = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text='Share on private LAN',
                        variable=self.share_lan).pack(anchor='w', pady=(8, 0))
        tk.Label(panel, text='Separate accounts, private chats and documents.',
                 bg=SIDE, fg=MUTED, wraplength=185, justify='left',
                 font=('Segoe UI', 8)).pack(anchor='w', pady=(6, 0))

    def _open_team_hub(self):
        from .team_server import start_team_server
        port = 8765
        lan = bool(self.share_lan.get())
        if lan and not messagebox.askyesno('Enable LAN sharing',
                'The Team Hub will be reachable over UNENCRYPTED HTTP on the local network.\n\n'
                'Use a trusted private network only. Do not forward this port to the internet.\n'
                'Continue?'):
            return
        if self.team_hub_server is None:
            try:
                self.team_hub_server = start_team_server(
                    host='0.0.0.0' if lan else '127.0.0.1',
                    port=port, backend_port=int(self.vars['port'].get()), lan=lan)
                threading.Thread(target=self.team_hub_server.serve_forever,
                                 daemon=True, name='LocalMoE-TeamHub').start()
            except (OSError, ValueError) as exc:
                messagebox.showerror('Cannot start Team Hub', str(exc))
                self.team_hub_server = None
                return
        elif self.team_hub_server.lan != lan:
            messagebox.showinfo('Restart needed',
                'Restart Local MoE Studio to change Team Hub LAN access.')
        webbrowser.open('http://127.0.0.1:8765')
        self.status.set('Team Hub running at http://127.0.0.1:8765')

    def close(self):
        # Leave saved GGUF models and user files untouched on exit.
        if self.team_hub_server is not None:
            self.team_hub_server.shutdown()
            self.team_hub_server.server_close()
            self.team_hub_server = None
        super().close()

    def build_models(self):
        f = self.views['models']
        # The catalog and quantization tables are scrollable on smaller screens.
        outer = tk.Frame(f, bg=BG)
        outer.pack(fill='both', expand=True)
        self.models_canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient='vertical', command=self.models_canvas.yview)
        self.models_canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.models_canvas.pack(side='left', fill='both', expand=True)
        shell = tk.Frame(self.models_canvas, bg=BG)
        window = self.models_canvas.create_window((0,0), window=shell, anchor='nw')
        shell.bind('<Configure>', lambda e: self.models_canvas.configure(scrollregion=self.models_canvas.bbox('all')))
        self.models_canvas.bind('<Configure>',lambda e: self.models_canvas.itemconfigure(window,width=e.width))
        shell.configure(padx=39,pady=25)
        self.models_canvas.bind('<Enter>',lambda e:self.models_canvas.bind_all('<MouseWheel>',self._scroll_models))
        self.models_canvas.bind('<Leave>',lambda e:self.models_canvas.unbind_all('<MouseWheel>'))
        tk.Label(shell, text='Models', bg=BG, fg=TEXT, font=('Segoe UI', 20, 'bold')).pack(anchor='w')
        tk.Label(shell, text='Browse public GGUF models, select a quantization, then download and start chatting.',
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
        # Use downloaded GGUFs without opening or double-clicking files in Explorer.
        tk.Label(shell, text='2. Installed models', bg=BG, fg=TEXT,
                 font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(3, 5))
        tk.Label(shell, text='Choose a downloaded GGUF here. Explorer only manages files; it does not load models.',
                 bg=BG, fg=MUTED, font=('Segoe UI', 9)).pack(anchor='w', pady=(0, 6))
        managed_frame = tk.Frame(shell, bg=BG)
        managed_frame.pack(fill='x', pady=(0, 6))
        self.installed_tree = ttk.Treeview(managed_frame, columns=('size', 'location'),
                                          show='tree headings', height=4, selectmode='browse')
        self.installed_tree.heading('#0', text='Downloaded GGUF model')
        self.installed_tree.heading('size', text='Size')
        self.installed_tree.heading('location', text='Folder')
        self.installed_tree.column('#0', width=415, stretch=True)
        self.installed_tree.column('size', width=90, stretch=False, anchor='e')
        self.installed_tree.column('location', width=225, stretch=True)
        self.installed_tree.pack(side='left', fill='x', expand=True)
        managed_scroll = ttk.Scrollbar(managed_frame, orient='vertical', command=self.installed_tree.yview)
        self.installed_tree.configure(yscrollcommand=managed_scroll.set)
        managed_scroll.pack(side='right', fill='y')
        self.installed_tree.bind('<Double-1>', lambda event: self.use_installed_model())
        self.installed_paths = {}
        installed_buttons = tk.Frame(shell, bg=BG)
        installed_buttons.pack(fill='x', pady=(0, 6))
        ttk.Button(installed_buttons, text='Use selected', style='Primary.TButton',
                   command=self.use_installed_model).pack(side='left')
        ttk.Button(installed_buttons, text='Use and start',
                   command=lambda: self.use_installed_model(start=True)).pack(side='left', padx=6)
        ttk.Button(installed_buttons, text='Choose a GGUF file...',
                   command=self.choose_local_gguf).pack(side='left', padx=6)
        ttk.Button(installed_buttons, text='Refresh installed',
                   command=self.refresh_installed_models).pack(side='left', padx=6)
        ttk.Button(installed_buttons, text='Manage files in Explorer',
                   command=self.open_model_folder).pack(side='right')
        self.installed_status = tk.StringVar(value='Looking for existing models...')
        tk.Label(shell, textvariable=self.installed_status, bg=BG, fg=MUTED,
                 anchor='w', justify='left').pack(fill='x', pady=(0, 11))
        ttk.Checkbutton(shell,text='Refresh model listings on startup (metadata only)',
                        variable=self.vars['auto_refresh_catalog'],
                        command=self.save_settings).pack(anchor='w',pady=(0,10))
        tk.Label(shell, text='3. Discover GGUF models', bg=BG, fg=TEXT,
                 font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0,8))
        filters=tk.Frame(shell,bg=BG)
        filters.pack(fill='x',pady=(1,6))
        tk.Label(filters,text='Family',bg=BG,fg=TEXT).pack(side='left')
        self.catalog_family=tk.StringVar(value='All')
        family_box=ttk.Combobox(filters,textvariable=self.catalog_family,
                 values=FAMILIES,state='readonly',width=13)
        family_box.pack(side='left',padx=(6,14))
        family_box.bind('<<ComboboxSelected>>',self._render_catalog)
        tk.Label(filters,text='Sort',bg=BG,fg=TEXT).pack(side='left')
        self.catalog_sort=tk.StringVar(value='Newest updates')
        sort_box=ttk.Combobox(filters,textvariable=self.catalog_sort,
                 values=('Newest updates','Most downloaded'),state='readonly',width=19)
        sort_box.pack(side='left',padx=(6,14))
        sort_box.bind('<<ComboboxSelected>>',self._render_catalog)
        self.refresh_catalog_btn=ttk.Button(filters,text='Refresh latest',command=self.refresh_catalog)
        self.refresh_catalog_btn.pack(side='right')
        search_bar=tk.Frame(shell,bg=BG)
        search_bar.pack(fill='x',pady=(3,8))
        tk.Label(search_bar,text='Find a model',bg=BG,fg=TEXT).pack(side='left')
        self.catalog_search=tk.StringVar()
        search_entry=ttk.Entry(search_bar,textvariable=self.catalog_search)
        search_entry.pack(side='left',fill='x',expand=True,padx=(8,8))
        search_entry.bind('<KeyRelease>',self._render_catalog)
        search_entry.bind('<Return>',lambda e:self.search_catalog_online())
        self.hub_search_btn=ttk.Button(search_bar,text='Search Hugging Face',command=self.search_catalog_online)
        self.hub_search_btn.pack(side='left')
        self.catalog_status=tk.StringVar(value='Loading local cached catalog...')
        tk.Label(shell,textvariable=self.catalog_status,bg=BG,fg=MUTED,
                 anchor='w',justify='left',wraplength=950).pack(fill='x',pady=(0,6))
        catalog_frame=tk.Frame(shell,bg=BG)
        catalog_frame.pack(fill='x',pady=(1,8))
        self.catalog_tree=ttk.Treeview(catalog_frame,columns=('family','downloads','updated'),
                                      show='tree headings',height=7)
        self.catalog_tree.heading('#0',text='Hugging Face GGUF repository')
        self.catalog_tree.heading('family',text='Family')
        self.catalog_tree.heading('downloads',text='Downloads')
        self.catalog_tree.heading('updated',text='Updated')
        self.catalog_tree.column('#0',width=465,stretch=True)
        self.catalog_tree.column('family',width=105,stretch=False)
        self.catalog_tree.column('downloads',width=100,stretch=False,anchor='e')
        self.catalog_tree.column('updated',width=110,stretch=False)
        self.catalog_tree.pack(side='left',fill='x',expand=True)
        catalog_scroll=ttk.Scrollbar(catalog_frame,orient='vertical',command=self.catalog_tree.yview)
        self.catalog_tree.configure(yscrollcommand=catalog_scroll.set)
        catalog_scroll.pack(side='right',fill='y')
        self.catalog_tree.bind('<<TreeviewSelect>>',self._choose_catalog_model)
        self.catalog_tree.bind('<Double-1>',lambda e:self.search_repo())
        self.catalog_visible={}
        tk.Label(shell,text='Select a repository above, then click Find GGUF files to choose its quantization.',
                 bg=BG,fg=MUTED,anchor='w').pack(fill='x',pady=(1,8))
        self._render_catalog()
        tk.Label(shell, text='4. Choose GGUF quantization',bg=BG,fg=TEXT,
                 font=('Segoe UI',11,'bold')).pack(anchor='w',pady=(7,8))


        row = tk.Frame(shell, bg=BG)
        row.pack(fill='x', pady=(0, 8))
        tk.Label(row, text='Quick picks', bg=BG, fg=TEXT).pack(side='left')
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
        self.hub_tree = ttk.Treeview(tv_frame, columns=('size',), show='tree headings', height=7)
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

    def _scroll_models(self,event):
        if self.views['models'].winfo_ismapped():
            self.models_canvas.yview_scroll(-int(event.delta/120),'units')

    def _render_catalog(self,event=None):
        """Render cached/online GGUF model repositories; no network call."""
        if not hasattr(self,'catalog_tree'): return
        family=self.catalog_family.get()
        needle=self.catalog_search.get().strip().casefold()
        models=[m for m in self.catalog_models
                if (family=='All' or m['family']==family)
                and (not needle or needle in m['id'].casefold())]
        if self.catalog_sort.get()=='Most downloaded':
            models.sort(key=lambda m:(m['downloads'],m['updated']),reverse=True)
        else:
            models.sort(key=lambda m:(m['updated'],m['downloads']),reverse=True)
        self.catalog_tree.delete(*self.catalog_tree.get_children())
        self.catalog_visible={}
        for i,m in enumerate(models[:350]):
            iid=str(i)
            self.catalog_visible[iid]=m
            self.catalog_tree.insert('', 'end', iid=iid, text=m['id'],
                                     values=(m['family'],f"{m['downloads']:,}",m['updated']))
        if not self.catalog_loading:
            self.catalog_status.set(f'{len(models)} matching repositories. '
                + ('Cached: '+self.catalog_cache_date[:16] if self.catalog_cache_date else 'Refresh for current models.')
                + ' Model weights are downloaded only when you click Download selected model.')

    def _choose_catalog_model(self,event=None):
        selection=self.catalog_tree.selection()
        if not selection:return
        model=self.catalog_visible.get(selection[0])
        if not model:return
        self.repo_var.set(model['id'])
        self.repo_desc.configure(text=f"{model['family']} / {model['downloads']:,} Hugging Face downloads. Verify publisher and license before use.")

    def refresh_catalog(self):
        """Refresh on every startup, but never download multi-GB model weights."""
        if self.catalog_loading:return
        self.catalog_loading=True
        self.refresh_catalog_btn.configure(state='disabled')
        self.catalog_status.set('Checking Hugging Face for latest public GGUF model repositories...')
        def work():
            try:
                models,warnings=discover_models()
                if not models: raise RuntimeError('No public GGUF repositories returned')
                save_catalog_cache(self.catalog_cache_path,models)
                self.hub_events.put(('catalog_done',(models,warnings)))
            except Exception as exc:
                self.hub_events.put(('catalog_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def search_catalog_online(self):
        """Search beyond predefined families (e.g. SmolLM, Granite, Command-R)."""
        query=self.catalog_search.get().strip()
        if not query:
            self.refresh_catalog();return
        if self.catalog_loading:return
        self.catalog_loading=True
        self.hub_search_btn.configure(state='disabled')
        self.catalog_status.set('Searching Hugging Face for '+query+'...')
        def work():
            try:
                models=search_hub_models(query,limit=100)
                self.hub_events.put(('catalog_search_done',(query,models)))
            except Exception as exc:
                self.hub_events.put(('catalog_error',str(exc)))
        threading.Thread(target=work,daemon=True).start()

    def _catalog_idle(self):
        self.catalog_loading=False
        self.refresh_catalog_btn.configure(state='normal')
        self.hub_search_btn.configure(state='normal')

    def _check_engine_installed(self):
        # Earlier releases used an unversioned folder. New versions coexist.
        engine_dir = USER_DATA / 'engine'
        if not Path(self.vars['server'].get()).is_file():
            candidates = list(engine_dir.glob('llama.cpp-cuda12*/llama-server.exe'))
            candidates += list(engine_dir.glob('llama.cpp-cuda13*/llama-server.exe'))
            candidates += list(engine_dir.glob('llama.cpp-cpu*/llama-server.exe'))
            if candidates:
                newest = max(candidates, key=lambda p: p.stat().st_mtime)
                self.vars['server'].set(str(newest))
                self.save_settings()
        path=Path(self.vars['server'].get())
        self.engine_state.set('Installed: '+str(path) if path.is_file() else 'Not installed. Click Install / Update llama.cpp.')

    def start_server(self):
        if self.engine_installing:
            messagebox.showwarning(
                'Engine update in progress',
                'Wait for the llama.cpp installation to finish before starting a model.'
            )
            return
        return super().start_server()

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
                if not repo and name != 'Custom Hugging Face repo':
                    family=name.split(' ')[0]
                    if family in FAMILIES:
                        self.catalog_family.set(family)
                        self.catalog_search.set('')
                        self._render_catalog()
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

    def refresh_installed_models(self):
        """Refresh the in-app installed GGUF list; never modify model files."""
        if not hasattr(self, 'installed_tree'):
            return
        previous = self.vars['model'].get().strip()
        try:
            models = list_installed_models(self.get_model_dir(), previous)
        except OSError as exc:
            self.installed_status.set('Could not scan installed models: ' + str(exc))
            return
        self.installed_tree.delete(*self.installed_tree.get_children())
        self.installed_paths = {}
        selected_id = None
        for idx, model in enumerate(models):
            key = str(idx)
            self.installed_paths[key] = model
            status = '' if model['complete'] else ' [incomplete shards]'
            self.installed_tree.insert('', 'end', iid=key,
                                       text=model['name'] + status,
                                       values=(human_size(model['size']),
                                               Path(model['location']).name))
            if Path(model['path']) == Path(previous):
                selected_id = key
        if selected_id is not None:
            self.installed_tree.selection_set(selected_id)
            self.installed_tree.see(selected_id)
        self.installed_status.set(
            f'{len(models)} installed GGUF model(s). Select one and click Use and start.'
            if models else 'No GGUF models found. Download a model below or choose a GGUF file.')

    def choose_local_gguf(self):
        """Select a local GGUF directly, without a Windows file association."""
        chosen = filedialog.askopenfilename(
            title='Choose a downloaded GGUF model',
            initialdir=str(self.get_model_dir()),
            filetypes=[('GGUF model', '*.gguf'), ('All files', '*.*')])
        if chosen:
            self._select_model_path(chosen)
            self.refresh_installed_models()

    def browse_model(self):
        self.choose_local_gguf()

    def _select_model_path(self, path):
        path = Path(path)
        if not path.is_file() or path.suffix.lower() != '.gguf':
            messagebox.showerror('Invalid GGUF', 'Select an existing .gguf model file.')
            return False
        if self.process and self.process.poll() is None:
            if self.vars['model'].get().strip() != str(path):
                messagebox.showwarning('Model running',
                                       'Stop the current model before switching to another GGUF.')
                return False
        self.vars['model'].set(str(path))
        self.model_name.configure(text=path.name)
        self.save_settings()
        self.installed_status.set('Selected model: ' + path.name + '. Click Start model or Use and start.')
        return True

    def use_installed_model(self, start=False):
        selected = self.installed_tree.selection()
        if not selected:
            messagebox.showinfo('Select a GGUF', 'Choose a model from Installed models, or use Choose a GGUF file.')
            return
        model = self.installed_paths.get(selected[0])
        if not model:
            return
        if not model['complete']:
            messagebox.showerror('Incomplete model',
                'This model has missing GGUF shards. Download all parts into the same folder before loading.')
            return
        if self._select_model_path(model['path']) and start:
            self._start_from_hub()

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
            self.navigate('models')
            messagebox.showinfo('Install engine', 'Install llama.cpp using the Models page first.')
            return
        model_path = Path(self.vars['model'].get().strip())
        if not model_path.is_file() or model_path.suffix.lower() != '.gguf':
            messagebox.showinfo('Choose GGUF', 'Select an installed GGUF model or choose an existing GGUF file.')
            return
        if self.process and self.process.poll() is None:
            self.navigate('chat')
            return
        self.start_server()
        if self.process is not None and self.process.poll() is None:
            self.navigate('chat')

    def _schedule_hardware(self):
        """Poll hardware in a worker thread; keep all Tk updates on the UI thread."""
        from .performance import sample_hardware
        def work():
            sample = sample_hardware()
            used, total = sample.get('gpu_used_mib'), sample.get('gpu_total_mib')
            gpu = f'GPU: {used:.0f}/{total:.0f} MiB' if total else 'GPU: unavailable'
            used, total = sample.get('ram_used_gib'), sample.get('ram_total_gib')
            ram = f'RAM: {used:.1f}/{total:.0f} GiB' if total else 'RAM: unavailable'
            self.hub_events.put(('hardware', gpu + '\n' + ram))
            self.events.put(('perf_hardware', sample))
        threading.Thread(target=work, daemon=True).start()
        self.after(3000, self._schedule_hardware)

    def _drain_hub_events(self):
        try:
            while True:
                typ, data = self.hub_events.get_nowait()
                if typ == 'catalog_done':
                    models,warnings=data
                    self.catalog_models=models
                    from datetime import datetime,timezone
                    self.catalog_cache_date=datetime.now(timezone.utc).isoformat()
                    self._catalog_idle()
                    self._render_catalog()
                    self.catalog_status.set(f'Refreshed {len(models)} public GGUF repositories. '
                        + (f'{len(warnings)} search sources unavailable; results may be partial.' if warnings else 'Latest model listings ready.'))
                elif typ == 'catalog_search_done':
                    query,models=data
                    by_id={m['id'].lower():m for m in self.catalog_models}
                    for model in models: by_id[model['id'].lower()]=model
                    self.catalog_models=list(by_id.values())
                    self.catalog_family.set('All')
                    self._catalog_idle()
                    self._render_catalog()
                    self.catalog_status.set(f'Found {len(models)} public GGUF repositories for "{query}"; showing matching models.')
                elif typ == 'catalog_error':
                    self._catalog_idle()
                    self._render_catalog()
                    self.catalog_status.set('Could not refresh online: '+data+'. Using cached models if available.')
                elif typ == 'engine_progress':
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
                        self.refresh_installed_models()
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
        self.profile_choice = tk.StringVar(value='GPU first (RAM fallback)')
        ttk.Combobox(bar, textvariable=self.profile_choice, state='readonly', width=29,
                     values=list(PROFILES)).pack(side='left', padx=6)
        ttk.Button(bar, text='Apply preset', command=self._apply_easy_profile).pack(side='left', padx=5)
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
