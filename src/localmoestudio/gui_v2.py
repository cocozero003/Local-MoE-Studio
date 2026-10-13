"""Local MoE Studio v2: Ollama-inspired local desktop GUI for llama.cpp.
No third-party Python libraries required. No network calls outside 127.0.0.1.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
import json
import os
from .backend import Application as BackendApplication

BG = '#FBFBFC'
SIDE = '#F7F7F8'
PANEL = '#F3F4F6'
TEXT = '#111827'
MUTED = '#6B7280'
LINE = '#E5E7EB'
ACCENT = '#222222'

class LocalMoEStudio(BackendApplication):
    def make_ui(self):
        self.title('Local MoE Studio')
        self.geometry('1380x900')
        self.minsize(1040, 700)
        self.configure(bg=BG)
        s = ttk.Style(self)
        s.theme_use('clam')
        s.configure('TFrame', background=BG)
        s.configure('Side.TFrame', background=SIDE)
        s.configure('TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        s.configure('Muted.TLabel', background=BG, foreground=MUTED, font=('Segoe UI', 9))
        s.configure('Title.TLabel', background=BG, foreground=TEXT, font=('Segoe UI', 20, 'bold'))
        s.configure('TEntry', padding=8)
        s.configure('TCombobox', padding=6)
        s.configure('TCheckbutton', background=BG, foreground=TEXT, font=('Segoe UI', 10))
        s.configure('TButton', padding=(13, 9), font=('Segoe UI', 9))
        s.configure('Primary.TButton', background='#242424', foreground='#FFFFFF', padding=(14,10))
        s.map('Primary.TButton', background=[('active', '#444444')])
        self.status = tk.StringVar(value='Ready to configure llama.cpp. Everything stays on this computer.')

        self.shell = tk.Frame(self, bg=BG)
        self.shell.pack(fill='both', expand=True)
        self.sidebar = tk.Frame(self.shell, bg=SIDE, width=220, highlightbackground=LINE, highlightthickness=1)
        self.sidebar.pack(side='left', fill='y')
        self.sidebar.pack_propagate(False)
        brand = tk.Frame(self.sidebar, bg=SIDE)
        brand.pack(fill='x', pady=(21,22), padx=17)
        tk.Label(brand, text='Local MoE Studio', font=('Segoe UI', 13, 'bold'), fg=TEXT, bg=SIDE).pack(anchor='w')
        tk.Label(brand, text='Private local AI', font=('Segoe UI', 9), fg=MUTED, bg=SIDE).pack(anchor='w', pady=(3,0))
        self.nav_buttons = {}
        for key, caption in [('chat','Chat'), ('models','Models'), ('settings','Settings'), ('logs','Server logs')]:
            b = tk.Button(self.sidebar, text=caption, anchor='w', relief='flat', bd=0,
                          font=('Segoe UI', 11), fg=TEXT, bg=SIDE, activebackground='#EDEDED',
                          padx=17, pady=11, cursor='hand2', command=lambda name=key: self.navigate(name))
            b.pack(fill='x', padx=11, pady=2)
            self.nav_buttons[key] = b
        ttk.Separator(self.sidebar).pack(fill='x', padx=16, pady=(27,15))
        tk.Label(self.sidebar, text='LOCAL STATUS', font=('Segoe UI', 9, 'bold'), fg=MUTED, bg=SIDE).pack(anchor='w', padx=20)
        self.state_label = tk.Label(self.sidebar, text='Not running', font=('Segoe UI', 10), fg='#B45309', bg=SIDE)
        self.state_label.pack(anchor='w', padx=20, pady=(7,5))
        tk.Label(self.sidebar, text='Local-only  •  No Docker', font=('Segoe UI', 9), fg=MUTED, bg=SIDE).pack(side='bottom', anchor='w', padx=20, pady=22)

        self.area = tk.Frame(self.shell, bg=BG)
        self.area.pack(side='left', fill='both', expand=True)
        self.views = {}
        for key in ('chat','models','settings','logs'):
            self.views[key] = tk.Frame(self.area, bg=BG)
        self.build_chat()
        self.build_models()
        self.build_settings()
        self.build_logs()
        self.footer = tk.Label(self, textvariable=self.status, anchor='w', bg=SIDE, fg=MUTED,
                               font=('Segoe UI', 9), padx=16, pady=7)
        self.footer.pack(side='bottom', fill='x')
        self.navigate('chat')
        self._refresh_status()

    def navigate(self, tab):
        for frame in self.views.values(): frame.pack_forget()
        self.views[tab].pack(fill='both', expand=True)
        for k,b in self.nav_buttons.items():
            b.configure(bg='#ECEEF2' if k==tab else SIDE,
                        font=('Segoe UI', 11, 'bold' if k==tab else 'normal'))

    def build_chat(self):
        from .chat_composer import build_chat
        build_chat(self)

    def _on_performance_update(self, snapshot):
        from .performance_ui import update_metrics
        update_metrics(self, snapshot)

    def _on_performance_hardware(self, snapshot):
        from .performance_ui import update_hardware
        update_hardware(self, snapshot)

    def _composer_enter(self, event):
        from .chat_composer import composer_enter
        return composer_enter(self, event)

    def _composer_ctrl_enter(self, event):
        from .chat_composer import composer_ctrl_enter
        return composer_ctrl_enter(self, event)

    def attach_text_file(self):
        from .chat_composer import attach_text_file
        return attach_text_file(self)

    def _welcome_chat(self):
        self.transcript.configure(state='normal')
        self.transcript.insert('end', '\nWelcome to Local MoE Studio.\n\n')
        self.transcript.insert('end', 'Choose a model in Models, then start chatting.\n')
        self.transcript.insert('end', 'MoE experts can stay in system RAM when GPU memory is limited.\n')
        self.transcript.configure(state='disabled')

    def build_models(self):
        f=self.views['models']
        area=tk.Frame(f,bg=BG)
        area.pack(fill='both',expand=True,padx=50,pady=36)
        ttk.Label(area,text='Models',style='Title.TLabel').pack(anchor='w')
        ttk.Label(area,text='Use GGUF files stored on this computer. The app does not download or upload model files.',style='Muted.TLabel').pack(anchor='w',pady=(7,24))
        ttk.Label(area,text='Selected GGUF model').pack(anchor='w')
        r=tk.Frame(area,bg=BG);r.pack(fill='x',pady=(7,20))
        ttk.Entry(r,textvariable=self.vars['model']).pack(side='left',fill='x',expand=True)
        ttk.Button(r,text='Browse GGUF',command=self.browse_model).pack(side='left',padx=(10,0))
        ttk.Label(area,text='Suggested model for 6 GB VRAM / 64 GB RAM',style='TLabel').pack(anchor='w')
        tk.Label(area,text='Qwen3 30B-A3B  •  GGUF Q4_K_M',font=('Segoe UI',13,'bold'),bg=PANEL,fg=TEXT,
                 padx=18,pady=17,anchor='w').pack(fill='x',pady=(8,4))
        ttk.Label(area,text='Approximately 18–20 GB of model weights. Try CPU MoE expert offloading in Settings.',style='Muted.TLabel').pack(anchor='w')
        box=tk.Frame(area,bg=PANEL)
        box.pack(fill='x',pady=(28,0))
        tk.Label(box,text='Where to get models',font=('Segoe UI',11,'bold'),bg=PANEL,fg=TEXT,anchor='w',padx=18,pady=12).pack(fill='x')
        tk.Label(box,text='Download an official GGUF model from its publisher, then browse to the file above.\nKeep all shards in the same folder for multi-file models.',
                 font=('Segoe UI',10),bg=PANEL,fg=MUTED,justify='left',anchor='w',padx=18,pady=8).pack(fill='x')
        ttk.Button(area,text='Configure model',command=lambda:self.navigate('settings')).pack(anchor='w',pady=25)

    def browse_model(self):
        p=filedialog.askopenfilename(title='Choose GGUF model',filetypes=[('GGUF','*.gguf'),('All files','*.*')])
        if p:
            self.vars['model'].set(p)
            self.model_name.configure(text=Path(p).name)

    def browse_server(self):
        p=filedialog.askopenfilename(title='Choose llama-server.exe',filetypes=[('Windows executable','*.exe'),('All files','*.*')])
        if p:self.vars['server'].set(p)

    def build_settings(self):
        f=self.views['settings']
        outer=tk.Frame(f,bg=BG)
        outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,bg=BG,highlightthickness=0)
        scrollbar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        inner=tk.Frame(canvas,bg=BG)
        win=canvas.create_window((0,0),window=inner,anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right',fill='y')
        canvas.pack(side='left',fill='both',expand=True)
        inner.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(win,width=e.width))
        main=tk.Frame(inner,bg=BG)
        main.pack(fill='x',padx=50,pady=(31,35))
        ttk.Label(main,text='Settings',style='Title.TLabel').pack(anchor='w')
        ttk.Label(main,text='Control exactly where llama.cpp stores your model weights and KV cache.',style='Muted.TLabel').pack(anchor='w',pady=(6,20))
        self._section(main,'Engine and model')
        self._file_setting(main,'llama-server.exe','server',self.browse_server)
        self._file_setting(main,'GGUF model file','model',self.browse_model)
        self._section(main,'Memory and MoE expert offloading')
        self._select(main,'GPU layers','gpu_layers',['auto','all','0','5','10','20','30','40','99'],
                     'Auto tries to fit memory; use lower values if VRAM runs out.')
        self._select(main,'MoE expert placement','moe',['all','first N layers','disabled'],
                     'All: place MoE expert tensors in system RAM (llama.cpp --cpu-moe).')
        self._input(main,'CPU MoE first N layers','moe_layers','Only when placement is first N layers.')
        self._input(main,'Context length','context','Start with 4096 tokens for a 6 GB GPU.')
        self._select(main,'KV cache type','kv',['q8_0','f16','q4_0'],'Q8_0 typically uses less VRAM than F16.')
        self._check(main,'Enable Flash Attention','flash')
        self._check(main,'Automatic VRAM fitting','fit')
        self._input(main,'Free VRAM target (MiB)','fit_margin','Start with 1024; lower only after testing.')
        self._section(main,'Server and chat')
        self._input(main,'Local API port','port','Always binds to 127.0.0.1; cannot be accessed over LAN.')
        self._input(main,'CPU threads','threads','Auto or positive integer.')
        self._input(main,'System prompt','system','Instructions sent to the local model with each chat.')
        btn=tk.Frame(main,bg=BG)
        btn.pack(fill='x',pady=(27,14))
        ttk.Button(btn,text='Start server',style='Primary.TButton',command=self.start_server).pack(side='left')
        ttk.Button(btn,text='Stop server',command=self.stop_server).pack(side='left',padx=8)
        ttk.Button(btn,text='Save settings',command=self.save_settings).pack(side='left',padx=8)
        ttk.Button(btn,text='Show launch command',command=self.show_command).pack(side='left',padx=8)
        ttk.Label(main,text='Tip: Ollama may remain installed, but unload its model before launching a large llama.cpp model.',style='Muted.TLabel').pack(anchor='w',pady=(4,15))

    def _section(self,container,title):
        tk.Label(container,text=title,font=('Segoe UI',12,'bold'),bg=BG,fg=TEXT).pack(anchor='w',pady=(21,12))
        tk.Frame(container,height=1,bg=LINE).pack(fill='x',pady=(0,10))

    def _line(self,parent,title,hint):
        """Size the settings row to fit its title and helper text at high DPI.

        The old left frame disabled geometry propagation while the adjacent
        input determined the row height, clipping the helper text on Windows.
        """
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x', pady=(9, 11))
        row.grid_columnconfigure(0, minsize=260)
        row.grid_columnconfigure(1, weight=1)
        left = tk.Frame(row, bg=BG)
        left.grid(row=0, column=0, sticky='nw')
        ttk.Label(left, text=title).pack(anchor='w')
        tk.Label(left, text=hint, fg=MUTED, bg=BG,
                 font=('Segoe UI', 9), wraplength=250,
                 justify='left', anchor='w').pack(anchor='w', pady=(4, 0))
        right = tk.Frame(row, bg=BG)
        right.grid(row=0, column=1, sticky='ew', padx=(15, 0))
        return right

    def _file_setting(self,parent,title,key,callback):
        right=self._line(parent,title,'File is read from your local drive.')
        ttk.Entry(right,textvariable=self.vars[key]).pack(side='left',fill='x',expand=True)
        ttk.Button(right,text='Browse',command=callback).pack(side='left',padx=(8,0))
    def _select(self,parent,title,key,values,hint):
        right=self._line(parent,title,hint)
        ttk.Combobox(right,textvariable=self.vars[key],values=values,width=24).pack(side='left')
    def _input(self,parent,title,key,hint):
        right=self._line(parent,title,hint)
        ttk.Entry(right,textvariable=self.vars[key],width=49).pack(side='left',fill='x',expand=True)
    def _check(self,parent,title,key):
        ttk.Checkbutton(parent,text=title,variable=self.vars[key]).pack(anchor='w',pady=7)

    def build_logs(self):
        f=self.views['logs']
        top=tk.Frame(f,bg=BG)
        top.pack(fill='x',padx=34,pady=(25,10))
        ttk.Label(top,text='Server logs',style='Title.TLabel').pack(side='left')
        ttk.Button(top,text='Clear logs',command=self.clear_logs).pack(side='right')
        self.log_text=ScrolledText(f,wrap='word',bg='#171717',fg='#E3E3E3',insertbackground='#FFFFFF',
                                   font=('Consolas',10),relief='flat',state='disabled',padx=17,pady=17)
        self.log_text.pack(fill='both',expand=True,padx=34,pady=(9,29))
        self.append_text(self.log_text,'Server logs will appear here after you click Start server.\n')
    def clear_logs(self):
        self.log_text.configure(state='normal');self.log_text.delete('1.0','end');self.log_text.configure(state='disabled')

    def _refresh_status(self):
        try:
            running=self.process is not None and self.process.poll() is None
            self.state_label.configure(text='Running' if self.ready else ('Loading model…' if running else 'Not running'),
                                       fg='#16803D' if self.ready else '#B45309')
            p=self.vars['model'].get().strip()
            self.model_name.configure(text=Path(p).name if p else 'No model selected')
        except tk.TclError: return
        self.after(1200,self._refresh_status)

    def new_chat(self):
        if self.busy:return
        self.history=[]
        self.transcript.configure(state='normal')
        self.transcript.delete('1.0','end')
        self.transcript.configure(state='disabled')
        self.status.set('New chat started. Current chat is only in memory.')

if __name__=='__main__':
    LocalMoEStudio().mainloop()
