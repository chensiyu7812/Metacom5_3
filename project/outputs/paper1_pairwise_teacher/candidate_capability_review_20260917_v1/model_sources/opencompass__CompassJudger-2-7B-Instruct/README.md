---
library_name: transformers
license: apache-2.0
pipeline_tag: text-ranking
tags:
- llm-as-judge
- qwen2
---

# CompassJudger-2

<div align="left" style="line-height: 1;">
  <a href="https://github.com/open-compass/CompassJudger" target="_blank" style="margin: 2px;">
    <img alt="Homepage" src="https://img.shields.io/badge/CompassJudger-GitHub-blue?color=1991ff&logo=github&logoColor=white" style="display: inline-block; vertical-align: middle;"/>
  </a>
  <a href="https://arxiv.org/abs/2507.09104" target="_blank" style="margin: 2px;"">
    <img
      src="https://img.shields.io/badge/CompassJudger--2-Paper-red?logo=arxiv&logoColor=red"
      alt="CompassJudger-2"
      style="display: inline-block; vertical-align: middle;"
    />
  </a>
  <a href="https://huggingface.co/opencompass" target="_blank" style="margin: 2px;">
      <img alt="Hugging Face" src="https://img.shields.io/badge/%F0%9F%A4%97%20Hugging%20Face-OpenCompass-536af5?color=536af5&logoColor=white" style="display: inline-block; vertical-align: middle;"/>
  </a>
  <a href="https://github.com/open-compass/CompassJudger/blob/main/LICENSE" style="margin: 2px;">
      <img alt="License" src="https://img.shields.io/badge/License-Apache%202.0-f5de53?color=f5de53&logoColor=white" style="display: inline-block; vertical-align: middle;"/>
  </a>
</div>

## Introduction

We introduce **CompassJudger-2**, a novel series of generalist judge models designed to overcome the narrow specialization and limited robustness of existing LLM-as-judge solutions. Current judge models often struggle with comprehensive evaluation, but CompassJudger-2 addresses these limitations with a powerful new training paradigm.

Key contributions of our work include:

-   **Advanced Data Strategy:** We employ a task-driven, multi-domain data curation and synthesis strategy to enhance the model's robustness and domain adaptability.
-   **Verifiable Reward-Guided Training:** We supervise judgment tasks with verifiable rewards, guiding the model's intrinsic reasoning through chain-of-thought (CoT) and rejection sampling. A refined margin policy gradient loss further enhances performance.
-   **Superior Performance:** CompassJudger-2 achieves state-of-the-art results across multiple judge and reward benchmarks. Our 7B model demonstrates competitive accuracy with models that are significantly larger.
-   **JudgerBenchV2:** We introduce a new, comprehensive benchmark with 10,000 questions across 10 scenarios, using a Mixture-of-Judgers (MoJ) consensus for more reliable ground truth.

This repository contains the **CompassJudger-2** series of models, fine-tuned on the Qwen2.5-Instruct series.

## Models

| Model Name                         | Size | Base Model           |                           Download                           | Notes                                         |
| :--------------------------------- | :--: | :------------------- | :----------------------------------------------------------: | :-------------------------------------------- |
| 👉 **CompassJudger-2-7B-Instruct**  |  7B  | Qwen2.5-7B-Instruct  | 🤗 [Model](https://huggingface.co/opencompass/CompassJudger-2-7B-Instruct) | Fine-tuned for generalist judge capabilities. |
| 👉 **CompassJudger-2-32B-Instruct** | 32B  | Qwen2.5-32B-Instruct | 🤗 [Model](https://huggingface.co/opencompass/CompassJudger-2-32B-Instruct) | A larger, more powerful judge model.          |

## Quickstart

Here is a simple example demonstrating how to load the model and use it for pairwise evaluation.

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path = "opencompass/CompassJudger-2-7B-Instruct"

model = AutoModelForCausalLM.from_pretrained(
    model_path,
    torch_dtype="auto",
    device_map="auto"
)
tokenizer = AutoTokenizer.from_pretrained(model_path)

# Example: Pair-wise Comparison
prompt = """
Please act as an impartial judge to evaluate the responses provided by two AI assistants to the user question below. Your evaluation should focus on the following criteria: helpfulness, relevance, accuracy, depth, creativity, and level of detail.

- Do not let the order of presentation, response length, or assistant names influence your judgment.
- Base your decision solely on how well each response addresses the user’s question and adheres to the instructions.

Your final reply must be structured in the following format:
{
  "Choice": "[Model A or Model B]"
}

User Question: {question}

Model A's Response: {answerA}

Model B's Response: {answerB}

Now it's your turn. Please provide selection result as required:
"""

messages = [
    {"role": "user", "content": prompt}
]

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)
model_inputs = tokenizer([text], return_tensors="pt").to(model.device)

generated_ids = model.generate(
    **model_inputs,
    max_new_tokens=2048
)
generated_ids = [
    output_ids[len(input_ids):] for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
]

response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
print(response)
```

## Evaluation

CompassJudger-2 sets a new state-of-the-art for judge models, outperforming general models, reward models, and other specialized judge models across a wide range of benchmarks.

| Model                              | JudgerBench V2 | JudgeBench |    RMB    | RewardBench |  Average  |
| :--------------------------------- | :------------: | :--------: | :-------: | :---------: | :-------: |
| **7B Judge Models**                |                |            |           |             |           |
| CompassJudger-1-7B-Instruct        |     57.96      |   46.00    |   38.18   |    80.74    |   55.72   |
| Con-J-7B-Instruct                  |     52.35      |   38.06    |   71.50   |    87.10    |   62.25   |
| RISE-Judge-Qwen2.5-7B              |     46.12      |   40.48    |   72.64   |    88.20    |   61.61   |
| **CompassJudger-2-7B-Instruct**    |   **60.52**    | **63.06**  | **73.90** |  **90.96**  | **72.11** |
| **32B+ Judge Models**              |                |            |           |             |           |
| CompassJudger-1-32B-Instruct       |     60.33      |   62.29    |   77.63   |    86.17    |   71.61   |
| Skywork-Critic-Llama-3.1-70B       |     52.41      |   50.65    |   65.50   |    93.30    |   65.47   |
| RISE-Judge-Qwen2.5-32B             |     56.42      |   63.87    |   73.70   |    92.70    |   71.67   |
| **CompassJudger-2-32B-Instruct**   |   **62.21**   | **65.48**  |   72.98   |  **92.62**  | **73.32** |
| **General Models (for reference)** |                |            |           |             |           |\
| Qwen2.5-32B-Instruct               |     62.97      |   59.84    |   74.99   |    85.61    |   70.85   |
| DeepSeek-V3-0324                   |     64.43      |   59.68    |   78.16   |    85.17    |   71.86   |
| Qwen3-235B-A22B                    |     61.40      |   65.97    |   75.59   |    84.68    |   71.91   |


For detailed benchmark performance and methodology, please refer to our [📑 Paper](https://huggingface.co/papers/2507.09104). 

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](https://github.com/open-compass/CompassJudger/blob/main/LICENSE) file for details. 

## Citation

If you find our work helpful, please consider citing our paper:

```bibtex
@article{zhang2025compassjudger,
  title={CompassJudger-2: Towards Generalist Judge Model via Verifiable Rewards},
  author={Zhang, Taolin and Cao, Maosong and Lam, Alexander and Zhang, Songyang and Chen, Kai},
  journal={arXiv preprint arXiv:2507.09104},
  year={2025}
}
```