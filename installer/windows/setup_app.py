from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import urllib.request
import zipfile

APP_VERSION = "0.9.2"
GITHUB_ZIP = "https://github.com/cocozero003/Local-MoE-Studio/archive/refs/heads/main.zip"

def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent

RESOURCE_ROOT = resource_root()
DATA_PACK = RESOURCE_ROOT / "ThaiFDA_DataPack.zip"

def default_install_path() -> Path:
    local = Path(os.getenv("LOCALAPPDATA") or Path.home())
    candidates = [
        Path(r"C:\Local-MoE-Studio"),
        Path.home() / "Local-MoE-Studio",
        local / "Programs" / "LocalMoEStudioThaiFDA",
    ]
    for p in candidates[:2]:
        if (p / "src" / "localmoestudio" / "team_server.py").is_file():
            return p
    return candidates[-1]

class Installer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Local MoE Studio - Thai FDA Edition Setup")
        self.geometry("790x620")
        self.minsize(730, 570)
        self.configure(bg="#f6f7f9")
        self.install_path = tk.StringVar(value=str(default_install_path()))
        self.create_shortcuts = tk.BooleanVar(value=True)
        self.launch_after = tk.BooleanVar(value=False)
        self.busy = False
        self._build()

    def _build(self):
        shell = tk.Frame(self, bg="#f6f7f9")
        shell.pack(fill="both", expand=True, padx=28, pady=24)
        tk.Label(shell, text="Local MoE Studio - Thai FDA Edition",
                 font=("Segoe UI", 20, "bold"), bg="#f6f7f9", fg="#1f2933").pack(anchor="w")
        tk.Label(shell,
                 text="Install or upgrade Local MoE Studio with Thai FDA V3.16/V3.17 precedent data and Data & Updates management.",
                 font=("Segoe UI", 10), bg="#f6f7f9", fg="#687581", wraplength=710,
                 justify="left").pack(anchor="w", pady=(7, 20))
        box=tk.Frame(shell,bg="#fff",highlightbackground="#dfe4e8",highlightthickness=1)
        box.pack(fill="x",pady=(0,12))
        tk.Label(box,text="Install / upgrade folder",font=("Segoe UI",10,"bold"),
                 bg="#fff",fg="#26313b").pack(anchor="w",padx=16,pady=(14,6))
        row=tk.Frame(box,bg="#fff");row.pack(fill="x",padx=16,pady=(0,14))
        ttk.Entry(row,textvariable=self.install_path).pack(side="left",fill="x",expand=True)
        ttk.Button(row,text="Browse",command=self.browse).pack(side="left",padx=(8,0))
        opts=tk.Frame(shell,bg="#f6f7f9");opts.pack(fill="x",pady=(0,10))
        ttk.Checkbutton(opts,text="Create Desktop shortcuts",variable=self.create_shortcuts).pack(anchor="w",pady=2)
        ttk.Checkbutton(opts,text="Open Thai FDA Team Hub after setup",variable=self.launch_after).pack(anchor="w",pady=2)
        info=tk.Frame(shell,bg="#eef4f7");info.pack(fill="x",pady=(2,12))
        tk.Label(info,text="Included",font=("Segoe UI",10,"bold"),bg="#eef4f7",fg="#24333d").pack(anchor="w",padx=14,pady=(10,2))
        tk.Label(info,text="Bundled Thai FDA runtime data, Local MoE Studio updater, data-pack upload/rollback, source staging and software patch support.",
                 font=("Segoe UI",9),bg="#eef4f7",fg="#52626d",wraplength=700,justify="left").pack(anchor="w",padx=14,pady=(0,10))
        self.progress=ttk.Progressbar(shell,mode="determinate",maximum=100);self.progress.pack(fill="x",pady=(2,8))
        self.status=tk.StringVar(value="Ready");ttk.Label(shell,textvariable=self.status).pack(anchor="w")
        log_frame=tk.Frame(shell,bg="#fff",highlightbackground="#dfe4e8",highlightthickness=1)
        log_frame.pack(fill="both",expand=True,pady=(8,12))
        self.log=tk.Text(log_frame,height=12,wrap="word",font=("Consolas",9),relief="flat",padx=10,pady=10,state="disabled")
        self.log.pack(fill="both",expand=True)
        btn=tk.Frame(shell,bg="#f6f7f9");btn.pack(fill="x")
        self.install_btn=ttk.Button(btn,text="Install / Upgrade",command=self.start_install);self.install_btn.pack(side="right")
        ttk.Button(btn,text="Close",command=self.destroy).pack(side="right",padx=(0,8))

    def browse(self):
        p=filedialog.askdirectory(title="Choose Local MoE Studio install folder")
        if p:self.install_path.set(p)

    def write_log(self,text):
        self.log.configure(state="normal");self.log.insert("end",text.rstrip()+"\n");self.log.see("end");self.log.configure(state="disabled")
        self.update_idletasks()

    def step(self,value,text):
        self.progress["value"]=value;self.status.set(text);self.write_log(text)

    def start_install(self):
        if self.busy:return
        self.busy=True;self.install_btn.configure(state="disabled")
        threading.Thread(target=self.install,daemon=True).start()

    def run(self,args,cwd=None):
        self.write_log("> "+" ".join(map(str,args)))
        p=subprocess.run(args,cwd=cwd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        if p.stdout:self.write_log(p.stdout)
        if p.returncode:raise RuntimeError("Command failed with exit code "+str(p.returncode))

    def download_source(self):
        req=urllib.request.Request(GITHUB_ZIP,headers={"User-Agent":"ThaiFDA-Installer"})
        with urllib.request.urlopen(req,timeout=45) as r:raw=r.read(30*1024*1024+1)
        if len(raw)>30*1024*1024:raise RuntimeError("Source archive is unexpectedly large")
        return raw

    def safe_extract(self,raw,dest):
        from io import BytesIO
        with zipfile.ZipFile(BytesIO(raw)) as z:
            root=dest.resolve()
            for info in z.infolist():
                target=(dest/info.filename).resolve()
                if root not in target.parents and target!=root:raise RuntimeError("Unsafe archive path")
            z.extractall(dest)

    def install_source(self,target):
        raw=self.download_source()
        with tempfile.TemporaryDirectory(prefix="lms_setup_") as td:
            td=Path(td);self.safe_extract(raw,td)
            roots=[p for p in td.iterdir() if p.is_dir()]
            if len(roots)!=1 or not (roots[0]/"src/localmoestudio").is_dir():raise RuntimeError("Downloaded source archive is invalid")
            source=roots[0]
            if target.exists() and (target/"src/localmoestudio").is_dir():
                backup=target/"_setup_backups"/time.strftime("%Y%m%d_%H%M%S");backup.mkdir(parents=True)
                for rel in ["src/localmoestudio","pyproject.toml","README.md","START_WINDOWS.bat","START_TEAM_HUB_WINDOWS.bat","START_THAI_FDA_TEAM_HUB_WINDOWS.bat"]:
                    src=target/rel
                    if not src.exists():continue
                    dst=backup/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copytree(src,dst) if src.is_dir() else shutil.copy2(src,dst)
                for rel in ["src/localmoestudio","pyproject.toml","README.md","START_WINDOWS.bat","START_TEAM_HUB_WINDOWS.bat","START_THAI_FDA_TEAM_HUB_WINDOWS.bat","docs"]:
                    src=source/rel
                    if not src.exists():continue
                    dst=target/rel
                    if src.is_dir():
                        if dst.exists():shutil.rmtree(dst)
                        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(src,dst)
                    else:
                        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
            else:
                if target.exists() and any(target.iterdir()):raise RuntimeError("Install folder is not empty and is not Local MoE Studio")
                target.mkdir(parents=True,exist_ok=True)
                for item in source.iterdir():
                    dst=target/item.name
                    shutil.copytree(item,dst) if item.is_dir() else shutil.copy2(item,dst)

    def install_data(self):
        if not DATA_PACK.is_file():raise RuntimeError("Bundled Thai FDA data pack is missing")
        local=Path(os.getenv("LOCALAPPDATA") or Path.home())/"LocalMoEStudio"
        dest=local/"thai_fda_precedent";dest.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="thai_fda_data_") as td:
            td=Path(td);self.safe_extract(DATA_PACK.read_bytes(),td)
            candidates=[td]+[p for p in td.iterdir() if p.is_dir()]
            src=next((p for p in candidates if (p/"retrieval_index.csv").is_file()),None)
            if src is None:raise RuntimeError("Bundled Thai FDA data pack is invalid")
            previous=dest.with_name(dest.name+".previous")
            if previous.exists():shutil.rmtree(previous)
            if dest.exists():dest.replace(previous)
            shutil.copytree(src,dest)

    def create_venv(self,target):
        venv=target/".venv"
        if not (venv/"Scripts/python.exe").is_file():
            attempts=[["py","-3","-m","venv",str(venv)],["python","-m","venv",str(venv)]]
            last=""
            for cmd in attempts:
                try:
                    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
                    if p.returncode==0:break
                    last=p.stdout or ""
                except OSError as exc:last=str(exc)
            else:raise RuntimeError("Python 3.10+ is required to create the Local MoE Studio environment. "+last)
        return venv/"Scripts/python.exe"

    def make_launchers(self,target,py):
        (target/"RUN_LOCAL_MOE_STUDIO.bat").write_text(
            '@echo off\nsetlocal\ncd /d "%~dp0"\nset "PYTHONPATH=%~dp0src"\n'
            f'"{py}" -m localmoestudio\nif errorlevel 1 pause\n',encoding="utf-8")
        (target/"RUN_THAI_FDA_TEAM_HUB.bat").write_text(
            '@echo off\nsetlocal\ncd /d "%~dp0"\nset "PYTHONPATH=%~dp0src"\n'
            f'start "" "{py}" -m localmoestudio.headless\n'
            'timeout /t 2 /nobreak >nul\nstart "" http://127.0.0.1:8765\n',encoding="utf-8")

    def create_shortcut(self,target,name,batch):
        desktop=Path(os.environ.get("USERPROFILE",str(Path.home())))/"Desktop"
        shortcut=desktop/(name+".lnk");target_bat=target/batch
        esc=lambda x:str(x).replace("'","''")
        ps=f"$W=New-Object -ComObject WScript.Shell;$S=$W.CreateShortcut('{esc(shortcut)}');$S.TargetPath='{esc(target_bat)}';$S.WorkingDirectory='{esc(target)}';$S.Save()"
        subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-Command",ps],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def smoke_test(self,target,py):
        env=os.environ.copy();env["PYTHONPATH"]=str(target/"src")
        code="from localmoestudio.thai_fda import status,analyze;s=status();print(s);assert s['available'];r=analyze('wound dressing with chlorhexidine, physical barrier action');print('precedents',len(r['precedents']));assert len(r['precedents'])>0"
        p=subprocess.run([str(py),"-c",code],cwd=target,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        self.write_log(p.stdout or "")
        if p.returncode:raise RuntimeError("Thai FDA runtime smoke test failed")

    def install(self):
        try:
            target=Path(self.install_path.get()).expanduser().resolve()
            self.after(0,self.step,5,"Downloading current Local MoE Studio source...")
            self.install_source(target)
            self.after(0,self.step,30,"Creating isolated Python environment...")
            py=self.create_venv(target)
            self.after(0,self.step,45,"Installing Local MoE Studio + Thai FDA dependencies...")
            self.run([str(py),"-m","pip","install","--upgrade","pip"],cwd=target)
            self.run([str(py),"-m","pip","install","-e",".[thai-fda]","pypdf"],cwd=target)
            self.after(0,self.step,70,"Installing bundled Thai FDA dataset...")
            self.install_data()
            self.after(0,self.step,82,"Creating launchers and shortcuts...")
            self.make_launchers(target,py)
            if self.create_shortcuts.get():
                self.create_shortcut(target,"Local MoE Studio","RUN_LOCAL_MOE_STUDIO.bat")
                self.create_shortcut(target,"Thai FDA Team Hub","RUN_THAI_FDA_TEAM_HUB.bat")
            self.after(0,self.step,92,"Running Thai FDA retrieval test...")
            self.smoke_test(target,py)
            self.after(0,self.step,100,"Installation completed successfully.")
            self.after(0,messagebox.showinfo,"Setup complete","Local MoE Studio - Thai FDA Edition is ready. Admin users can update datasets and software from Data & updates.")
            if self.launch_after.get():subprocess.Popen(["cmd","/c",str(target/"RUN_THAI_FDA_TEAM_HUB.bat")],cwd=target)
        except Exception as exc:
            self.after(0,self.write_log,"ERROR: "+str(exc));self.after(0,self.status.set,"Installation failed")
            self.after(0,messagebox.showerror,"Setup failed",str(exc))
        finally:
            self.busy=False;self.after(0,self.install_btn.configure,{"state":"normal"})

if __name__=="__main__":
    Installer().mainloop()
