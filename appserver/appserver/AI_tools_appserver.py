# AI_tools_appserver.py
# Appserver-local implementation of the Claude API helpers needed by chatbot.py.
# Kept separate from /home/flask/blog/AI_tools.py because appserver and webserver
# run on different machines in staging/production - no shared filesystem.

import logging
import requests
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
import config

log = logging.getLogger("AI_tools_appserver")

# ------------------------------------------------------------------
# Anthropic (Claude) model IDs
# ------------------------------------------------------------------
ANTHROPIC_API_KEY = config.anthropic_token
ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'

CLAUDE_OPUS_46   = 'claude-opus-4-6'           # most capable
CLAUDE_SONNET_46 = 'claude-sonnet-4-6'         # recommended default - strong + fast
CLAUDE_HAIKU_45  = 'claude-haiku-4-5-20251001' # fast + cheap
CLAUDE_HAIKU_35  = 'claude-3-5-haiku-20241022' # very cheap

CLAUDE_MODEL_DEFAULT = CLAUDE_SONNET_46


class AnthropicAPIError(Exception):
    pass


def _prepare_system(system, cache_system=False, cache_ttl='5m'):
    """Normalize a string or ordered text blocks for Anthropic's system field.

    A block supplied with ``cache_control`` is an explicit cache breakpoint.  This lets Tara cache
    its stable behavioral prefix while leaving topic-selected knowledge and live screen data after
    the breakpoint.  Legacy string callers retain the old whole-system caching behavior.
    """
    if not system:
        return None

    if isinstance(system, str):
        if not cache_system:
            return system
        control = {'type': 'ephemeral'}
        if cache_ttl == '1h':
            control['ttl'] = '1h'
        return [{'type': 'text', 'text': system, 'cache_control': control}]

    if not isinstance(system, (list, tuple)):
        raise TypeError('system must be a string or an ordered list of text blocks')

    blocks = []
    has_breakpoint = False
    for item in system:
        block = {'type': 'text', 'text': item} if isinstance(item, str) else dict(item)
        if block.get('type') != 'text' or not isinstance(block.get('text'), str):
            raise TypeError('system blocks must contain type=text and string text')
        if cache_system and block.get('cache_control'):
            control = dict(block['cache_control'])
            control.setdefault('type', 'ephemeral')
            if cache_ttl == '1h':
                control['ttl'] = '1h'
            else:
                # Five minutes is Anthropic's default.  Remove a stale one-hour marker if a
                # reusable block list is sent through the five-minute path.
                control.pop('ttl', None)
            block['cache_control'] = control
            has_breakpoint = True
        elif not cache_system:
            block.pop('cache_control', None)
        blocks.append(block)

    # Backward-compatible behavior for block-list callers that did not mark a breakpoint.
    if cache_system and blocks and not has_breakpoint:
        control = {'type': 'ephemeral'}
        if cache_ttl == '1h':
            control['ttl'] = '1h'
        blocks[-1]['cache_control'] = control
    return blocks


def send_claude_messages(messages, model=CLAUDE_MODEL_DEFAULT, system=None,
                         max_tokens=4096, temperature=0.0, timeout=(15, 100),
                         cache_system=False, cache_ttl='5m', tools=None, return_raw=False):
    """
    Send a multi-turn conversation to Claude.
    `messages` is a list of {'role': 'user'|'assistant', 'content': str|blocks} dicts.
    The system prompt (if any) goes in the separate `system` parameter. It may be a string or an
    ordered list of Anthropic text blocks; a list can put ``cache_control`` on the last stable block
    and leave changing suffix blocks uncached.
    Set cache_system=True to enable Anthropic prompt caching on marked system blocks.
      cache_ttl='5m' - $1.25/MTok write, resets on every hit (good for active users)
      cache_ttl='1h' - $2.00/MTok write, survives 1hr inactivity (good for sporadic use)
    Cache hits are $0.10/MTok regardless of TTL - 10x cheaper than base input.

    `tools` (optional): a list of Anthropic tool schemas. When set, the model may emit
    tool_use blocks; the caller MUST run the tool loop and so MUST pass return_raw=True to
    receive the FULL response dict (stop_reason + content blocks) rather than just text.
    `return_raw=True`: return the full response.json() instead of content[0].text. Required
    whenever `tools` is used (content[0] may be a tool_use block, not text).
    """
    headers = {
        'x-api-key':         ANTHROPIC_API_KEY,
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type':      'application/json',
    }
    if cache_system:
        headers['anthropic-beta'] = 'prompt-caching-2024-07-31'

    payload = {
        'model':      model,
        'max_tokens': max_tokens,
        'messages':   messages,
    }
    prepared_system = _prepare_system(system, cache_system=cache_system, cache_ttl=cache_ttl)
    if prepared_system:
        payload['system'] = prepared_system
    if temperature != 0.0:
        payload['temperature'] = temperature
    if tools:
        payload['tools'] = tools

    resp = requests.post(ANTHROPIC_API_URL, headers=headers,
                         json=payload, timeout=timeout)
    if resp.status_code != 200:
        # Log the provider's body server-side only; never surface it (it can carry request
        # echoes / rate-limit detail). Callers raise/return a generic message.
        log.warning("Anthropic API %s: %s", resp.status_code, resp.text[:500])
        raise AnthropicAPIError(f'HTTP {resp.status_code}')
    data = resp.json()
    usage = data.get('usage') if isinstance(data, dict) else None
    if isinstance(usage, dict):
        log.info(
            "Anthropic usage model=%s input=%s cache_create=%s cache_read=%s output=%s",
            model,
            usage.get('input_tokens', 0),
            usage.get('cache_creation_input_tokens', 0),
            usage.get('cache_read_input_tokens', 0),
            usage.get('output_tokens', 0),
        )
    if return_raw:
        return data
    return data['content'][0]['text']
