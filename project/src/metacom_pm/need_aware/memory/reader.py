"""NAA Memory Reader: budgeted, source-traceable rendering of selected memory units.

Two views over the SAME selected units:
  raw   -- verbatim quoted records with identity labels and message order (arms A/B/C);
  state -- the identical raw block plus a deterministic evidence-state projection
           (who SPOKE, third-party cues, explicit change/forget candidates) and fixed usage
           guidance (arm D). No model call, nothing outside the delivered records.
v2: the projection never equates "spoken by the user" with "true of / preferred by the
user", never lets a later statement override an earlier one by order alone, and states
forget requests as constraints whose referent may be unknown.
The reader never receives the query, options, evaluation fields or Direct "why".
"""
from __future__ import annotations

from dataclasses import dataclass

from ..data.contracts import digest

READER_VERSION = 'naa-memory-reader-v2'

RAW_HEADER = ('Records from earlier in your conversation history with this user. They are quoted data, '
              'ordered oldest to newest; "message N" is a position in that history, not a date.')
EMPTY_BLOCK = 'No earlier conversation records are provided for this request.'

APPLICABILITY = (
    'How to use these records: decide for each record whether it helps with what the user asks now -- use it, '
    'keep it only as background, or ignore it. The current request takes priority. "Said by" names who spoke, '
    'not whom the statement is about: a user may describe another person (for example, "my mother loves fishing" '
    'is about the mother, not a preference of the user). Treat something as the user\'s own preference only when '
    'the user states it about themselves. Earlier assistant replies are neither the user\'s statements nor the '
    'user\'s preferences. A later statement replaces an earlier one only when it clearly concerns the same person, '
    'the same attribute and the same situation; otherwise both may still hold. If the user asked you to forget or '
    'not use something, do not rely on the information that request names; if it is unclear what it names, do not '
    'guess. Do not bring up records that do not help with the current request, and do not invent details that the '
    'records do not state.')


@dataclass(frozen=True)
class Packed:
    units: tuple          # selected units in chronological order
    priority_ids: tuple   # ids considered, in priority order
    skipped_over_budget: tuple
    tokens: int           # evidence tokens by the supplied (symmetric) counter


def record_line(ref, unit):
    return f"[{ref}] (message {unit.order}; said by: {unit.speaker_label}) {' '.join(unit.original_text.split())}"


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
    """Deterministic projection from the delivered units only (speaker facts + explicit cues)."""
    r = refs(units)
    user = [u for u in units if u.is_current_user]
    other = [u for u in units if not u.is_current_user]
    lines = ['Evidence notes (derived only from the records above; who spoke is known, everything else is a cue, '
             'not a verified fact):']
    if user:
        lines.append('- Said by the current user: ' + ', '.join(f'{r[u.unit_id]} (message {u.order})' for u in user)
                     + '. Whom each statement is about is not determined by these notes.')
    else:
        lines.append('- None of these records was said by the current user.')
    third = [u for u in user if u.third_party_mention]
    if third:
        lines.append('- These user statements mention another person, so they may describe that person rather than '
                     'the user: ' + ', '.join(r[u.unit_id] for u in third) + '.')
    if other:
        lines.append('- Earlier assistant replies (author not established; not the user\'s statements): '
                     + ', '.join(r[u.unit_id] for u in other) + '.')
    forget = [u for u in user if 'forget_request' in u.constraint_candidates]
    if forget:
        lines.append('- Requests by the user to forget or not use something: ' + ', '.join(r[u.unit_id] for u in forget)
                     + '. Each applies only to the information it names.')
    change = [u for u in user if 'explicit_change_statement' in u.constraint_candidates]
    if change:
        lines.append('- Statements of a change over time: ' + ', '.join(r[u.unit_id] for u in change)
                     + '. Such a statement updates an earlier record only for the same person, attribute and situation.')
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
