"""Minimal chat presentation for Local MoE Studio (stdlib Tkinter only).

User prompts are right-aligned blue bubbles; assistant replies are uncluttered,
left-aligned rich text. Text is never interpreted as HTML or executable markup.
"""
from __future__ import annotations

import re
import tkinter as tk

CANVAS = '#FBFBFC'
USER_BG = '#E6F1FF'
TEXT = '#172333'
MUTED = '#6B7280'
BORDER = '#E5E7EB'


def configure(app):
    t = app.transcript
    app._chat_bubbles = []
    app._chat_widgets = []
    t.configure(bg=CANVAS, fg=TEXT, insertbackground=TEXT, font=('Segoe UI', 11),
                spacing1=3, spacing2=2, spacing3=8)
    t.tag_configure('message', font=('Segoe UI', 11), foreground=TEXT,
                    lmargin1=24, lmargin2=24, rmargin=24, spacing1=3, spacing3=4)
    t.tag_configure('heading', font=('Segoe UI', 13, 'bold'), foreground=TEXT,
                    lmargin1=24, lmargin2=24, rmargin=24, spacing1=15, spacing3=8)
    t.tag_configure('subheading', font=('Segoe UI', 11, 'bold'), foreground=TEXT,
                    lmargin1=24, lmargin2=24, rmargin=24, spacing1=12, spacing3=6)
    t.tag_configure('bullet', font=('Segoe UI', 11), foreground=TEXT,
                    lmargin1=32, lmargin2=44, rmargin=24, spacing1=3, spacing3=4)
    t.tag_configure('codeblock', font=('Consolas', 10), background='#EFF1F5',
                    foreground='#243247', lmargin1=30, lmargin2=30, rmargin=24,
                    spacing1=2, spacing3=2)
    t.tag_configure('bold', font=('Segoe UI', 11, 'bold'))
    t.tag_configure('inlinecode', font=('Consolas', 10), background='#EFF1F5')
    t.tag_configure('muted', foreground=MUTED, justify='center',
                    font=('Segoe UI', 11), spacing1=22, spacing3=8)
    t.tag_configure('error', foreground='#8B1E1E', background='#FEF1F1',
                    font=('Segoe UI', 11), lmargin1=24, lmargin2=24)
    t.bind('<Configure>', lambda event: _resize_bubbles(app, event.width), add='+')


def _viewport_width(t):
    width = int(t.winfo_width())
    return max(300, width if width > 10 else 900)


def _resize_bubbles(app, width=None):
    width = width or _viewport_width(app.transcript)
    for row, bubble in getattr(app, '_chat_bubbles', []):
        try:
            wrap = max(180, min(570, int(width * 0.58)))
            bubble.configure(wraplength=wrap)
            row.configure(width=max(220, width - 46),
                          height=bubble.winfo_reqheight() + 20)
        except tk.TclError:
            pass


def _insert_user(app, content):
    t = app.transcript
    message = str(content or '').strip()
    if not message:
        return
    row = tk.Frame(t, bg=CANVAS)
    label = tk.Label(row, text=message, bg=USER_BG, fg=TEXT,
                     font=('Segoe UI', 11), justify='left', anchor='w',
                     padx=20, pady=12, borderwidth=0)
    label.pack(side='right', anchor='e', padx=(15, 4), pady=7)
    row.pack_propagate(False)
    app._chat_bubbles.append((row, label))
    app._chat_widgets.append(row)
    _resize_bubbles(app)
    t.window_create('end', window=row)
    t.insert('end', '\n\n')


def parse_table(lines):
    """Parse pipe-delimited Markdown tables; return (headings, body) or None."""
    if len(lines) < 2:
        return None
    def cells(line):
        return [cell.strip() for cell in line.strip().strip('|').split('|')]
    columns = cells(lines[0])
    if not (2 <= len(columns) <= 8):
        return None
    marker = cells(lines[1])
    if len(marker) != len(columns) or not all(re.fullmatch(r':?-{3,}:?', x) for x in marker):
        return None
    rows = [cells(line) for line in lines[2:]]
    rows = [row for row in rows if len(row) == len(columns)]
    return columns, rows


