"""Rebuild a G0e request by lawful reads; old keys are never relabelled."""
from .. import contracts as K
from ..io import object_sha256

PROTOCOL = 'pmrl1v3-g0e-replay-binding-1'


def rebuild_from_replay(old_port, new_port, old_key):
    if old_port.prefix.runtime_sha256 != new_port.prefix.runtime_sha256:
        raise ValueError('prefix mismatch')
    for field in ('bank_version', 'index_version'):
        if old_port.identity[field] != new_port.identity[field]:
            raise ValueError('resource version mismatch: ' + field)
    old_trace = old_port.replay(old_key)
    if not isinstance(old_trace, K.ExecutionTrace):
        raise ValueError('old replay failed')
    views = ()
    for action, group, old_view in zip(old_key.ordered_path[:-1], old_key.acquired, old_trace.readings):
        result = new_port.read(action[4:], acquired=views)
        if not isinstance(result, K.ReadSuccess):
            raise ValueError('new lawful read failed: ' + result.reason)
        if result.record_ids != group or result.reading != old_view:
            raise ValueError('resource group or ReadingView changed')
        if new_port.verify_records(result.record_ids):
            raise ValueError('source verification failed')
        views += (result.reading,)
    packet = new_port.request_packet(views)
    if packet.key.acquired != old_key.acquired or packet.key.ordered_path != old_key.ordered_path:
        raise ValueError('subset or acquired groups changed')
    if packet.key.sha256 == old_key.sha256:
        raise ValueError('old replay identity was reused')
    packet.trace.verify_key(packet.key)
    return packet, dict(protocol=PROTOCOL, old_key_sha256=old_key.sha256,
        new_key_sha256=packet.key.sha256, request_sha256=packet.request_sha256,
        resource_groups_sha256=object_sha256(packet.key.acquired),
        readings_sha256=object_sha256(views), same_resource_groups=True, same_readings=True,
        changed_identity_fields=[k for k in old_port.identity if old_port.identity[k] != new_port.identity[k]],
        generation_calls=0, terminal_status='pending')
