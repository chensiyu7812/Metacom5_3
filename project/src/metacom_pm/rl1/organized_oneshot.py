"""Candidate ordered-program return regression, using only the initial view.

The menu/search procedure is supplied and frozen separately. This module never
uses a catalog or later observation to choose or discard a program. No claim of
exhaustive search or strong-baseline adequacy follows from a small supplied menu.
"""
import torch
from torch import nn
import heapq

from .organized_policy_interface import commit_program


def program_tensor(programs):
    if not programs:
        raise ValueError('nonempty program batch required')
    for p in programs:
        if (not p or any(type(a) is not int or a not in range(5) for a in p)
                or p[-1] != 0 or 0 in p[:-1]):
            raise ValueError('complete ordered GET program ending in STOP required')
    x=torch.full((len(programs),max(map(len,programs))),-1,dtype=torch.long)
    for i,p in enumerate(programs):x[i,:len(p)]=torch.tensor(p)
    return x


class ProgramReturnModel(nn.Module):
    """Variable-length program GRU + original-width MLP; development candidate."""
    def __init__(self,feature_dimension):
        super().__init__()
        self.feature_dimension=feature_dimension
        self.program=nn.GRU(5,32,batch_first=True)
        self.body=nn.Sequential(nn.Linear(feature_dimension+32,128),nn.Tanh(),
            nn.Linear(128,128),nn.Tanh(),nn.Linear(128,128),nn.Tanh())
        self.return_head=nn.Linear(128,1)

    def forward(self,features,programs):
        if (features.ndim!=2 or features.shape[-1]!=self.feature_dimension or programs.ndim!=2
                or programs.shape[0]!=features.shape[0] or programs.dtype!=torch.long
                or not torch.isfinite(features).all()):
            raise ValueError('initial public features and padded ordered programs required')
        lengths=(programs>=0).sum(1)
        if not (lengths>0).all() or (programs < -1).any() or (programs > 4).any():
            raise ValueError('invalid program tokens')
        positions=torch.arange(programs.shape[1],device=programs.device)[None,:]
        if (not torch.equal(programs>=0,positions<lengths[:,None])
                or not (programs.gather(1,(lengths-1)[:,None])==0).all()
                or ((programs==0)&(positions<lengths[:,None]-1)).any()):
            raise ValueError('padding or STOP in the middle of a program')
        encoded=torch.nn.functional.one_hot(programs.clamp_min(0),5).to(features.dtype)
        packed=nn.utils.rnn.pack_padded_sequence(encoded,lengths.cpu(),batch_first=True,enforce_sorted=False)
        _,hidden=self.program(packed)
        return self.return_head(self.body(torch.cat((features,hidden[0]),dim=-1))).squeeze(-1)

    @torch.no_grad()
    def choose(self,initial,programs,*,view,interface_identity):
        if view.no_text:
            raise ValueError('OneShot uses the initial full public view')
        committed=[commit_program(initial,p,interface_identity=interface_identity) for p in programs]
        if len({p.identity for p in committed})!=len(committed) or not any(p.actions==(0,) for p in committed):
            raise ValueError('distinct precommitted programs including OFF required')
        # Do not run future retrieval to construct a privileged feasibility mask.
        for p in committed:
            if any(p.actions.count(a)>initial.remaining_items[a-1] for a in range(1,5)):
                raise ValueError('program exceeds initial public inventory')
        x,_=view.sequential(initial)
        device=next(self.parameters()).device
        features=torch.tensor(x,dtype=torch.float32,device=device).expand(len(committed),-1)
        tokens=program_tensor([list(p.actions) for p in committed]).to(device)
        values=self(features,tokens)
        if not torch.isfinite(values).all():raise ValueError('nonfinite predicted returns')
        return committed[int(values.argmax())]

    @torch.no_grad()
    def search(self, initial, *, view, interface_identity, max_expansions):
        """Initial-only best-first program search with explicit compute budget.

        STOP at a prefix supplies its learned ranking heuristic, not an upper
        bound on longer programs. All head orders/lengths within public stock
        are in the search domain; finite search is approximate and can miss
        complementary programs. No future retrieval or feasibility oracle is
        consulted. Native-capacity failures are handled by the declared program
        executor, never by secretly replaying candidates to select a winner.
        """
        if type(max_expansions) is not int or max_expansions < 1 or view.no_text:
            raise ValueError('explicit positive search budget and initial public view required')
        off = commit_program(initial, [0], interface_identity=interface_identity)
        features, _ = view.sequential(initial)
        device = next(self.parameters()).device
        def score(programs):
            x = torch.tensor(features, dtype=torch.float32, device=device).expand(len(programs), -1)
            values = self(x, program_tensor(programs).to(device))
            if not torch.isfinite(values).all():
                raise ValueError('nonfinite predicted program return')
            return values.cpu().tolist()
        best_actions, best_value = (0,), score([(0,)])[0]
        frontier = [(-best_value, ())]
        expanded, evaluated, depth = 0, 1, 0
        while frontier and expanded < max_expansions:
            _, prefix = heapq.heappop(frontier)
            children = [prefix+(a,) for a in range(1, 5)
                        if prefix.count(a) < initial.remaining_items[a-1]
                        and (prefix or initial.action_mask[a])]
            expanded += 1
            if not children:
                continue
            values = score([p+(0,) for p in children])
            evaluated += len(children)
            for p, value in zip(children, values):
                actions = p+(0,)
                if value > best_value or (value == best_value and (len(actions), actions) < (len(best_actions), best_actions)):
                    best_actions, best_value = actions, value
                depth = max(depth, len(p))
                if any(p.count(a) < initial.remaining_items[a-1] for a in range(1,5)):
                    heapq.heappush(frontier, (-value, p))
        chosen = off if best_actions == (0,) else commit_program(initial, best_actions, interface_identity=interface_identity)
        return chosen, dict(search='initial-only best-first using predicted STOP-prefix return',
            max_expansions=max_expansions, expanded=expanded, evaluated_programs=evaluated,
            deepest_GETs=depth, frontier_exhausted=not frontier, predicted_return=best_value,
            future_observations_read=0, environment_GET_cap=None,
            globally_optimal_guaranteed=False, formal_search_budget_frozen=False)
