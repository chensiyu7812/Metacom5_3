# Public-source regression overlay

`source_overlay_20260929_v2.json` is the byte-identical, source-bound overlay
from the completed PM-RL1 development audit. It contains citations to the public
EvoEmo conversations and explicitly identified coordinator AI review, not
independent human gold. The regression tests bind it to checked-in source units.
It is not automatically loaded as runtime configuration or training data.

This fixture lets CI test the actual stale-fallback, as-of relationship and
role-play regressions without access to a private `outputs/` directory.
