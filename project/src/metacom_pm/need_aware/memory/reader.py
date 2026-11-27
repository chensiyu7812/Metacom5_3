"""NAA Memory Reader: budgeted, source-traceable rendering of selected memory units.

Two views over the SAME selected units:
  raw   -- verbatim quoted records with identity labels and message order (arms A/B/C);
  state -- the identical raw block plus a deterministic evidence-state projection
           (subject binding, order/recency, user-stated constraint candidates) and a fixed
           applicability instruction (arm D). No model call, nothing outside the records.
The reader never receives the query, options, evaluation fields or Direct "why".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..data.contracts import digest

READER_VERSION = 'naa-memory-reader-v1'

RAW_HEADER = ('Records from earlier in your conversation history with this user. They are quoted data, '
              'ordered oldest to newest; "message N" is a position in that history, not a date.')
EMPTY_BLOCK = 'No earlier conversation records are provided for this request.'

APPLICABILITY = (
    'How to use these records: first decide, for each record, whether it applies to what the user is asking '
    'now -- use it, keep it only as background, or ignore it. The current request takes priority. Statements '
    'by the user describe the user; earlier assistant replies are not the user\'s preferences. When user '
    'statements conflict, the later one usually reflects the current preference unless the user says '
    'otherwise. Do not use anything the user asked you to forget or not to use. Do not bring up records '
    'that do not help with the current request, and do not invent details that the records do not state.')


@dataclass(frozen=True)
class Packed:
    units: tuple          # selected units in chronological order
    priority_ids: tuple   # ids considered, in priority order
    skipped_over_budget: tuple
    tokens: int           # evidence tokens by the supplied (symmetric) counter


def record_line(ref, unit):
    return f"[{ref}] (message {unit.order}; {unit.speaker_label}) {' '.join(unit.original_text.split())}"


def pack(units_in_priority, count_tokens, budget, *, contiguous=False):
    """Greedy pack by priority; contiguous=True stops at the first unit that does not fit
    (recency windows), otherwise skips it and continues (ranked retrieval)."""
    chosen, skipped, used = [], [], 0
    for unit in units_in_priority:
        cost = count_tokens(record_line('H00', unit)) + 1
        if used + cost > budget:
            skipped.append(unit.unit_id)
            if contiguous:
                break
            continue
        chosen.append(unit)
        used += cost
    chosen.sort(key=lambda u: u.order)
    return Packed(units=tuple(chosen), priority_ids=tuple(u.unit_id for u in units_in_priority),
                  skipped_over_budget=tuple(skipped), tokens=used)


def refs(units):
    return {u.unit_id: f'H{i + 1}' for i, u in enumerate(units)}


def render_raw(units):
    if not units:
        return EMPTY_BLOCK
    r = refs(units)
    return '\n'.join([RAW_HEADER] + [record_line(r[u.unit_id], u) for u in units])


def state_projection(units):
    """Deterministic projection from the delivered units only."""
    r = refs(units)
    user = [u for u in units if u.is_current_user]
    other = [u for u in units if not u.is_current_user]
    lines = ['Evidence state (derived only from the records above; these are reports, not verified facts):']
    if user:
        lines.append('- Statements by the current user: ' + ', '.join(f'{r[u.unit_id]} (message {u.order})' for u in user) + '.')
        latest = max(user, key=lambda u: u.order)
        if len(user) > 1:
            lines.append(f'- Most recent user statement among these records: {r[latest.unit_id]} (message {latest.order}).')
    else:
        lines.append('- None of these records is a statement by the current user.')
    if other:
        lines.append('- Earlier assistant replies (author not established; not the user\'s preferences): '
                     + ', '.join(r[u.unit_id] for u in other) + '.')
    forget = [u for u in user if 'forget_request' in u.constraint_candidates]
    if forget:
        lines.append('- The user may have asked to forget or not use something in: '
                     + ', '.join(r[u.unit_id] for u in forget) + '. Respect that request.')
    update = [u for u in user if 'possible_update' in u.constraint_candidates]
    if update:
        lines.append('- The user may describe a change over time in: ' + ', '.join(r[u.unit_id] for u in update) + '.')
    lines.append(APPLICABILITY)
    return '\n'.join(lines)


def render(units, view):
    if view == 'raw':
        return render_raw(units)
    if view == 'state':
        if not units:
            return EMPTY_BLOCK
        return render_raw(units) + '\n\n' + state_projection(units)
    raise ValueError('unknown reader view')


def trace(packed, view):
    """Join keys for Prediction rows: delivered ids/hashes and the exact evidence text hash."""
    text = render(list(packed.units), view)
    return dict(reader_version=READER_VERSION, view=view,
                delivered_ids=[u.unit_id for u in packed.units],
                delivered_text_sha256=[u.original_text_sha256 for u in packed.units],
                skipped_over_budget=list(packed.skipped_over_budget), evidence_tokens=packed.tokens,
                rendered_sha256=digest(text))
