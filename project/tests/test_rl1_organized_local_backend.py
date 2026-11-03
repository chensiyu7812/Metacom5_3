"""Loading admission and interruption behavior; all hardware is mocked."""
import pytest
import torch

from metacom_pm.rl1 import local_backend, organized_local_backend as implementation
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.local_backend import LOCAL
from test_rl1_local_backend import setup


def production_fixture(tmp_path, monkeypatch, *, blocked=False, wrong=False):
    old, _, _, _, _, _, _ = setup(tmp_path/'fixture')
    root = tmp_path/'real'
    p = stamp({k:v for k,v in old.protocol.items() if k != 'identity'} | dict(
        scope=LOCAL, gpu_sampling_policy='last_xml', run_directory=str(root.resolve())))
    approval = dict(status='APPROVED', protocol_identity=p['identity'],
                    user_authorization_reference='SYNTHETIC TEST', operations=['local_generation','public_embedding'])
    calls = []
    class Guard:
        def __init__(self, uuid, runtime, root, *, latest_snapshot):
            calls.append(('guard', latest_snapshot))
        def check(self, **kwargs):
            calls.append(('check', kwargs))
            if blocked:
                raise RuntimeError('MOCK occupied')
    class G:
        manifest = {k:v for k,v in p['runtime'].items() if k != 'identity'}
        identity = 'wrong' if wrong else p['runtime']['identity']
    def loader(runtime):
        calls.append(('load', runtime)); torch.manual_seed(101)
        return G()
    monkeypatch.setattr(implementation, 'LocalGPUCheck', Guard)
    monkeypatch.setattr(implementation, 'check_static', lambda _: None)
    monkeypatch.setattr(local_backend, 'load_generator', loader)
    monkeypatch.setenv('HF_HUB_OFFLINE', '1'); monkeypatch.setenv('TRANSFORMERS_OFFLINE', '1')
    return implementation.OrganizedLocalBackend(p, root, approval=approval), calls


def test_latest_snapshot_and_one_load_preserve_rng_and_resident_check(tmp_path, monkeypatch):
    b, calls = production_fixture(tmp_path, monkeypatch)
    before = torch.get_rng_state().clone(); b.prepare(); b.prepare()
    assert torch.equal(before, torch.get_rng_state())
    assert ('guard', True) in calls and sum(x[0] == 'load' for x in calls) == 1
    assert 'own_pid' in calls[-1][1]
    again = implementation.OrganizedLocalBackend(b.protocol, b.root, approval=b.approval)
    with pytest.raises(ValueError, match='load envelope'):
        again.prepare()


def test_failed_admission_never_creates_load_or_generator_entry(tmp_path, monkeypatch):
    b, calls = production_fixture(tmp_path, monkeypatch, blocked=True)
    with pytest.raises(RuntimeError, match='occupied'):
        b.prepare()
    assert not list(b.root.glob('load_*.started.json')) and not any(x[0] == 'load' for x in calls)


@pytest.mark.parametrize('problem', ['directory', 'sampling'])
def test_scope_cannot_reset_directory_or_revert_sampling(tmp_path, monkeypatch, problem):
    b, calls = production_fixture(tmp_path, monkeypatch)
    if problem == 'directory':
        b.root = tmp_path/'different'
    else:
        b.protocol = stamp({k:v for k,v in b.protocol.items() if k != 'identity'} | dict(gpu_sampling_policy='first_csv'))
        b.approval['protocol_identity'] = b.protocol['identity']
    with pytest.raises(ValueError, match='sampling policy or fixed run directory'):
        b.prepare()
    assert not calls


def test_wrong_loaded_runtime_is_archived_and_cannot_reload(tmp_path, monkeypatch):
    b, calls = production_fixture(tmp_path, monkeypatch, wrong=True)
    with pytest.raises(ValueError, match='differs'):
        b.prepare()
    assert (b.root/'load_0000.observed.json').exists() and b.generator is None
    with pytest.raises(ValueError, match='load envelope'):
        b.prepare()
    assert sum(x[0] == 'load' for x in calls) == 1
