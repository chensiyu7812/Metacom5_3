# Paper 1 local research environment

The formal local runtime is a dedicated Python 3.11 Conda environment named
`metacom-paper1-py311`. It is separate from the hosted NVIDIA NIM Generator:
the environment runs Paper-1 code, tests, token accounting, and frozen
retriever encoders; the Generator itself remains the hosted
`meta/llama-3.1-8b-instruct` service.

Create or reconcile the environment from the repository root:

```bash
bash scripts/paper1/10_create_paper1_environment.sh
```

The bootstrap deliberately installs the CUDA 12.1 build of PyTorch before the
editable project. This avoids pip selecting a newer CUDA build that imports
successfully but is incompatible with the research host's NVIDIA driver.

The Conda directory and Hugging Face model files are local and must not be
committed. The repository instead stores:

- `paper1-py311.yml`: the Python/pip bootstrap;
- `requirements-paper1-py311.lock.txt`: exact resolved Python packages for
  the Linux x86_64 CUDA 12.1 research runtime;
- `scripts/paper1/10_attest_paper1_environment.py`: fail-closed package,
  import-boundary, tokenizer-byte, and encoder-forward verification.

The `official-rag` project extra pins only the retrieval core needed to
reproduce ES-MemEval's shipped RAG baseline path: `langchain-huggingface`,
`sentence-transformers`, `langchain-community`, and `faiss-cpu`. It does not
install or redefine the MP/MS/ME treatment pipeline, and it does not select an
RS retriever. `scripts/paper1/13_attest_official_rag_runtime.py` exercises this
path offline with a commit-addressed local BGE-M3 snapshot and synthetic
session documents; its output is engineering evidence, not a benchmark result.

The checked-in lock is for the local GPU research runtime. GitHub Actions
continues to install from `pyproject.toml` on a CPU runner to test the supported
dependency ranges and portability. Neither path unlocks formal outcomes.

The Llama tokenizer and BGE encoders are distinct artifacts. The tokenizer is
only a local text-to-token accounting/capping candidate; final cost uses NIM
usage fields, and provider-tokenizer parity remains an M2 freeze item.

Two BGE snapshots are attested without freezing either one: BGE-small is a
lightweight English RS challenger and environment smoke-test; BGE-M3 matches
the model identity used by ES-MemEval's official FAISS session-level Top-4 RAG
baseline and remains a separate typed-memory candidate. The official source
does not pin a Hub revision. The attested local M3 revision is a
commit-addressed Hub PR-130 `safetensors` snapshot whose
config/tokenizer/pooling bytes match the current official-model main snapshot;
weight equivalence to that unpinned main revision is not asserted. The
official-library parity probe verifies the actual SentenceTransformer pooling,
normalization, FAISS construction, and Top-4 API path for engineering use. It
does not freeze the local revision, establish retrieval quality, alter Typed
Memory, or assign BGE-M3 to RS.
