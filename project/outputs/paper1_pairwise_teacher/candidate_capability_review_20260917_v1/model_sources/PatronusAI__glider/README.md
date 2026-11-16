---
library_name: transformers
tags:
- text-generation
- pytorch
- small-evaluator
- Patronus AI
- evaluation
- hallucination-detection
- multilingual
license: cc-by-nc-4.0
language:
- en
base_model:
- microsoft/Phi-3.5-mini-instruct
pipeline_tag: text-generation
---

# Patronus GLIDER

<a href=https://github.com/patronus-ai/glider><img src="https://img.shields.io/badge/GithubCode-Glider-13d91f"></a> 
<a href=https://huggingface.co/PatronusAI/glider-gguf><img src="https://img.shields.io/badge/GGUF-Glider_GGUF-blue"></a>
<a href=https://arxiv.org/abs/2412.14140><img src="https://img.shields.io/badge/Paper-2412.14140-red"></a>
<a href=https://www.patronus.ai/blog/glider-state-of-the-art-slm-judge><img src="https://img.shields.io/badge/Patronus-Blog-violet"></a>


<img src="https://i.imgur.com/1AbgTJa.png" alt="GLIDER" width="100%"/>

GLIDER is a fine tuned phi-3.5-mini-instruct which can be used as a general purpose evaluation model to judge texts, conversations and RAG setups according to arbitrary, user defined criteria and rubric scale. 
This model was trained using a combination of synthetic and domain adapted data from popular datasets like Mocha, FinQA, Realtoxicity, etc.  The training data for this model covers over 183 metrics and 685 domains including finance, medicine, and many more.
The maximum sequence length is 8192 tokens but the model can support longer texts as well (tested upto 12,000 tokens). 


## Model Details

- **Model Type:** GLIDER is a fine-tuned version of microsoft/Phi-3.5-mini-instruct model.
- **Language:** Primarily English but supports Korean, Kazakh, Hindi, Bengali, Spanish, Indonesian, German, French, Arabic, Russian, Thai, Turkish, Ukraninan, Romainian and more.
- **Developed by:** Patronus AI
- **Paper:** [https://arxiv.org/abs/2412.14140](https://arxiv.org/abs/2412.14140)
- **License:** [https://creativecommons.org/licenses/by-nc/4.0/](https://creativecommons.org/licenses/by-nc/4.0/)

### Model Sources

<!-- Provide the basic links for the model. -->

- **Repository:** [https://github.com/patronus-ai/glider](https://github.com/patronus-ai/glider)


## How to Get Started with the Model
To use the model, we recommend using the following prompt:

```
PROMPT = """Analyze the following pass criteria carefully and score the text based on the rubric defined below.

To perform this evaluation, you must:

1. Understand the text tags, pass criteria and rubric thoroughly.
2. Review the finer details of the text and the rubric.
3. Compare the tags to be evaluated to the score descriptions in the rubric.
4. Pay close attention to small details that might impact the final score and form accurate associations between tags and pass criteria.
5. Write a detailed reasoning justifying your evaluation in a bullet point format. 
6. The reasoning must summarize the overall strengths and weaknesses of the output while quoting exact phrases from the output wherever required.
7. Output a list of words or phrases that you believe are the most important in determining the score.
8. Assign a final score based on the scoring rubric.

Data to evaluate:
{data}

Pass Criteria:
{pass_criteria}

Rubric:
{rubric}

Your output must in the following format:
<reasoning>
[Detailed reasoning justifying your evaluation in a bullet point format according to the specifics defined above]
</reasoning>
<highlight>
[List of words or phrases that you believe are the most important in determining the score]
</highlight>
<score>
[The final integer score assigned based on the scoring rubric]
</score>
"""
```

Since the model supports arbitrary number of inputs and outputs, the data can be structured in any one of the following ways:

1. Conversational data:

```
data = """<SYSTEM PROMPT>
{system_prompt}
</SYSTEM PROMPT>

<USER PROMPT>
{user_prompt}
</USER PROMPT>

<ASSISTANT REPLY>
{assistant_response}
</ASSISTANT REPLY>
"""
```

This template can be adapted for arbitrary number of conversations by simply appending a numeric turn number as "<USER PROMPT 1>", "<USER PROMPT 2>" and so on. 
Ensure that you specify the exact tags that you want the model to judge in the pass criteria

2. RAG system evaluation

```
data = """<CONTEXT>
{retrieved_context}
</CONTEXT>

<USER INPUT>
{user_input}
</USER INPUT>

<MODEL OUTPUT>
{model_output}
</MODEL OUTPUT>
"""
```

3. General purpose evaluations

```
data = """<USER INPUT>
{input}
</USER INPUT>

<MODEL OUTPUT>
{output}
</MODEL OUTPUT>
"""
```

Note that these XML tags can be changed according to your convenience and task

## Inference

To run inference, you can use HF pipeline:

```
model_name = 'PatronusAI/glider'
pipe = pipeline(
          "text-generation",
          model=model_name,
          max_new_tokens=2048,
          device="cuda",
          return_full_text=False
        )

messages = [
    {"role": "user", "content": prompt},
]

result = pipe(messages)
print(result[0]['generated_text'])

```

Since the model is trained in chat format, ensure that you pass the prompt as a user message.

## Evaluation

The model was evaluated on several popular datasets:

<img src="https://i.imgur.com/77lhcwf.png" alt="Results" width="100%"/>

## Citation
If you are using the model, cite using

```
@misc{deshpande2024glider,
      title={GLIDER: Grading LLM Interactions and Decisions using Explainable Ranking}, 
      author={Darshan Deshpande and Selvan Sunitha Ravi and Sky CH-Wang and Bartosz Mielczarek and Anand Kannappan and Rebecca Qian},
      year={2024},
      eprint={2412.14140},
      archivePrefix={arXiv},
      primaryClass={cs.CL},
      url={https://arxiv.org/abs/2412.14140}, 
}
```

## Model Card Contact
[@darshandeshpande](https://huggingface.co/darshandeshpande)
[@RebeccaQian1](https://huggingface.co/RebeccaQian1)