"""LLM-driven briefing generator.

Reads the tenant default chat model from `model_configs` (via `get_default_model_config`),
calls the LLM, and parses Markdown + action_items JSON.

Falls back to a deterministic rule-based summary on any failure.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SEC = 90
PROMPT_MAX_MESSAGES = 50

SYSTEM_PROMPT = (
    "You are a senior insurance business coach helping agents organise the "
    "customer notifications that require follow-up today. Respond in English "
    "with professional, concise, and actionable guidance."
)


def _truncate_messages(messages: list[dict]) -> list[dict]:
    if len(messages) <= PROMPT_MAX_MESSAGES:
        return messages
    p0 = [m for m in messages if m.get('priority') == 'P0']
    p1 = [m for m in messages if m.get('priority') == 'P1']
    p2 = [m for m in messages if m.get('priority') == 'P2']
    return p0 + p1[:30] + p2[:10]


def _build_user_prompt(messages: list[dict]) -> str:
    truncated = _truncate_messages(messages)
    omitted = len(messages) - len(truncated)
    payload = [
        {
            'priority': m.get('priority'),
            'category': m.get('category'),
            'notification_name': m.get('notification_name'),
            'policy_no': m.get('policy_no'),
            'customer_name': m.get('customer_name'),
            'product_name': m.get('product_name'),
            'business_type': m.get('business_type'),
            'template_summary': m.get('template_summary'),
            'classify_reason': m.get('classify_reason'),
            'deadline_at': m.get('deadline_at'),
            'occurred_at': m.get('occurred_at'),
            'source_message_id': m.get('id'),
        }
        for m in truncated
    ]
    note = f'\n\n({omitted} lower-priority P2 notifications were omitted.)' if omitted > 0 else ''
    return (
        f"The agent received {len(messages)} customer notifications today. "
        f"Generate a daily briefing using the requirements below.{note}\n\n"
        "1. **Start with** 'The three most important actions today' as a short "
        "ordered list using `1.`, `2.`, and `3.`.\n"
        "2. Then group key notifications by priority: P0 urgent, P1 important, "
        "and P2 routine.\n"
        "3. For every notification include:\n"
        "   - notification name, policy number, customer name, and deadline when available;\n"
        "   - a **recommended action** with one to three concrete steps;\n"
        "   - a **suggested call or message script** of two to four natural, "
        "friendly, professional English sentences.\n"
        "4. Follow this Markdown structure exactly:\n"
        "   - Represent each notification with an unordered list item and a bold name:\n"
        "     `- **Notification name**`\n"
        "   - Put details in unordered sub-items indented by two spaces:\n"
        "     `  - Policy number: HK-xxxx`\n"
        "     `  - Customer: Name`\n"
        "     `  - Deadline: YYYY/MM/DD HH:mm`\n"
        "     `  - Recommended action: ...`\n"
        "     `  - Suggested script: *\"Hello ..., ...\"*`\n"
        "   - Only the opening top-three section may use numbered items.\n"
        "   - Never flatten detail sub-items to the same level as the notification.\n"
        "5. Keep the result professional, concise, and actionable.\n"
        "6. Write the complete briefing in English.\n\n"
        "Notification list (JSON):\n"
        f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```\n\n"
        "Output requirement:\n"
        "- Return only the Markdown body; do not wrap it in a code block.\n"
    )


_PRIORITY_RE = re.compile(r'P([012])\b')
_ITEM_START_RE = re.compile(r'^\s*(?:-|\d+\.)\s+\*\*(.+?)\*\*')
_SUB_FIELD_RE = re.compile(r'^\s{2,}-\s*(.+?)[：:]\s*(.+)$')
_FIELD_MAP = {
    'policy number': 'policy_no', 'policy': 'policy_no',
    'customer name': 'customer_name', 'customer': 'customer_name',
    'deadline': 'deadline', 'due': 'deadline',
    'recommended action': 'action', 'next step': 'action', 'action': 'action',
}


def _extract_action_items(markdown: str) -> list[dict]:
    """Extract a structured preview list from LLM-generated markdown.

    Parses the expected structure:
        ### P0 Urgent follow-up (N items)
        - **notification_name**
          - Policy number: HK-xxxx
          - Customer: Name
          - Recommended action: action text
          - Suggested script: *"Script"*

    Returns up to 5 items, prioritized P0 > P1 > P2.
    Only used for the main page preview snippet; the markdown itself is the
    source of truth for detailed display in the modal.
    """
    items: list[dict] = []
    current_priority: str | None = None
    current: dict | None = None

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        # Detect priority section header (# ... P0 ... / ## ... P1 ...)
        if line.lstrip().startswith('#'):
            m = _PRIORITY_RE.search(line)
            if m:
                current_priority = f'P{m.group(1)}'
            if current:
                items.append(current)
                current = None
            continue

        # Top-level numbered item: "1. **notification_name**"
        m = _ITEM_START_RE.match(line)
        if m:
            if current:
                items.append(current)
            name = m.group(1).strip()
            current = {
                'priority': current_priority or 'P2',
                'notification_name': name,
                'policy_no': '',
                'customer_name': '',
                'action': name,  # Overridden when a recommended action is parsed.
                'deadline': '',
                'source_message_id': '',
            }
            continue

        # Sub-field: "  - Policy number: HK-xxxx"
        m = _SUB_FIELD_RE.match(line)
        if m and current:
            key = m.group(1).strip()
            value = m.group(2).strip()
            normalized_key = key.casefold()
            for prefix, field in _FIELD_MAP.items():
                if prefix in normalized_key:
                    current[field] = value
                    break

    if current:
        items.append(current)

    # Sort P0 > P1 > P2, keep first 5
    items.sort(key=lambda x: {'P0': 0, 'P1': 1, 'P2': 2}.get(x['priority'], 3))
    return items[:5]


async def _call_openai_compat(model_config: dict, system: str, user: str) -> str:
    from openai import AsyncOpenAI

    base_url = model_config.get('base_url') or None
    client = AsyncOpenAI(api_key=model_config['api_key'], base_url=base_url)
    resp = await asyncio.wait_for(
        client.chat.completions.create(
            model=model_config['model_id'],
            messages=[
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': user},
            ],
            max_tokens=model_config.get('max_tokens') or 4096,
            temperature=model_config.get('temperature') or 0.5,
        ),
        timeout=LLM_TIMEOUT_SEC,
    )
    return resp.choices[0].message.content or ''


async def _call_anthropic(model_config: dict, system: str, user: str) -> str:
    from anthropic import AsyncAnthropic

    base_url = model_config.get('base_url') or None
    client = AsyncAnthropic(api_key=model_config['api_key'], base_url=base_url)
    resp = await asyncio.wait_for(
        client.messages.create(
            model=model_config['model_id'],
            max_tokens=model_config.get('max_tokens') or 4096,
            temperature=model_config.get('temperature') or 0.5,
            system=system,
            messages=[{'role': 'user', 'content': user}],
        ),
        timeout=LLM_TIMEOUT_SEC,
    )
    parts = []
    for block in resp.content:
        text = getattr(block, 'text', None)
        if text:
            parts.append(text)
    return ''.join(parts)


def _build_fallback_summary(messages: list[dict]) -> tuple[str, list[dict]]:
    """Rule-based fallback when LLM is unavailable."""
    buckets: dict[str, list[dict]] = {'P0': [], 'P1': [], 'P2': []}
    for m in messages:
        buckets.setdefault(m.get('priority', 'P2'), []).append(m)

    lines = ["## Daily Business Briefing (Rule-Based)\n"]
    titles = {'P0': 'P0 Urgent Follow-up', 'P1': 'P1 Important Follow-up', 'P2': 'P2 Routine Notifications'}
    for prio in ('P0', 'P1', 'P2'):
        items = buckets.get(prio, [])
        if not items:
            continue
        lines.append(f"### {titles[prio]} ({len(items)} items)\n")
        for m in items:
            cust = m.get('customer_name') or m.get('customer_id') or 'Unknown customer'
            policy = m.get('policy_no') or '-'
            ddl = m.get('deadline_at')
            ddl_text = ''
            if ddl:
                try:
                    from datetime import datetime as _dt
                    dt = _dt.fromisoformat(str(ddl).replace('Z', '+00:00'))
                    ddl_text = f"  · Due {dt.strftime('%Y/%m/%d')}"
                except Exception:
                    ddl_text = f"  · Due {ddl}"
            lines.append(f"- **{m.get('notification_name')}** · {policy} · {cust}{ddl_text}")
        lines.append('')

    if not messages:
        lines.append('There are no new notifications today.')

    action_items: list[dict] = []
    for m in messages:
        if m.get('priority') in ('P0', 'P1'):
            action_items.append({
                'priority': m.get('priority'),
                'policy_no': m.get('policy_no') or '',
                'customer_name': m.get('customer_name') or '',
                'action': m.get('notification_name') or '',
                'deadline': m.get('deadline_at') or '',
                'source_message_id': m.get('id') or '',
                'suggested_script': '',
            })
    return '\n'.join(lines), action_items


async def generate_briefing(messages: list[dict]) -> dict:
    """Generate daily briefing for the given messages.

    Compliance warnings are NOT handled here — they are displayed separately
    by the frontend using api.briefing.compliance.get_compliance_warnings().

    Args:
        messages: list of inbox messages.

    Returns:
        {
            'summary_markdown': str,
            'action_items': list[dict],
            'model_id': str | None,
            'model_display_name': str,
        }
    """
    from admin.config_bridge import get_default_model_config

    model_config = await asyncio.to_thread(get_default_model_config)

    if not model_config or not model_config.get('api_key'):
        logger.warning('No default model configured, using fallback')
        md, items = _build_fallback_summary(messages)
        return {
            'summary_markdown': md,
            'action_items': items,
            'model_id': None,
            'model_display_name': 'fallback-rule-based',
        }

    if not messages:
        return {
            'summary_markdown': 'There are no new notifications today.',
            'action_items': [],
            'model_id': model_config.get('id'),
            'model_display_name': model_config.get('display_name') or 'default',
        }

    user_prompt = _build_user_prompt(messages)
    provider = (model_config.get('provider') or '').lower()

    if provider == 'anthropic':
        text = await _call_anthropic(model_config, SYSTEM_PROMPT, user_prompt)
    else:
        text = await _call_openai_compat(model_config, SYSTEM_PROMPT, user_prompt)
    markdown_body = text.strip()
    if not markdown_body:
        raise RuntimeError('Empty LLM output')
    # Extract preview action_items by parsing the markdown (single source of truth)
    action_items = _extract_action_items(markdown_body)
    return {
        'summary_markdown': markdown_body,
        'action_items': action_items,
        'model_id': model_config.get('id'),
        'model_display_name': model_config.get('display_name') or model_config.get('model_id'),
    }
