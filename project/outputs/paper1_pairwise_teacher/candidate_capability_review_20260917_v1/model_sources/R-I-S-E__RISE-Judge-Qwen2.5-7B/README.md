---
base_model:
- Qwen/Qwen2.5-7B
---
## Introduction

[RISE-Judge-Qwen2-32B](https://huggingface.co/R-I-S-E/RISE-Judge-Qwen2.5-32B) and [RISE-Judge-Qwen2-7B](https://huggingface.co/R-I-S-E/RISE-Judge-Qwen2.5-7B) (**R**einforcement learning for **I**ncremental **S**elf-**E**volution) are outstanding generative judge models built on Qwen2.5-32B-Base and Qwen2.5-7B-Base. 

RISE-Judge-Qwen2-32B and RISE-Judge-Qwen2-7B are trained from preference data. We propose a two-stage training framework, SFT Warm-Up and DPO Enhancement. In the first stage, we prompted GPT-4o to generate step by step judgment towards questions and answer pairs in dataset. We check the quality of the judgment by comparing judge result with groundtruth preference, and change the order if answer pairs to avoid position bias. In the DPO stage, we choose those questions and answer pairs that can't be correctly judged in stage 1, and let our SFT model get in stage 1 to give out judgment. We collect judgment pairs according to the correctness of judgment and do DPO traning to get our final model.

To train on specially synthesized data, our models not only achieve SOTA on Reward-Bench, but also have good general abilities. We use our model to generate preference pairs to help our internal model's DPO traning and achieve good results.

To get more details about our models and data, view our paper [Improve LLM-as-a-Judge Ability as a General Ability](https://arxiv.org/abs/2502.11689).

## Usage

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "R-I-S-E/RISE-Judge-Qwen2.5-7B"
model = AutoModelForCausalLM.from_pretrained(model_name, device_map='auto', trust_remote_code=True)
tokenizer = AutoTokenizer.from_pretrained(model_name)

question = "What is the remainder of 2004 divided by 12?"
answer_a = "I know that 12 divides evenly into 2000, so the remainder will be the same as dividing 4 by 12.\nBut 4 is less than 12, so it cannot be divided by 12 without using fractions or decimals.\nTherefore, the remainder is just 4 itself.\nThat means 2004 = 12 * 167 + 4.\n# Answer\n\n4"
answer_b = "An integer is divisible by 12 if and only if it is divisible by both 3 and 4.  Because $2+0+0+4=6$ is divisible by 3, 2004 is divisible by 3.  Also, the last two digits of 2004 form a multiple of 4, so 2004 is divisible by 4 as well. Therefore, 2004 is divisible by 12 and hence leaves a remainder of $\\boxed{0}$ when divided by 12.\n"

# Format and tokenize the conversations
RISE_Judge_PROMPT = """下面我会给出一个问题和两个回答，请判断哪个回答更好。注意逐步分析并给出结论。
注意以下几点:
1. 如果给出的问题是开放性问题，请着重评价回答的指令遵循程度和准确性。
2. 如果给出的问题包含歧视、色情、危险等内容，模型应该拒绝回答。请不要选择生成了上述有害内容、生成了错误信息或者不负责任的回答。
3. 请准确判断回答的内容是否和原问题严格相关，不要让回答的长度和前后位置影响你的判断，而应该更重视答案的实用性、有帮助性。
问题：{instruction}\n回答A：{output_1}\n回答B：{output_2}\n
如果你认为回答A更好，请在分析最后输出'[[A]]'，如果你认为回答B更好，请在分析最后输出'[[B]]'。"""
user_prompt = RISE_Judge_PROMPT.format(instruction=question, output_1=answer_a, output_2=answer_b)
system_prompt = ""
messages = [
    {"role": "system", "content": system_prompt,},
    {"role": "user", "content": user_prompt},
]
prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
prompt = tokenizer([prompt], return_tensors="pt")

# Generate judgment for the given prompt
with torch.no_grad():
    generated_ids = model.generate(prompt.input_ids, do_sample=False, max_new_tokens=4096, temperature=0)
generated_ids = [
    output_ids[len(input_ids):] for input_ids, output_ids in zip(prompt.input_ids, generated_ids)
]
response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
print(response)
# response: 让我们逐步分析两个回答。\n\n回答A：\n1. 回答A提到“12 divides evenly into 2000”，这是正确的。\n2. 然后回答A说“the remainder will be the same as dividing 4 by 12”，这也是正确的，因为2004 - 2000 = 4。\n3. 回答A接着说“4 is less than 12, so it cannot be divided by 12 without using fractions or decimals”，这也是正确的。\n4. 最后，回答A得出结论“the remainder is just 4 itself”，这也是正确的。\n\n然而，回答A的回答虽然在逻辑上是正确的，但它没有直接回答问题。问题问的是2004除以12的余数，而回答A的回答是4，这显然是错误的，因为2004除以12的余数应该是0。\n\n回答B：\n1. 回答B提到“An integer is divisible by 12 if and only if it is divisible by both 3 and 4”，这是正确的。\n2. 回答B接着分析2004是否能被3整除，因为2 + 0 + 0 + 4 = 6，6能被3整除，所以2004能被3整除，这也是正确的。\n3. 回答B接着分析2004是否能被4整除，因为最后两位数04能被4整除，所以2004能被4整除，这也是正确的。\n4. 回答B得出结论“2004 is divisible by 12 and hence leaves a remainder of 0 when divided by 12”，这是正确的。\n\n回答B的回答不仅逻辑上正确，而且直接回答了问题，指出2004除以12的余数是0。\n\n因此，回答B的回答更好。\n\n[[B]]

```

## Performance

<table>
  <tr>
    <th rowspan="2">Model</th>
    <th colspan="5">Reward-Bench</th>
  </tr>
  <tr>
    <th>Chat</th>
    <th>Chat-H</th>
    <th>Safety</th>
    <th>Reasoning</th>
    <th>Average</th>
  </tr>
    <td>Llama3.1-8B</td>
    <td>80.7</td>
    <td>49.8</td>
    <td>64.0</td>
    <td>68.1</td>
    <td>65.7</td>
  </tr>
  <tr>
    <td>Llama3.1-70B</td>
    <td><b>97.2</b></td>
    <td>70.2</td>
    <td>82.8</td>
    <td>86.0</td>
    <td>84.0</td>
  </tr>
  <tr>
    <td>Qwen2.5-32B</td>
    <td>86.6</td>
    <td>61.4</td>
    <td>74.5</td>
    <td>90.7</td>
    <td>86.8</td>
  </tr>
    <td>GPT-4o</td>
    <td>96.1</td>
    <td>76.1</td>
    <td>88.1</td>
    <td>86.6</td>
    <td>86.7</td>
  </tr>
  </tr>
    <td>Gemini-1.5-pro</td>
    <td>94.1</td>
    <td>77.0</td>
    <td>85.8</td>
    <td>90.2</td>
    <td>86.8</td>
  </tr>
  </tr>
    <td>Claude-3-5-sonnet</td>
    <td>96.4</td>
    <td>74.0</td>
    <td>81.6</td>
    <td>84.7</td>
    <td>84.2</td>
  </tr>
  <tr>
    <td>RISE-Judge-7B (ours)</td>
    <td>92.2</td>
    <td>76.5</td>
    <td>88.0</td>
    <td>96.1</td>
    <td>88.2</td>
  </tr>
  <tr>
    <td>RISE-Judge-32B (ours)</td>
    <td>96.6</td>
    <td><b>83.3</b></td>
    <td><b>91.9</b></td>
    <td><b>98.8</b></td>
    <td><b>92.7</b></td>
  </tr>
</table>

## Reference
```
@misc{yu2025improvellmasajudgeabilitygeneral,
      title={Improve LLM-as-a-Judge Ability as a General Ability}, 
      author={Jiachen Yu and Shaoning Sun and Xiaohui Hu and Jiaxu Yan and Kaidong Yu and Xuelong Li},
      year={2025},
      eprint={2502.11689},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2502.11689}, 
}
```