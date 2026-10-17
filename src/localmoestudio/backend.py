"""Local MoE Studio: standard-library Windows GUI for llama.cpp llama-server.
No telemetry, Docker, KoboldCpp, Ollama, or external Python packages.
"""
import json
import os
import queue
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from .performance import GenerationMetrics, append_history, tokenize_output_count
from .model_support import memory_flags
from .completion_control import (CONTINUE_PROMPT, finish_reason, wants_auto_continue,
                                 continuation_messages, append_answer)

ROOT = Path(__file__).resolve().parent
USER_DATA = Path(os.getenv('LOCALAPPDATA') or (Path.home() / '.localmoestudio')) / 'LocalMoEStudio'
USER_DATA.mkdir(parents=True, exist_ok=True)
SETTINGS = USER_DATA / 'settings.json'
DEFAULTS = {
    'server': '', 'model': '', 'context': '4096', 'gpu_layers': 'auto',
    'auto_refresh_catalog': True,
    'moe': 'all', 'moe_layers': '16', 'dense_ffn': '0', 'threads': 'auto', 'flash': True,
    'kv': 'q8_0', 'fit': True, 'fit_margin': '1024',
    'port': '8081', 'temp': '0.7', 'max_tokens': '1024',
    'system': 'You are a helpful private assistant. Reply in the language of the user.',
    'auto_continue': True, 'use_saved_chats': True
}

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Local MoE Studio - llama.cpp')
        self.geometry('1120x790')
        self.minsize(900, 650)
        self.process = None
        self.events = queue.Queue()
        self.history = []
        self.metrics = None
        self._finish_info = {}
        self._can_continue = False
        self.busy = False
        self.ready = False
        self.config_data = self.load_settings()
        self.vars = {key: tk.BooleanVar(value=value) if isinstance(value, bool)
                     else tk.StringVar(value=str(value))
                     for key, value in self.config_data.items()}
        self.make_ui()
        self.after(100, self.drain_events)
        self.protocol('WM_DELETE_WINDOW', self.close)

    def load_settings(self):
        values = DEFAULTS.copy()
        if SETTINGS.exists():
            try:
                data = json.loads(SETTINGS.read_text(encoding='utf-8'))
                values.update({k: v for k, v in data.items() if k in values})
            except (OSError, ValueError):
                pass
        return values

    def save_settings(self):
        values = {k: v.get() for k, v in self.vars.items()}
        temp = SETTINGS.with_suffix('.tmp')
        temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(temp, SETTINGS)
        self.status.set('Settings saved in your Windows user profile')

    def make_ui(self):
        self.status = tk.StringVar(value='Select llama-server.exe and a GGUF model.')
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=10, pady=10)
        self.setup_tab = ttk.Frame(nb, padding=12)
        self.chat_tab = ttk.Frame(nb, padding=12)
        self.logs_tab = ttk.Frame(nb, padding=12)
        nb.add(self.setup_tab, text='Model and Settings')
        nb.add(self.chat_tab, text='Local Chat')
        nb.add(self.logs_tab, text='Server Logs')

        frm = self.setup_tab
        frm.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(frm, text='Local MoE Studio', font=('Segoe UI', 18, 'bold')).grid(row=r, column=0, columnspan=3, sticky='w', pady=(0, 12))
        r += 1
        self.path_row(frm, r, 'llama-server.exe', 'server', executable=True); r += 1
        self.path_row(frm, r, 'GGUF model', 'model', executable=False); r += 1
        ttk.Separator(frm).grid(row=r, column=0, columnspan=3, sticky='ew', pady=10); r += 1
        ttk.Label(frm, text='GPU layers').grid(row=r, column=0, sticky='w', pady=4)
        ttk.Combobox(frm, textvariable=self.vars['gpu_layers'], values=['auto', 'all', '0', '10', '20', '30', '40', '99'], width=16).grid(row=r, column=1, sticky='w')
        ttk.Label(frm, text='auto is recommended for 6 GB VRAM').grid(row=r, column=2, sticky='w'); r += 1
        ttk.Label(frm, text='MoE expert placement').grid(row=r, column=0, sticky='w', pady=4)
        ttk.Combobox(frm, textvariable=self.vars['moe'], values=['all', 'first N layers', 'disabled'], state='readonly', width=20).grid(row=r, column=1, sticky='w')
        ttk.Label(frm, text='all = keep expert weights in system RAM').grid(row=r, column=2, sticky='w'); r += 1
        self.field(frm, r, 'CPU MoE first N layers', 'moe_layers', 'Used only if first N layers is selected'); r += 1
        self.field(frm, r, 'Context tokens', 'context', 'Start at 4096 to conserve memory'); r += 1
        self.field(frm, r, 'CPU threads', 'threads', 'auto or an integer'); r += 1
        self.field(frm, r, 'KV cache', 'kv', 'f16, q8_0 or q4_0', choices=['q8_0', 'f16', 'q4_0']); r += 1
        ttk.Checkbutton(frm, text='Flash Attention', variable=self.vars['flash']).grid(row=r, column=1, sticky='w', pady=4)
        ttk.Checkbutton(frm, text='Automatic memory fit', variable=self.vars['fit']).grid(row=r, column=2, sticky='w'); r += 1
        self.field(frm, r, 'Free VRAM target (MiB)', 'fit_margin', '1024 = reserve about 1 GB'); r += 1
        self.field(frm, r, 'Local API port', 'port', 'Only binds to 127.0.0.1'); r += 1
        ttk.Separator(frm).grid(row=r, column=0, columnspan=3, sticky='ew', pady=10); r += 1
        actions = ttk.Frame(frm)
        actions.grid(row=r, column=0, columnspan=3, sticky='w', pady=8)
        ttk.Button(actions, text='Start Server', command=self.start_server).pack(side='left', padx=(0,8))
        ttk.Button(actions, text='Stop Server', command=self.stop_server).pack(side='left', padx=(0,8))
        ttk.Button(actions, text='Save Settings', command=self.save_settings).pack(side='left', padx=(0,8))
        ttk.Button(actions, text='Show Launch Command', command=self.show_command).pack(side='left')
        r += 1
        ttk.Label(frm, text='Tip: Use the official llama.cpp CUDA-enabled Windows build. For MoE models, select all expert weights on CPU.', wraplength=850).grid(row=r, column=0, columnspan=3, sticky='w', pady=8)

        chat = self.chat_tab
        chat.columnconfigure(0, weight=1)
        chat.rowconfigure(2, weight=1)
        opt = ttk.Frame(chat)
        opt.grid(row=0, column=0, sticky='ew')
        ttk.Label(opt, text='Temperature').pack(side='left')
        ttk.Entry(opt, textvariable=self.vars['temp'], width=7).pack(side='left', padx=5)
        ttk.Label(opt, text='Max output tokens').pack(side='left', padx=(10,0))
        ttk.Entry(opt, textvariable=self.vars['max_tokens'], width=8).pack(side='left', padx=5)
        ttk.Button(opt, text='New Chat', command=self.new_chat).pack(side='right')
        ttk.Label(chat, text='System prompt').grid(row=1, column=0, sticky='w', pady=(10,2))
        system_entry = ttk.Entry(chat, textvariable=self.vars['system'])
        system_entry.grid(row=1, column=0, sticky='ew', padx=(96,0), pady=(10,2))
        self.transcript = ScrolledText(chat, wrap='word', state='disabled', font=('Segoe UI', 10))
        self.transcript.grid(row=2, column=0, sticky='nsew', pady=(6,8))
        compose = ttk.Frame(chat)
        compose.grid(row=3, column=0, sticky='ew')
        compose.columnconfigure(0, weight=1)
        self.prompt = tk.Text(compose, height=4, wrap='word', font=('Segoe UI', 10))
        self.prompt.grid(row=0, column=0, sticky='ew')
        self.prompt.bind('<Control-Return>', lambda e: self.send_message())
        ttk.Button(compose, text='Send (Ctrl+Enter)', command=self.send_message).grid(row=0, column=1, padx=(8,0))
        self.log_text = ScrolledText(self.logs_tab, wrap='word', font=('Consolas', 9), state='disabled')
        self.log_text.pack(fill='both', expand=True)
        ttk.Label(self, textvariable=self.status, anchor='w', relief='sunken').pack(side='bottom', fill='x')

    def path_row(self, frm, r, label, key, executable):
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky='w', pady=4, padx=(0,12))
        ttk.Entry(frm, textvariable=self.vars[key]).grid(row=r, column=1, sticky='ew', pady=4)
        def browse():
            patterns = [('Windows executable', '*.exe')] if executable else [('GGUF model', '*.gguf')]
            path = filedialog.askopenfilename(filetypes=patterns + [('All files', '*.*')])
            if path:
                self.vars[key].set(path)
        ttk.Button(frm, text='Browse', command=browse).grid(row=r, column=2, padx=8, sticky='w')

    def field(self, frm, r, label, key, hint, choices=None):
        ttk.Label(frm, text=label).grid(row=r, column=0, sticky='w', pady=4)
        if choices:
            widget = ttk.Combobox(frm, textvariable=self.vars[key], values=choices, state='readonly', width=18)
        else:
            widget = ttk.Entry(frm, textvariable=self.vars[key], width=20)
        widget.grid(row=r, column=1, sticky='w')
        ttk.Label(frm, text=hint).grid(row=r, column=2, sticky='w')

    def arguments(self):
        exe = Path(self.vars['server'].get().strip().strip('"'))
        model = Path(self.vars['model'].get().strip().strip('"'))
        if not exe.is_file():
            raise ValueError('Select the existing llama-server.exe file.')
        if not model.is_file() or model.suffix.lower() != '.gguf':
            raise ValueError('Select an existing .gguf model file.')
        context = int(self.vars['context'].get())
        port = int(self.vars['port'].get())
        margin = int(self.vars['fit_margin'].get())
        if not (512 <= context <= 262144 and 1024 <= port <= 65535 and 0 <= margin <= 32768):
            raise ValueError('Invalid context, port, or VRAM target.')
        ngl = self.vars['gpu_layers'].get().strip()
        if ngl not in ('auto', 'all'):
            if int(ngl) < 0:
                raise ValueError('GPU layers must be positive.')
        args = [str(exe), '-m', str(model), '--host', '127.0.0.1', '--port', str(port),
                '-c', str(context), '-ngl', ngl, '-fa', 'on' if self.vars['flash'].get() else 'off',
                '-ctk', self.vars['kv'].get(), '-ctv', self.vars['kv'].get(),
                '-fit', 'on' if self.vars['fit'].get() else 'off',
                '-fitt', str(margin)]
        args.extend(memory_flags({key: var.get() for key, var in self.vars.items()}, model, exe))
        threads = self.vars['threads'].get().strip()
        if threads != 'auto':
            if int(threads) < 1:
                raise ValueError('CPU thread count must be positive.')
            args += ['-t', threads]
        return args

    def show_command(self):
        try:
            cmd = subprocess.list2cmdline(self.arguments())
        except (ValueError, OSError) as ex:
            messagebox.showerror('Settings error', str(ex)); return
        w = tk.Toplevel(self)
        w.title('llama-server command preview')
        w.geometry('900x180')
        txt = ScrolledText(w, wrap='word')
        txt.pack(fill='both', expand=True)
        txt.insert('1.0', cmd)

    def start_server(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo('Already running', 'Stop the current server before starting a new one.'); return
        try:
            args = self.arguments()
            self.save_settings()
            self.process = subprocess.Popen(args, cwd=str(Path(args[0]).parent),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                text=True, encoding='utf-8', errors='replace', bufsize=1,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except (OSError, ValueError) as ex:
            messagebox.showerror('Cannot start server', str(ex)); return
        self.ready = False
        self.status.set('Starting llama.cpp: loading GGUF model (may take some time)...')
        threading.Thread(target=self.read_logs, args=(self.process,), daemon=True).start()
        threading.Thread(target=self.check_ready, args=(self.process,), daemon=True).start()

    def read_logs(self, process):
        try:
            for line in process.stdout:
                self.events.put(('log', line))
        except (OSError, ValueError) as ex:
            self.events.put(('log', 'Log reader ended: ' + str(ex) + '\n'))
        self.events.put(('stopped', 'Server process exited.'))

    def check_ready(self, process):
        url = self.endpoint('/health')
        while process.poll() is None:
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    if r.status == 200:
                        self.events.put(('ready', 'Server ready: local chat is available.'))
                        return
            except (urllib.error.URLError, TimeoutError, ValueError):
                pass
            time.sleep(1.5)

    def endpoint(self, route):
        return 'http://127.0.0.1:' + self.vars['port'].get().strip() + route

    def stop_server(self):
        proc = self.process
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
            self.status.set('Server stopped.')
        self.ready = False

    def append_text(self, widget, msg):
        widget.configure(state='normal')
        widget.insert('end', msg)
        widget.see('end')
        widget.configure(state='disabled')

    def new_chat(self):
        if self.busy:
            return
        self.history = []
        self.transcript.configure(state='normal')
        self.transcript.delete('1.0', 'end')
        self.transcript.configure(state='disabled')
        self.status.set('New chat started.')

    def send_message(self):
        if self.busy:
            return
        user_text = self.prompt.get('1.0', 'end').strip()
        if not user_text:
            return
        # A request to list saved questions is answered exactly from local
        # records, even when no inference model is loaded.
        if hasattr(self, '_answer_local_history_request'):
            if self._answer_local_history_request(user_text):
                return
        if not self.ready:
            messagebox.showwarning('Server not ready', 'Start the server and wait for a ready status.'); return
        try:
            temperature = float(self.vars['temp'].get())
            max_tokens = int(self.vars['max_tokens'].get())
            if not (0 <= temperature <= 2 and 1 <= max_tokens <= 32768):
                raise ValueError()
        except ValueError:
            messagebox.showerror('Invalid generation settings', 'Temperature 0-2; max tokens 1-32768.'); return
        self.prompt.delete('1.0', 'end')
        self._finish_info = {}
        self._can_continue = False
        self._set_continue_button(False)
        if hasattr(self, '_begin_chat_request_ui'):
            self._begin_chat_request_ui(user_text)
        else:
            self.append_text(self.transcript, '\nYOU\n' + user_text + '\n\nASSISTANT\n')
        self.busy = True
        self.status.set('Generating locally...')
        self.metrics = GenerationMetrics(self.vars['model'].get().strip())
        self.events.put(('perf_started', self.metrics.snapshot()))
        payload_history = ([{'role':'system','content':self.vars['system'].get()}]
                           if self.vars['system'].get().strip() else []) + self.history + [
                           {'role':'user','content':user_text}]
        if hasattr(self, '_saved_history_context'):
            try:
                archive_context = self._saved_history_context(user_text)
            except (OSError, ValueError):
                archive_context = ''
            if archive_context:
                payload_history.insert(0, {'role':'system','content':archive_context})
        threading.Thread(target=self.chat_request, args=(user_text, payload_history, temperature, max_tokens), daemon=True).start()

    def _set_continue_button(self, enabled):
        button = getattr(self, 'chat_continue_button', None)
        if button is not None:
            try:
                button.configure(state='normal' if enabled else 'disabled')
            except tk.TclError:
                pass

    def continue_answer(self):
        """Append a new generation to the last assistant turn, not a new user bubble."""
        if self.busy or not self.ready or not self._can_continue:
            return
        if not self.history or self.history[-1].get('role') != 'assistant':
            return
        try:
            temperature = float(self.vars['temp'].get())
            max_tokens = int(self.vars['max_tokens'].get())
            if not (0 <= temperature <= 2 and 1 <= max_tokens <= 32768):
                raise ValueError()
        except ValueError:
            messagebox.showerror('Invalid generation settings',
                                 'Temperature 0-2; max tokens 1-32768.')
            return
        self._can_continue = False
        self._set_continue_button(False)
        self._finish_info = {}
        self.busy = True
        self.status.set('Continuing the unfinished answer...')
        self.metrics = GenerationMetrics(self.vars['model'].get().strip())
        self.events.put(('perf_started', self.metrics.snapshot()))
        dialog = ([{'role': 'system', 'content': self.vars['system'].get()}]
                  if self.vars['system'].get().strip() else []) + self.history + [
                      {'role': 'user', 'content': CONTINUE_PROMPT}]
        threading.Thread(target=self.chat_request,
                         args=('', dialog, temperature, max_tokens, True),
                         daemon=True).start()

    def chat_request(self, user_text, messages, temp, max_tokens, continuing=False):
        """Stream responses, interpreting finish_reason and continuing at most twice.

        Each extra segment is requested only when llama.cpp explicitly reports
        finish_reason='length'. Stop and offer a manual continuation if the
        server returns another reason or exhausts the bounded extension budget.
        """
        text = ''
        metrics = self.metrics or GenerationMetrics(self.vars['model'].get().strip())
        dialog = list(messages)
        rounds = 0
        reason = None
        segment_timings = []
        segment_usage = []
        try:
            while True:
                base = {'messages': dialog, 'stream': True,
                        'temperature': temp, 'max_tokens': max_tokens}
                response = None
                for with_usage in (True, False):
                    payload = dict(base)
                    if with_usage:
                        payload['stream_options'] = {'include_usage': True}
                    req = urllib.request.Request(
                        self.endpoint('/v1/chat/completions'),
                        data=json.dumps(payload).encode('utf-8'),
                        headers={'Content-Type':'application/json'}, method='POST')
                    try:
                        response = urllib.request.urlopen(req, timeout=3600)
                        break
                    except urllib.error.HTTPError as exc:
                        if with_usage and exc.code == 400:
                            continue
                        raise
                reason = None
                part_text = ''
                last_update = 0.0
                # Per-segment backend timings are collected independently so
                # a later request cannot overwrite an earlier segment's values.
                metrics.timings = {}
                metrics.usage = {}
                with response:
                    for raw in response:
                        line = raw.decode('utf-8', errors='replace').strip()
                        if not line.startswith('data: '):
                            continue
                        value = line[6:]
                        if value == '[DONE]':
                            break
                        try:
                            chunk = json.loads(value)
                            if not isinstance(chunk, dict):
                                continue
                            observed_reason = finish_reason(chunk)
                            if observed_reason:
                                reason = observed_reason
                            part = metrics.ingest(chunk)
                        except (ValueError, TypeError, IndexError):
                            continue
                        if part:
                            part_text += part
                            self.events.put(('token', part))
                        now = time.perf_counter()
                        if part and now - last_update >= 0.3:
                            self.events.put(('perf_progress', metrics.snapshot(now)))
                            last_update = now
                text = append_answer(text, part_text)
                segment_timings.append(dict(metrics.timings))
                segment_usage.append(dict(metrics.usage))
                if not part_text or not wants_auto_continue(
                        reason, getattr(getattr(self, 'vars', {}).get('auto_continue'),
                                'get', lambda: False)(),
                        rounds):
                    break
                rounds += 1
                self.events.put(('chat_continuing', rounds))
                dialog = continuation_messages(dialog, part_text)

            # Aggregate reported token totals rather than claiming that the
            # last segment's tokens/sec represents the whole response.
            if len(segment_timings) > 1:
                counts = [float(t['predicted_n']) for t in segment_timings
                          if isinstance(t.get('predicted_n'), (int, float))]
                speeds = [float(t['predicted_per_second']) for t in segment_timings
                          if isinstance(t.get('predicted_per_second'), (int, float))
                          and t.get('predicted_per_second') > 0]
                # Never label a last-segment speed as a whole-response speed.
                metrics.timings.pop('predicted_per_second', None)
                metrics.timings.pop('predicted_n', None)
                metrics.usage.pop('completion_tokens', None)
                if len(counts) == len(segment_timings):
                    metrics.timings['predicted_n'] = sum(counts)
                    if len(speeds) == len(counts):
                        total_time = sum(n / speed for n, speed in zip(counts, speeds))
                        if total_time > 0:
                            metrics.timings['predicted_per_second'] = sum(counts) / total_time
                if not metrics.timings.get('predicted_n') and all(
                        isinstance(u.get('completion_tokens'), int) for u in segment_usage):
                    metrics.usage['completion_tokens'] = sum(
                        u['completion_tokens'] for u in segment_usage)
            completed_at = time.perf_counter()
            if (text and not metrics.timings.get('predicted_n')
                    and not metrics.usage.get('completion_tokens')):
                try:
                    count = tokenize_output_count(self.endpoint('/tokenize'), text)
                    if count is not None:
                        metrics.usage['completion_tokens'] = count
                except Exception:
                    pass
            self.events.put(('perf_done', metrics.finish(now=completed_at)))
            self.events.put(('chat_finish_state', {
                'reason': reason or 'unknown', 'segments': rounds + 1,
                'continuing': continuing, 'has_text': bool(text)}))
            self.events.put(('chat_done', (user_text, text, continuing)))
        except Exception as exc:
            self.events.put(('perf_done', metrics.finish(error=str(exc))))
            if text:
                self.events.put(('chat_finish_state', {
                    'reason': 'error', 'segments': rounds + 1,
                    'continuing': continuing, 'has_text': True,
                    'error': str(exc)}))
                self.events.put(('chat_done', (user_text, text, continuing)))
            else:
                self.events.put(('chat_error', str(exc)))

    def drain_events(self):
        try:
            while True:
                typ, data = self.events.get_nowait()
                if typ == 'log':
                    self.append_text(self.log_text, data)
                elif typ == 'ready':
                    self.ready = True
                    self.status.set(data)
                elif typ == 'stopped':
                    self.ready = False
                    self.status.set(data)
                elif typ == 'token':
                    if hasattr(self, '_append_assistant_token'):
                        self._append_assistant_token(data)
                    else:
                        self.append_text(self.transcript, data)
                elif typ in ('perf_started', 'perf_progress', 'perf_done'):
                    callback = getattr(self, '_on_performance_update', None)
                    if callback:
                        callback(data)
                    if typ == 'perf_done':
                        try:
                            append_history(USER_DATA / 'performance_history.jsonl', data)
                        except OSError:
                            pass
                elif typ == 'perf_hardware':
                    callback = getattr(self, '_on_performance_hardware', None)
                    if callback:
                        callback(data)
                elif typ == 'chat_continuing':
                    self.status.set('Output limit reached; continuing answer '
                                    f'(extension {data}/2)...')
                    if hasattr(self, 'perf_status'):
                        self.perf_status.set(f'Continuing response {data}/2')
                elif typ == 'chat_finish_state':
                    self._finish_info = data
                elif typ == 'chat_done':
                    if len(data) > 2 and data[2]:
                        if self.history and self.history[-1]['role'] == 'assistant':
                            self.history[-1]['content'] = append_answer(
                                self.history[-1]['content'], data[1])
                    else:
                        self.history.extend([{'role':'user', 'content':data[0]},
                                             {'role':'assistant', 'content':data[1]}])
                    if hasattr(self, '_finalize_chat_ui'):
                        self._finalize_chat_ui()
                    else:
                        self.append_text(self.transcript, '\n')
                    self.busy = False
                    info = self._finish_info
                    reason = info.get('reason')
                    incomplete = reason in ('length', 'unknown', 'error')
                    self._can_continue = bool(incomplete and info.get('has_text'))
                    self._set_continue_button(self._can_continue)
                    if reason == 'length':
                        notice = 'Output limit reached. Select Continue answer for more.'
                    elif reason == 'error':
                        notice = ('Generation interrupted: ' + str(info.get('error', ''))
                                  + '. Continue answer is available.')
                    elif reason == 'unknown':
                        notice = 'Response ended without a finish signal. Continue if incomplete.'
                    else:
                        notice = 'Response complete.'
                    self.status.set(notice)
                    if hasattr(self, 'perf_status'):
                        self.perf_status.set(notice)
                elif typ == 'chat_error':
                    if hasattr(self, '_chat_error_ui'):
                        self._chat_error_ui(data)
                    else:
                        self.append_text(self.transcript, '\n[Error: ' + data + ']\n')
                    self.busy = False
                    self._can_continue = False
                    self._set_continue_button(False)
                    self.status.set('Request failed; see chat error and logs.')
        except queue.Empty:
            pass
        self.after(100, self.drain_events)

    def close(self):
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno('Exit', 'Stop the running llama.cpp server and exit?'):
                return
            self.stop_server()
        try:
            self.save_settings()
        except OSError:
            pass
        self.destroy()

if __name__ == '__main__':
    Application().mainloop()
