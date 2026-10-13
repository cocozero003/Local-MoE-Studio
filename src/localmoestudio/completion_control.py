"""Pure, bounded output-continuation rules for llama.cpp streaming chat.

Never continue on a normal end-of-sequence; only when the server explicitly
reports length, and at most MAX_AUTO_EXTRA_REQUESTS extra times per user turn.
"""

MAX_AUTO_EXTRA_REQUESTS = 2
CONTINUE_PROMPT = (
    'Continue the unfinished answer exactly where it stopped. '
    'Do not repeat earlier content, do not restart, and preserve formatting. '
    'Finish the original response.'
)


def finish_reason(chunk):
    if not isinstance(chunk, dict):
        return None
    choices = chunk.get('choices')
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    reason = first.get('finish_reason')
    return reason if isinstance(reason, str) and reason else None


def wants_auto_continue(reason, enabled, previous_extras):
    return (reason == 'length' and bool(enabled) and
            0 <= previous_extras < MAX_AUTO_EXTRA_REQUESTS)


def continuation_messages(previous_messages, generated_text):
    """Extend the last assistant message as conversation context, not as a new answer."""
    if not generated_text or not isinstance(previous_messages, list):
        raise ValueError('Cannot continue an empty response')
    return previous_messages + [
        {'role': 'assistant', 'content': generated_text},
        {'role': 'user', 'content': CONTINUE_PROMPT},
    ]


def append_answer(previous, addition):
    """Minimize avoidable whitespace while retaining exact text/structure."""
    if not previous:
        return addition
    if not addition:
        return previous
    # Only trim an exact repeated suffix/prefix; preserve code/Markdown otherwise.
    max_overlap = min(len(previous), len(addition), 500)
    for n in range(max_overlap, 11, -1):
        if previous[-n:] == addition[:n]:
            return previous + addition[n:]
    if previous[-1].isspace() or addition[0].isspace():
        return previous + addition
    return previous + ' ' + addition
