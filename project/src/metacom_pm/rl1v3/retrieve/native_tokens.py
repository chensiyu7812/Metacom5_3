"""Frozen local tokenizer only. Never opens weights, downloads, or generates."""
from functools import lru_cache
from pathlib import Path
import json
from ..io import file_sha256,object_sha256
from ..render.v0 import messages

class NativeTokenizer:
    def __init__(self, model_path, asset_manifest):
        path=Path(model_path);audit=json.loads(Path(asset_manifest).read_text())
        names=('tokenizer.json','tokenizer_config.json','chat_template.jinja','config.json')
        hashes={}
        for name in names:
            f=path/name;matches=[r for r in audit['files'] if r.get('exists') and Path(r['path'])==f]
            if len(matches)!=1 or file_sha256(f)!=matches[0]['sha256']:
                raise ValueError('tokenizer/config differs from fixed asset audit: '+name)
            hashes[name]=matches[0]['sha256']
        from transformers import PreTrainedTokenizerFast
        config=json.loads((path/'tokenizer_config.json').read_text())
        self.tokenizer=PreTrainedTokenizerFast(tokenizer_file=str(path/'tokenizer.json'),
            chat_template=(path/'chat_template.jinja').read_text(),bos_token=config['bos_token'],eos_token=config['eos_token'])
        model=json.loads((path/'config.json').read_text())
        self.native_context_tokens=int(model.get('text_config',model)['max_position_embeddings'])
        self.identity='native-tokenizer:'+object_sha256(dict(files=hashes,enable_thinking=False,
            add_generation_prompt=True,add_special_tokens=False,adapter='PreTrainedTokenizerFast-v0.1'))
        self.file_hashes=hashes

    @lru_cache(maxsize=10000)
    def count(self,text):return len(self.tokenizer.encode(text,add_special_tokens=False))

    def prompt_tokens(self,prefix,readings):
        ids=self.tokenizer.apply_chat_template(messages(prefix,readings),tokenize=True,
            add_generation_prompt=True,enable_thinking=False)
        return len(ids)
