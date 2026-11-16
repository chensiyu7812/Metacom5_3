---
license: other
base_model: meta-llama/Meta-Llama-3.1-8B-Instruct
pipeline_tag: text-generation
---

<div align="center">
<img src="misc/misc_fig.jpg" width="400"/>
🤗 <a href="https://huggingface.co/Skywork" target="_blank">Hugging Face</a> • 🤖 <a href="https://modelscope.cn/organization/Skywork" target="_blank">ModelScope</a>
<br>
<br>
<br>
</div>

# Introduction to Skywork Critic Series Models

[**Skywork-Critic-Llama3.1-70B**](https://huggingface.co/Skywork/Skywork-Critic-Llama3.1-70B) and [**Skywork-Critic-Llama3.1-8B**](https://huggingface.co/Skywork/Skywork-Critic-Llama-3.1-8B), developed by the [SkyworkAI](https://huggingface.co/Skywork) Alignment Team, are advanced judge models that excel at pairwise preference evaluation. These models compare and assess input pairs, offering nuanced judgments on their relative quality or suitability. Leveraging their deep understanding of language and context, Skywork-Critic models provide valuable insights for various applications, including data improvement, evaluation, and reward modeling.

# Training Details 


Skywork-Critic-Llama3.1-70B and Skywork-Critic-Llama3.1-8B are built on Meta [Llama-3.1-70B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3-70B-Instruct) and [Llama-3.1-8B-Instruct](https://huggingface.co/meta-llama/Meta-Llama-3-8B-Instruct) respectively. These models have undergone fine-tuning using a diverse array of high-quality datasets, including:
- **Cleaned open-source data**: We utilize a high-quality subset of [HelpSteer2](https://huggingface.co/datasets/nvidia/HelpSteer2), [OffsetBias](https://huggingface.co/datasets/NCSOFT/offsetbias), [WildGuard (adversarial)](https://huggingface.co/allenai/wildguard) and Magpie DPO series([Ultra](https://huggingface.co/datasets/argilla/magpie-ultra-v0.1),[Pro (Llama-3.1)](https://huggingface.co/datasets/Magpie-Align/Magpie-Llama-3.1-Pro-DPO-100K-v0.1),[Pro](https://huggingface.co/datasets/Magpie-Align/Magpie-Pro-DPO-100K-v0.1),[Air](https://huggingface.co/datasets/Magpie-Align/Magpie-Air-DPO-100K-v0.1)). For more details, please refer to our [Skywork-Reward-Preference-80K-v0.1 dataset](https://huggingface.co/datasets/Skywork/Skywork-Reward-Preference-80K-v0.1). Additionally, we integrate several open-source, high-quality critic datasets such as [Open-Critic-GPT](https://huggingface.co/datasets/Vezora/Open-Critic-GPT) into our training process.
- **In-house human annotation data**: This includes both pointwise scoring across many dimensions for a single response and pairwise comparisons between two responses. Each dimension incorporates a rationale for the assigned score. Please note that manually labeled data is very expensive to obtain. We only have a few hundred manually labeled data points, all of which are in Chinese, so the ability to perform single rating might not be particularly strong. 
- **Synthetic critic data**: We use a similar appoarch to [**self-taught**](https://arxiv.org/abs/2408.02666). Specifically, we employed two methods to generate inferior responses for a given instruction: 1) Creating a similar instruction and then generating a response for this new instruction. 2) Introducing subtle errors into high-quality responses. 
- **Critic-related chat data**: We incorporate critic-related chat data to maintain the model's conversational capabilities.

The training employs instruction-tuning methodology, focusing on pairwise preference evaluation and general chat tasks. We have conducted a thorough verification process to ensure our training dataset does not contain any test set information from RewardBench, maintaining the integrity of our evaluation results.


# RewardBench Leaderboard for Generative Models

We evaluate our models on [RewardBench](https://huggingface.co/spaces/allenai/reward-bench) using the [official test script](https://github.com/allenai/reward-bench). 

As of September 2024, Skywork-Critic-Llama3.1-70B **ranks first** on RewardBench for generative models across all sizes, while Skywork-Critic-Llama3.1-8B tops the list for generative models under 10B parameters. (Note: An asterisk (*) indicates an open-source model.)


| Model                           | Chat  | Chat Hard | Safety | Reasoning | Overall Score |
| ------------------------------- | :---: | :-------: | :----: | :-------: | :---: |
| **Skywork-Critic-Llama3.1-70B**  *      | **96.6**  |   **87.9**    |  **93.1**  |   **95.5**    | **93.3**  |
| Salesforce/SFR-LLaMa-3.1-70B-Judge-r      | 96.9 | 84.8 | 91.6 | 97.6    | 92.7  |
| Salesforce/SFR-nemo-12B-Judge-r      | 97.2 | 82.2 | 86.5 | 95.1    | 90.3  |
| **Skywork-Critic-Llama3.1-8B**  *      | **93.6**  |   **81.4**    |  **91.1**  |   **89.8**    | **89.0**  |
| Salesforce/SFR-LLaMa-3.1-8B-Judge-r      | 95.5 | 77.7 | 86.2 | 95.1    | 88.7  |
| facebook/Self-taught-Llama-3-70B  | 96.9  |   84.0    |  91.1  |   82.5    | 88.6  |
| google/gemini-1.5-pro-0514      | 92.3  |   80.6    |  87.9  |   92.0    | 88.2  |
| openai/gpt-4o-2024-08-06         | 96.1  |   76.1    |  88.1  |   86.6    | 86.7  |
| openai/gpt-4-0125-preview    | 95.3  |   74.3    |  87.6  |   86.9    | 86.0  |
| openai/gpt-4-turbo-2024-04-09        | 95.3  |   75.4    |  87.6  |   82.7    | 85.2  |
| Anthropic/claude-3-5-sonnet-20240620       | 96.4  |   74.0    |  81.6  |   84.7    | 84.2  |
| meta-llama/Meta-Llama-3.1-70B-Instruct *       | 97.2 |   70.2    |  82.8  |   86.0    | 84.0  |
| NCSOFT/Llama-3-OffsetBias-8B *       | 92.5  |   80.3    |  86.8  |   76.4    | 84.0  |


# Demo Code
Below is an example of obtaining the critic of two conversations.

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# An Example Case
prompt = "Jane has 12 apples. She gives 4 apples to her friend Mark, then buys 1 more apple, and finally splits all her apples equally among herself and her 2 siblings. How many apples does each person get?"
responseA = "1. Jane starts with 12 apples and gives 4 to Mark. 12 - 4 = 8. Jane now has 8 apples.\n2. Jane buys 1 more apple. 8 + 1 = 9. Jane now has 9 apples.\n3. Jane splits the 9 apples equally among herself and her 2 siblings (3 people in total). 9 ÷ 3 = 3 apples each. Each person gets 3 apples."
responseB = "1. Jane starts with 12 apples and gives 4 to Mark. 12 - 4 = 8. Jane now has 8 apples.\n2. Jane buys 1 more apple. 8 + 1 = 9. Jane now has 9 apples.\n3. Jane splits the 9 apples equally among her 2 siblings (2 people in total). 9 ÷ 2 = 4.5 apples each. Each person gets 4 apples."

# feed a natural language prompt to generative model
prompt_template = """Please act as an impartial judge and evaluate the quality of the responses provided by two AI assistants to the user question displayed below. You should choose the assistant that follows the user\'s instructions and answers the user\'s question better. 
Your evaluation should consider factors such as the helpfulness, relevance, accuracy, depth, creativity, and level of detail of their responses. Avoid any position biases and ensure that the order in which the responses were presented does not influence your decision. Do not allow the length of the responses to influence your evaluation. Do not favor certain names of the assistants. Be as objective as possible. 
Please directly output your final verdict by strictly following this format: "[[A]]" if assistant A is better, "[[B]]" if assistant B is better.

[User Question]
{input}

[The Start of Assistant A's Answer]
{response_a}
[The End of Assistant A's Answer]

[The Start of Assistant B's Answer]
{response_b}
[The End of Assistant B's Answer]
"""

user_message = prompt_template.format(input=prompt, response_a=responseA, response_b=responseB)

conversation = [{"role": "user", "content": user_message}]

model_name = "Skywork/Skywork-Critic-Llama3.1-70B"
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",
    device_map="auto"
)
tokenizer = AutoTokenizer.from_pretrained(model_name)

input_ids = tokenizer.apply_chat_template(
    conversation, 
    tokenize=True, 
    add_generation_prompt=True,
    return_tensors="pt").to(model.device)

generation = model.generate(
    input_ids=input_ids,
    max_new_tokens=2048,
    do_sample=False,
    pad_token_id=128009,
    temperature=0)

completion = tokenizer.decode(
    generation[0][len(input_ids[0]):], 
    skip_special_tokens=True, 
    clean_up_tokenization_spaces=True)

print(completion)

# Output:
# The generative model should output "[[A]]"

```

# Declaration and License Agreement

## Declaration

We hereby declare that the Skywork model should not be used for any activities that pose a threat to national or societal security or engage in unlawful actions. Additionally, we request users not to deploy the Skywork model for internet services without appropriate security reviews and records. We hope that all users will adhere to this principle to ensure that technological advancements occur in a regulated and lawful environment.

We have done our utmost to ensure the compliance of the data used during the model's training process. However, despite our extensive efforts, due to the complexity of the model and data, there may still be unpredictable risks and issues. Therefore, if any problems arise as a result of using the Skywork open-source model, including but not limited to data security issues, public opinion risks, or any risks and problems arising from the model being misled, abused, disseminated, or improperly utilized, we will not assume any responsibility.

## License Agreement

The community usage of Skywork model requires [Skywork Community License](https://github.com/SkyworkAI/Skywork-Reward/blob/main/misc/Skywork%20Community%20License.pdf). The Skywork model supports commercial use. If you plan to use the Skywork model or its derivatives for commercial purposes, you must abide by terms and conditions within [Skywork Community License](https://github.com/SkyworkAI/Skywork-Reward/blob/main/misc/Skywork%20Community%20License.pdf).

# Contact
If you have any questions or feedback, don't hesitate to reach out to our friendly team at <shiwen.tu@kunlun-inc.com> or <liang.zhao@kunlun-inc.com>. Liang Zhao leads this project.

# Citation

If you find our work helpful, please feel free to cite us using the following BibTeX entry:

```bibtex
@misc{skyworkcritic2024,
  title={Skywork Critic Model Series},
  author={Shiwen, Tu and Liang, Zhao and Liu, Chris Yuhao and Zeng, Liang and Liu, Yang},
  year={2024},
  month={September},
  howpublished={\url{https://huggingface.co/Skywork}},
  url={https://huggingface.co/Skywork},
}
```
