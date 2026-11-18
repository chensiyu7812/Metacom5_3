#!/bin/bash
# Same env + same command at several commits, sequentially, in ONE scratch worktree.
set -u
S=/tmp/claude-1004/-home-tokkio/ddd2d8a1-5810-45ac-a347-c2a4d4b35623/scratchpad
W=/opt/tokkio-data0/tokkio_runs/wsb_alltests_20261119/wt
PY=/tmp/claude-1004/-home-tokkio/4811e48b-52df-4031-b630-5f9e663990c0/scratchpad/venv311/bin/python
OUT=/opt/tokkio-data0/tokkio_runs/wsb_alltests_20261119/out
cd /home/tokkio/Metacom5_3-ws-b
[ -d "$W" ] || git worktree add -q --detach "$W" a9cf0cca || exit 1
$PY -c "import sys;print(sys.version)" > $OUT/env.txt
$PY -m pip freeze 2>/dev/null | sha256sum >> $OUT/env.txt
for c in "$@"; do
  cd "$W" && git checkout -q --detach "$c" && git clean -fdxq || exit 1
  cd "$W/project" || exit 1
  (date -u +%FT%TZ; git rev-parse HEAD) > $OUT/$c.start
  TMPDIR=/opt/tokkio-data0/tokkio_runs/wsb_alltests_20261119/tmp PYTHONNOUSERSITE=1 PYTHONPATH=src CUDA_VISIBLE_DEVICES= HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    $PY -m pytest -q -m "not gpu" tests -ra -o addopts= --junitxml=$OUT/$c.xml > $OUT/$c.log 2>&1
  echo "exit=$?" >> $OUT/$c.log
  date -u +%FT%TZ >> $OUT/$c.start
done
