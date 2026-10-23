"""Blind P3 instrument and selective decryption, with no missing-to-zero path.

Encryption protects the handoff from accidental validation-label inspection;
the local researcher retains custody of the private key. It is not a security
boundary against someone deliberately bypassing this workflow.
"""
import base64
import json
from .evidence import evidence_turns
from .judge import _pairs
from .schema import digest

PROTOCOL = 'pm-rl1-p3-human-calibration-v1'
LABEL_KEYS = {'item_id', 'preference', 'risk_A', 'risk_B', 'quote_A', 'quote_B',
              'source_ids', 'reason', 'uncertainty'}


def strict_json(text):
    return json.loads(text, object_pairs_hook=_pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def validate_label(label, item, evidence):
    if set(label) != LABEL_KEYS or label['item_id'] != item['item_id']:
        raise ValueError('label fields or item identity mismatch')
    if label['preference'] not in ('A', 'B', 'tie', 'uncertain'):
        raise ValueError('missing or invalid preference')
    for side in ('A', 'B'):
        if label['risk_' + side] not in ('none_detected', 'local', 'severe', 'uncertain'):
            raise ValueError('missing or invalid risk')
        quote = label['quote_' + side]
        if not isinstance(quote, str) or (quote and quote not in item[side]):
            raise ValueError('response quote is not exact')
        if label['risk_' + side] in ('local', 'severe') and not quote.strip():
            raise ValueError('nonzero risk needs an exact response quote')
    for field in ('reason', 'uncertainty'):
        if not isinstance(label[field], str):
            raise ValueError('reason fields must be strings')
    if not label['reason'].strip():
        raise ValueError('a substantive reason is required')
    uncertain = 'uncertain' in (label['preference'], label['risk_A'], label['risk_B'])
    if uncertain and not label['uncertainty'].strip():
        raise ValueError('explain uncertainty; it is not zero risk')
    source_ids = label['source_ids']
    allowed = set(evidence_turns(evidence)) | {'ROLE', 'FULL_SOURCE'}
    if (not isinstance(source_ids, list) or any(not isinstance(s, str) for s in source_ids)
            or len(source_ids) != len(set(source_ids)) or not set(source_ids) <= allowed):
        raise ValueError('invalid source references')
    if any(label['risk_' + side] in ('local', 'severe') for side in ('A', 'B')) and not source_ids:
        raise ValueError('nonzero risk needs source references or ROLE/FULL_SOURCE')
    return dict(label)


def decrypt_item(envelope, private_key, *, packet_identity, form_identity):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if set(envelope) != {'item_id', 'wrapped_key', 'nonce', 'ciphertext'}:
        raise ValueError('invalid encrypted envelope')
    decode = lambda s: base64.b64decode(s, validate=True)
    key = private_key.decrypt(decode(envelope['wrapped_key']), padding.OAEP(
        mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    aad = (packet_identity + ':' + form_identity + ':' + envelope['item_id']).encode()
    plaintext = AESGCM(key).decrypt(decode(envelope['nonce']), decode(envelope['ciphertext']), aad)
    return strict_json(plaintext.decode())


def ingest_submission(submission, *, form, private_items, evidence_pool, private_key,
                      phase='development', measurement_freeze=None):
    expected_keys = {'protocol', 'packet_identity', 'form_identity', 'reviewer_kind',
                     'reviewer_identity', 'reviewer_details', 'items'}
    if set(submission) != expected_keys or submission['protocol'] != PROTOCOL:
        raise ValueError('instrument mismatch')
    for key in ('packet_identity', 'form_identity'):
        if submission[key] != form[key]:
            raise ValueError('source/form binding mismatch')
    if submission['reviewer_kind'] != 'individual_human':
        raise ValueError('this handoff requires an individual human; AI/consensus are separate provenance')
    if not isinstance(submission['reviewer_identity'], str) or not submission['reviewer_identity'].strip():
        raise ValueError('reviewer identity required')
    if not isinstance(submission['reviewer_details'], str):
        raise ValueError('reviewer details must be text')
    if phase not in ('development', 'validation'):
        raise ValueError('unknown intake phase; reserve has a separate activation gate')
    # Check the freeze before decrypting even one held-out item.
    if phase == 'validation':
        freeze = measurement_freeze or {}
        needed = {'packet_identity', 'scorer_protocol_identity', 'development_intake_sha256',
                  'qualification_contract_identity', 'semantic_revisions', 'status', 'form_identities'}
        if not needed <= set(freeze) or freeze.get('status') != 'FROZEN_BEFORE_VALIDATION_LABEL_ACCESS':
            raise ValueError('measurement freeze required before validation label access')
        if (freeze['packet_identity'] != form['packet_identity']
                or form['form_identity'] not in freeze['form_identities']
                or type(freeze['semantic_revisions']) is not int
                or freeze['semantic_revisions'] not in (0, 1)
                or not all(isinstance(freeze[k], str) and len(freeze[k]) == 64 for k in (
                    'scorer_protocol_identity', 'development_intake_sha256', 'qualification_contract_identity'))):
            raise ValueError('invalid measurement freeze binding')
    visible = {i['item_id']: i for i in form['items']}
    rows = submission['items']
    if (not isinstance(rows, list) or len(rows) != len(visible)
            or {r.get('item_id') for r in rows} != set(visible)):
        raise ValueError('missing, duplicated or replaced submitted items')
    labels = []
    sealed_ids = []
    for envelope in rows:
        item_id = envelope['item_id']
        if set(envelope) != {'item_id', 'wrapped_key', 'nonce', 'ciphertext'}:
            raise ValueError('invalid encrypted envelope')
        meta = private_items[item_id]
        if meta['group'] != phase:
            sealed_ids.append(item_id)
            continue
        label = decrypt_item(envelope, private_key,
            packet_identity=form['packet_identity'], form_identity=form['form_identity'])
        labels.append(validate_label(label, visible[item_id], evidence_pool[visible[item_id]['source_key']]))
    return dict(protocol=PROTOCOL, phase=phase, packet_identity=form['packet_identity'],
        form_identity=form['form_identity'], reviewer_kind=submission['reviewer_kind'],
        reviewer_identity=submission['reviewer_identity'], reviewer_details=submission['reviewer_details'],
        submission_identity=digest(submission), labels=labels, other_phase_decrypted=False,
        sealed_items=sealed_ids, reward_qualified=False)
