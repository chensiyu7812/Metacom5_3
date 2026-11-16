---
base_model:
- deepseek-ai/DeepSeek-R1-Distill-Qwen-14B
language:
- en
license: mit
pipeline_tag: text-generation
library_name: transformers
---

![image/png](https://cdn-uploads.huggingface.co/production/uploads/654d784d71a30c4bca09a319/Q7MVJfIHDerQ24c1zwZwK.png)

<font size=3><div align='center' >  
[[**🤗 Model & Dataset**](https://huggingface.co/collections/gaotang/rm-r1-681128cdab932701cad844c8)] 
[[**📊 Code**](https://github.com/RM-R1-UIUC/RM-R1)] 
[[**📖 Paper**](https://arxiv.org/abs/2505.02387)]
</div></font>

# 🚀 Can we cast reward modeling as a reasoning task?

**RM-R1** is a training framework for *Reasoning Reward Model* (ReasRM) that judges two candidate answers by first **thinking out loud**—generating structured rubrics or reasoning traces—then emitting its preference. Compared to traditional scalar or generative reward models, RM-R1 delivers **state-of-the-art performance** on public RM benchmarks on average while offering fully interpretable justifications.


## 🧠 TL;DR
* **Two-stage training**  
  1. **Distillation** of ~8.7 K high-quality reasoning traces (Chain-of-Rubrics).  
  2. **Reinforcement Learning with Verifiable Rewards** (RLVR) on ~64 K preference pairs.

* **Backbones** released: 7 B / 14 B / 32 B Qwen-2.5-Instruct variants + DeepSeek-distilled checkpoints.

## 💡 Intended uses
* **RLHF / RLAIF**: plug-and-play reward function for policy optimisation.  
* **Automated evaluation**: LLM-as-a-judge for open-domain QA, chat, and reasoning.  
* **Research**: study process supervision, chain-of-thought verification, or rubric generation.

## 🔍 Demo Code 

Try the model with this example. Full demo notebook available at:

📎 [Official Demo Link](https://github.com/RM-R1-UIUC/RM-R1/blob/main/demo/demo.ipynb)

### 🧾 Prompt Template 

```python
REASONING_SINGLE_PROMPT_TEMPLATE = (
    "Please act as an impartial judge and evaluate the quality of the responses provided by two AI Chatbots to the Client question displayed below. \n\n"
    "[Client Question]\n{question}\n\n[The Start of Chatbot A's Response]\n{answer_a}\n[The End of Chatbot A's Response]\n\n"
    "[The Start of Chatbot B's Response]\n{answer_b}\n[The End of Chatbot B's Response]" + "\n\n"
    "Output your final verdict at last by strictly following this format: "
    "'<answer>[[A]]</answer>' if Chatbot A is better, or '<answer>[[B]]</answer>' if Chatbot B is better."
)
```

### 📦 Inference Code

```python
# Load the Model 
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

model_name = "gaotang/RM-R1-DeepSeek-Distilled-Qwen-14B"
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype="auto",
    device_map="auto" # or specify the specific device map if needed
)
tokenizer = AutoTokenizer.from_pretrained(model_name)

# Single Turn Example - from Reward Bench 

prompt = "How do I detail a car?"
answer_a = "Detailing a car involves a thorough cleaning inside and out, as well as polishing and waxing to protect the vehicle's surfaces. Here's a step-by-step guide to detailing a car:\n\n**Exterior Detailing:**\n\n1. **Wash the Car:**\n   - Rinse the car with water to remove loose dirt.\n   - Use a car wash soap and microfiber wash mitt to clean the car from top to bottom.\n   - Clean the wheels and tires with a brush and a wheel cleaner.\n   - Rinse the car thoroughly to remove all soap.\n\n2. **Dry the Car:**\n   - Use a microfiber towel or a chamois to dry the car to prevent water spots.\n\n3. **Clay Bar Treatment:**\n   - Use a clay bar with a lubricant to remove embedded surface contaminants from the paint.\n\n4. **Polishing:**\n   - Apply car polish with a dual-action polisher or by hand to correct paint imperfections and create a smooth surface.\n\n5. **Waxing:**\n   - Apply a coat of wax or paint sealant to protect the paint and give it a glossy finish.\n\n6. **Windows and Mirrors:**\n   - Clean the windows and mirrors with a glass cleaner and a microfiber towel.\n\n7. **Tire and Trim Dressing:**\n   - Apply a tire dressing to the tires for a shiny finish.\n   - Use a trim restorer or protectant on plastic and rubber parts to prevent fading.\n\n**Interior Detailing:**\n\n1. **Remove Trash:**\n   - Clear out any trash and remove personal items from the car.\n\n2. **Vacuum:**\n   - Vacuum the seats, carpets, floor mats, and trunk.\n   - Use a brush attachment for the dashboard and door panels.\n\n3. **Shampoo Carpets and Upholstery:**\n   - Use a carpet cleaner and a brush to clean the carpets and upholstery.\n   - For leather interiors, use a leather cleaner and conditioner.\n\n4. **Clean Hard Surfaces:**\n   - Wipe down all hard surfaces (dashboard, center console, door panels, etc.) with a mild all-purpose cleaner and a microfiber cloth.\n\n5. **Windows and Mirrors:**\n   - Clean the interior side of windows and mirrors.\n\n6. **Air Vents and Crevices:**\n   - Use a detailing brush or compressed air to clean out air vents and hard-to-reach crevices.\n\n7. **Final Touches:**\n   - Apply a protectant to the dashboard and other plastic components.\n   - Replace air fresheners if needed.\n\n**Additional Tips:**\n\n- Work in the shade or a cool, well-ventilated garage to prevent products from drying too quickly and leaving residue.\n- Use separate buckets for washing and rinsing to avoid contaminating the clean water with dirt.\n- Always use gentle, non-abrasive materials and cleaners specifically designed for automotive use to avoid damaging surfaces.\n- Move in a systematic way to ensure you don't miss any spots.\n\nBy following these steps, you'll give your car a thorough clean that not only makes it look great but also helps in maintaining its value. Remember, regular detailing can prevent wear and tear and keep your car looking new for years to come." # Accepted
answer_b = "Detailing a car involves washing the exterior and interior of the car, as well as polishing and waxing the exterior. Interior detailing typically involves vacuuming, cleaning the upholstery and air vents, polishing the dashboard and console, and dusting. Polishing and waxing the exterior will depend on the condition of the paint, but typically involves applying a polish and wax to make it shine."  # Rejected

user_prompt_single = REASONING_SINGLE_PROMPT_TEMPLATE.format(
    question=prompt,
    answer_a=answer_a,
    answer_b=answer_b
) 

conversation = [
    {"role":"user", "content": user_prompt_single}
]

input_ids = tokenizer.apply_chat_template(
    conversation, 
    tokenize=True, 
    add_generation_prompt=True,
    return_tensors="pt").to(model.device)

generation = model.generate(
    input_ids=input_ids,
    max_new_tokens=8192, # For optimal performance benchmarking, please set this to unlimited (e.g., 50000)
    do_sample=False,
)

completion = tokenizer.decode(
    generation[0][len(input_ids[0]):], 
    skip_special_tokens=True, 
    clean_up_tokenization_spaces=True
)

print(completion)
```

## Citations

```bibtex
@article{chen2025rm,
  title={RM-R1: Reward Modeling as Reasoning},
  author={Chen, Xiusi and Li, Gaotang and Wang, Ziqi and Jin, Bowen and Qian, Cheng and Wang, Yu and Wang, Hongru and Zhang, Yu and Zhang, Denghui and Zhang, Tong and others},
  journal={arXiv preprint arXiv:2505.02387},
  year={2025}
}
```