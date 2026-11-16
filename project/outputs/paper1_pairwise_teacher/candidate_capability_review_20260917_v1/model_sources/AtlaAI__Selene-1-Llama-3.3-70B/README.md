---
base_model:
- meta-llama/Llama-3.3-70B-Instruct
library_name: transformers
language:
- en
- de
- fr
- it
- pt
- es
pipeline_tag: text-generation
tags:
- llama
- atla
- evaluation
- llm-as-a-judge
- meta
- conversational
- lm-judge
license: llama3.3
---

<p align="center">
  <picture>
    <source 
      srcset="https://atla-ai.notion.site/image/https%3A%2F%2Fprod-files-secure.s3.us-west-2.amazonaws.com%2Ff08e6e70-73af-4363-9621-90e906b92ebc%2F1bfb4316-1ce6-40a0-800c-253739cfcdeb%2Fatla_white3x.svg?table=block&id=17c309d1-7745-80f9-8f60-e755409acd8d&spaceId=f08e6e70-73af-4363-9621-90e906b92ebc&userId=&cache=v2"
      media="(prefers-color-scheme: dark)"
      width="200"
    />
    <source 
      srcset="https://atla-ai.notion.site/image/attachment%3A230448e8-921f-45df-b2af-a3158b6c04cd%3Aatla_black2x.png?table=block&id=188309d1-7745-805c-87e4-c39ca54d598d&spaceId=f08e6e70-73af-4363-9621-90e906b92ebc&width=2000&userId=&cache=v2"
      media="(prefers-color-scheme: light)"
      width="200"
    />
    <img 
      src="https://atla-ai.notion.site/image/attachment%3A230448e8-921f-45df-b2af-a3158b6c04cd%3Aatla_black2x.png?table=block&id=188309d1-7745-805c-87e4-c39ca54d598d&spaceId=f08e6e70-73af-4363-9621-90e906b92ebc&width=2000&userId=&cache=v2"
      width="200"
    />
  </picture>
</p>
<p align="center">
    🌐 <a href="https://www.atla-ai.com/post/selene-1">Blogpost</a> | 
    📄 <a href="https://arxiv.org/abs/2501.17195v1">Technical report</a> | 
    💻 <a href="https://github.com/atla-ai/selene-mini">Cookbooks</a> | 
    👀 <a href="https://www.atla-ai.com/" style="background-image: linear-gradient(to right, red, orange, yellow, green, blue, indigo, violet); -webkit-background-clip: text; color: transparent; animation: rainbow 5s ease infinite; text-decoration: underline; text-decoration-color: currentColor;">Atla agent evals</a>
</p>

<style>
@keyframes rainbow {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
}
</style>

# Model Summary

Atla Selene 1 is a **state-of-the-art large language model-as-a-judge**. Selene 1 achieves **frontier-level performance across 11 evaluation benchmarks**, outperforming OpenAI's o1, o3-mini, and GPT-4o, Anthropic's Claude 3.5 Sonnet, Meta's Llama 3.3, and DeepSeek's R1.  

<p align="left">
  <img src="https://cdn-uploads.huggingface.co/production/uploads/633c4fb100732349209f2aad/6UmMz9Pyaa3yEx8z-sMA6.png" width="800" alt="Centered image">
</p>

Selene 1 was post-trained from Llama-3.3-70B on a combined SFT+DPO objective using the same recipe as [Selene Mini](https://arxiv.org/abs/2501.17195v1).
Trained across a wide range of evaluation tasks and scoring criteria, Selene 1 **outperforms frontier models across 11 benchmarks covering three different types of tasks:**

- Absolute scoring, e.g. "Evaluate the harmlessness of this response on a scale of 1-5"
- Classification, e.g. "Does this response address the user query? Answer Yes or No."
- Pairwise preference. e.g. "Which of the following responses is more logically consistent - A or B?"

Selene 1 particularly excels at capturing human judgements on **nuanced, complex real-world evaluations**, as evidenced by its state-of-the-art performance on FLASK, MT-Bench, RewardBench and Auto-J.

<p align="left">
  <img src="https://cdn-uploads.huggingface.co/production/uploads/633c4fb100732349209f2aad/LFvmTz61HuqJxg7bKz2Dc.png" width="800" alt="Centered image">
</p>

If you're interested in evaluating more complex systems like LLM agents, learn more [here](https://calendly.com/atla-team/agents-demo).

## Model Details

- **Developed by:** [Atla](https://www.atla-ai.com)
- **Model type:** Post-trained from Llama-3.3-70B
- **Parameters:** 70 billion
- **Language(s) (NLP):** Primarily English but supports German, French, Italian, Portuguese, Hindi, Spanish, Thai
- **Context length** 128K

## Model Use

Selene 1 can be used as a **general-purpose evaluation model**. It supports different inputs & scoring scales, generates structured evaluation outputs, and provides qualitative critiques with reasoning. The model is highly steerable with customizable evaluation criteria and can evaluate responses with or without reference responses.

Try our cookbooks to get started with two popular use cases below:

- [Absolute scoring](https://colab.research.google.com/github/atla-ai/selene-mini/blob/main/cookbooks/HF_Quickstart_Absolute_Scoring.ipynb)
- [RAG hallucination](https://colab.research.google.com/github/atla-ai/selene-mini/blob/main/cookbooks/HF_Quickstart_Hallucination.ipynb)

To achieve best results, **we provide the prompts we used for training [here](https://github.com/atla-ai/selene-mini/tree/main/prompt-templates).**

Remember to apply the conversation template of Llama 3 - not doing so might lead to unexpected behaviors. You can find the conversation class at this [link](https://github.com/lm-sys/FastChat/blob/main/fastchat/conversation.py) or you can refer to the below code that will apply it.

## Quickstart (HF Transformers):

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
device = "cuda" # the device to load the model onto

model_id = "AtlaAI/Selene-1-Llama-3.3-70B"

model = AutoModelForCausalLM.from_pretrained(model_id, device_map="auto")
tokenizer = AutoTokenizer.from_pretrained(model_id)

prompt = "I heard you can evaluate my responses?" # replace with your prompt / we provide prompt templates used during training at github.com/atla-ai/selene-mini/tree/main/prompt-templates
messages = [{"role": "user", "content": prompt}]
text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
model_inputs = tokenizer([text], return_tensors="pt").to(device)

generated_ids = model.generate(model_inputs.input_ids, max_new_tokens=512, do_sample=True)
generated_ids = [output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)]

response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
```

## Contact

support@atla-ai.com
<br>
You can also join our [Discord](https://discord.com/invite/qFCMgkGwUK)!

## Citation

If you are using the model, cite using

```
@misc{alexandru2025atlaseleneminigeneral,
      title={Atla Selene Mini: A General Purpose Evaluation Model},
      author={Andrei Alexandru and Antonia Calvi and Henry Broomfield and Jackson Golden and Kyle Dai and Mathias Leys and Maurice Burger and Max Bartolo and Roman Engeler and Sashank Pisupati and Toby Drane and Young Sun Park},
      year={2025},
      eprint={2501.17195},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2501.17195},
}
```