def _insert_table(app, lines):
    t = app.transcript
    parsed = parse_table(lines)
    if parsed is None:
        for line in lines:
            t.insert('end', line + '\n', 'message')
        return
    header, rows = parsed
    outer = tk.Frame(t, bg=BORDER)
    width = _viewport_width(t)
    per_cell = max(80, min(250, int((width - 105) / len(header))))
    for col in range(len(header)):
        outer.grid_columnconfigure(col, weight=1, uniform='table')
    for i, row in enumerate([header] + rows[:100]):
        is_header = i == 0
        for j, value in enumerate(row):
            cell = tk.Label(outer, text=value.replace('**', ''), bg='#F2F4F7' if is_header else CANVAS,
                            fg=TEXT, font=('Segoe UI', 9, 'bold' if is_header else 'normal'),
                            justify='left', anchor='nw', wraplength=per_cell,
                            padx=10, pady=8)
            cell.grid(row=i, column=j, sticky='nsew', padx=(0, 1), pady=(0, 1))
    app._chat_widgets.append(outer)
    t.window_create('end', window=outer, padx=24, pady=5)
    t.insert('end', '\n')


_INLINE = re.compile(r'\*\*([^*\n]+)\*\*|`([^`\n]+)`')


def _insert_inline(t, line, base):
    start = 0
    for match in _INLINE.finditer(line):
        if match.start() > start:
            t.insert('end', line[start:match.start()], base)
        if match.group(1) is not None:
            t.insert('end', match.group(1), (base, 'bold'))
        else:
            t.insert('end', match.group(2), (base, 'inlinecode'))
        start = match.end()
    if start < len(line):
        t.insert('end', line[start:], base)
    t.insert('end', '\n')


def _insert_assistant(app, content):
    t = app.transcript
    lines = str(content or '').replace('\r\n', '\n').split('\n')
    i = 0
    fence = False
    while i < len(lines):
        raw = lines[i]
        stripped = raw.strip()
        if stripped.startswith('```'):
            fence = not fence
            i += 1
            continue
        if fence:
            t.insert('end', raw + '\n', 'codeblock')
            i += 1
            continue
        if stripped.startswith('|') and stripped.endswith('|'):
            chunk = []
            while i < len(lines) and lines[i].strip().startswith('|') and lines[i].strip().endswith('|'):
                chunk.append(lines[i])
                i += 1
            _insert_table(app, chunk)
            continue
        if not stripped:
            t.insert('end', '\n', 'message')
        elif stripped in ('---', '***', '___'):
            t.insert('end', '\n', 'message')
        elif stripped.startswith('#') and re.match(r'^#{1,6}\s', stripped):
            level = len(stripped) - len(stripped.lstrip('#'))
            _insert_inline(t, stripped[level:].strip(), 'heading' if level <= 2 else 'subheading')
        elif re.match(r'^([-*]|\d+[.)])\s+', stripped):
            content_line = re.sub(r'^([-*]|\d+[.)])\s+', '', stripped, count=1)
            _insert_inline(t, '- ' + content_line, 'bullet')
        else:
            _insert_inline(t, raw, 'message')
        i += 1
    t.insert('end', '\n', 'message')


def render_history(app, messages):
    t = app.transcript
    t.configure(state='normal')
    t.delete('1.0', 'end')
    for widget in getattr(app, '_chat_widgets', []):
        try:
            widget.destroy()
        except tk.TclError:
            pass
    app._chat_bubbles = []
    app._chat_widgets = []
    if not messages:
        t.insert('end', '\nStart a conversation with your local model.\n', 'muted')
    else:
        for message in messages:
            if message.get('role') == 'user':
                _insert_user(app, message.get('content', ''))
            elif message.get('role') == 'assistant':
                _insert_assistant(app, message.get('content', ''))
    t.configure(state='disabled')
    t.see('end')


def begin_request(app, user_text):
    t = app.transcript
    t.configure(state='normal')
    if not getattr(app, '_chat_streaming', False) and not app.history:
        t.delete('1.0', 'end')
    _insert_user(app, user_text)
    app._chat_streaming = True
    t.configure(state='disabled')
    t.see('end')


def append_token(app, part):
    t = app.transcript
    t.configure(state='normal')
    t.insert('end', part, 'message')
    t.configure(state='disabled')
    t.see('end')


def finish_request(app):
    app._chat_streaming = False
    render_history(app, app.history)


def show_error(app, error):
    app._chat_streaming = False
    t = app.transcript
    t.configure(state='normal')
    t.insert('end', '\nError: ' + str(error) + '\n', 'error')
    t.configure(state='disabled')
    t.see('end')