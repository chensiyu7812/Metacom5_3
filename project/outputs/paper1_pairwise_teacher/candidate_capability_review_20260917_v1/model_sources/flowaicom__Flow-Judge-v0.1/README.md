---
language:
- en
license: apache-2.0
license_link: https://huggingface.co/flowaicom/Flow-Judge-v0.1/resolve/main/LICENSE
tags:
- lm-judge
- evaluation
- nlp
datasets:
- flowaicom/Flow-Judge-v0.1-binary-heldout
- flowaicom/Flow-Judge-v0.1-3-likert-heldout
- flowaicom/Flow-Judge-v0.1-5-likert-heldout
pipeline_tag: text-generation
library_name: transformers
metrics:
- accuracy
- f1
- precision
- recall
- pearsonr
- spearmanr
- kendall-tau
base_model:
- microsoft/Phi-3.5-mini-instruct
widget:
  - messages:
    - role: user
      content: |
        # GOAL
        Your job is to evaluate a task carried out by an AI system powered by a large language model.
        You will be provided with the inputs and output of the task, as well as the evaluation criteria and scoring rubric. Your task is to evaluate the output of the AI system based on the evaluation criteria and scoring rubric provided.
        # INPUT/s
        Below are the inputs required for performing the task:
        <inputs>
        <customer_query>
        Subject: Issues with recent order #12345
        Hello,
        I recently received my order #12345, but I'm having a few problems:
        1. The blue t-shirt I ordered is actually green. Can I exchange it?
        2. The phone case doesn't fit my iPhone 13 Pro Max. The website said it was compatible.
        3. I was charged for express shipping, but it took over a week to arrive. Can I get a refund on the shipping cost?
        Please let me know how we can resolve these issues. I've been a loyal customer for years and this is the first time I've had problems like this.
        Thank you,
        Jane Smith
        </customer_query>
        </inputs>

        # OUTPUT
        Below is the output of the task:
        <output>
        Dear Jane Smith,
        Thank you for reaching out about the issues with your recent order #12345. We sincerely apologize for the inconvenience you've experienced. Let me address each of your concerns:
        1. T-shirt color discrepancy: We're sorry about the mix-up with the t-shirt color. We'd be happy to exchange it for the correct blue t-shirt. I'll send you a prepaid return label for the green shirt, and we'll ship out the blue one as soon as we receive the return.
        2. Phone case compatibility: We apologize for the confusion regarding the phone case compatibility. Our website information should have been more accurate. We'll gladly accept a return of the incompatible case and issue a full refund for it. Additionally, I can recommend a case that will fit your iPhone 13 Pro Max if you're interested.
        3. Shipping charge: You're absolutely right about the shipping charge. Since the delivery didn't meet our express shipping standards, we will refund the entire shipping cost to your original payment method. This refund should process within 3-5 business days.
        To initiate these resolutions, please reply to this email confirming that you'd like to proceed with the t-shirt exchange and phone case return. Once confirmed, I'll send you the necessary return labels and process the shipping refund immediately.
        We truly value your loyalty as a long-time customer and sincerely regret that you've encountered these issues. Rest assured, we're taking steps to prevent similar problems in the future. As a gesture of goodwill, we'd like to offer you a 20% discount on your next order.
        If you have any further questions or concerns, please don't hesitate to reach out. We're here to ensure your complete satisfaction.
        Best regards,
        Alex Johnson
        Customer Service Representative
        </output>

        # EVALUATION CRITERIA AND SCORING RUBRIC
        Here are the evaluation criteria and the rubric that you need to use for evaluating the task:
        <evaluation_criteria>
        How well the response addresses the specific issues raised in the customer's query?
        </evaluation_criteria>
        <scoring_rubric>
        - Score 1: The response completely fails to address the customer's needs and ignores the specific issues raised.
        - Score 2: The response barely addresses the customer's query and misses most of the specific issues raised.
        - Score 3: The response partially addresses the customer's query, touching on some of the specific issues but leaving others unaddressed.
        - Score 4: The response adequately addresses most aspects of the customer's query and the specific issues raised.
        - Score 5: The response fully and comprehensively addresses all aspects of the customer's query and all specific issues raised in a highly satisfactory manner.
        </scoring_rubric>

        # INSTRUCTIONS FOR THE EVALUATION
        1. Understand the task and criteria: Familiarize yourself with the task to be evaluated. Review the evaluation criteria and scoring rubric to understand the different levels of performance and the descriptions for each score.
        2. Review the inputs and output: Look at the inputs provided for the task. Examine the output generated from completing the task.
        3. Compare output to score descriptions: Compare the output against the criteria and score descriptions in the scoring rubric. For each criterion,decide which description best matches the output.
        4. After comparing the output to the score descriptions, pay attention to the small details that might impact the final score that you assign. Sometimes a small difference can dictate the final score.
        5. Write verbal feedback justifying your evaluation that includes a detailed rationale, referring to specific aspects of the output and comparing them to the rubric.
        6. Assign a final score based on the scoring rubric.

        ## FORMAT FOR THE EVALUATION
        - Write the verbal feedback inside <feedback> tags without any additional surrounding text.
        - Write the numeric score inside <score> tags, without any additional surrounding text and always after the feedback.
        Please accurately evaluate the task. Strictly adhere to the evaluation criteria and rubric.
---

<p align="center">
  <img src="https://cdn-uploads.huggingface.co/production/uploads/63368577d184e6b53c50e6d0/6kSJKgPh2pDh4tA-Ky0xW.png" alt="Centered image">
</p>
<p align="center">🚀 <a href="https://www.flow-ai.com/judge">Flow Judge</a> | 📄 <a href="https://www.flow-ai.com/blog/flow-judge">Technical report</a> | 💻 <a href="https://github.com/flowaicom/flow-judge">flow-judge</a></p>

## Model Summary

Flow-Judge-v0.1 is a compact yet powerful 3.8B model that offers customizable LLM system evaluations across various fields. The model inherits it's architecture from Phi-3.5-mini instruct model which enables Flow-Judge to deliver high-quality results while maintaining a small footprint. Despite its smaller size, it achieves performance comparable to larger models in both held-out and out-of-domain benchmarks. Flow-Judge-v0.1 supports multiple scoring scales, provides qualitative feedback, and generates structured evaluation outputs. Trained on a smaller synthetic dataset, it represents an efficient approach to AI development. Released under the Apache 2.0 license, Flow Judge is an open and accessible model suitable for developers and companies seeking cost-effective and rapid evaluations using custom rubrics.

__Quantized weights__
- [flowaicom/Flow-Judge-v0.1-AWQ](https://huggingface.co/flowaicom/Flow-Judge-v0.1-AWQ)
- [flowaicom/Flow-Judge-v0.1-GGUF](https://huggingface.co/flowaicom/Flow-Judge-v0.1-GGUF)

__Quickstart__
- [Quickstart](https://github.com/flowaicom/flow-judge/examples/1_quickstart.ipynb)

## Intended Use Case
Flow Judge is intended to be used on custom LLM system evaluation tasks.

- Customizable evaluations: Users can define their own evaluation criteria and rubrics, tailoring Flow Judge to their specific needs and requirements. This flexibility allows for the creation of highly targeted assessments that accurately measure performance of their LLM system

- Flow Judge supports three different scoring scales:
    - Pass/fail: Suitable for binary assessments, such as determining whether a piece of text meets a specific standard or contains errors.
    - 3-Likert: Allows for more granular evaluations, with scores ranging from negative to neutral to positive. Useful for assessing the overall quality or sentiment of a piece of text.
    - 5-Likert: Provides an even more nuanced assessment, with scores ranging from strongly negative to strongly positive, enabling users to capture subtle differences in quality or sentiment.   

- Easy to interpret results: 
    - Flow Judge produces structured evaluations with `<feedback>` and `<score>` tags.
        - Qualitative feedback: Flow Judge detects errors and grades outputs and provides qualitative feedback that explains its reasoning for assigning a particular score from the rubric while highlighting problematic parts of the responses. 
        - Score: Based on a grading rubric Flow Judge will return a numerical score on binary, likert-3 or likert-5 scale. 

## Training

### Model

Flow Judge is based on the Phi-3.5-mini architecture, and the base model checkpoint used is specifically its instruct version. The model uses the same tokenizer, supports MQA and Flash Attention 2, and has weights in bfloat16 precision. However, post-finetuning, the model's support for languages and long context lengths has not been fully tested. Due to specialized Supervised Fine-Tuning (SFT), Flow Judge might show different benchmark results and support a maximum context length of 8192, shorter than the base model's. 


### Training Datasets

Flow-Judge-v0.1 has been trained on synthetically generated datasets. The construction of training datasets for Flow Judge involves a multi-step process:

1. Manually curating seed rubrics to serve as a foundation
2. Synthetically generating domain-adapted metrics and rubrics for various domains
3. Synthetically generating training instances with multiple inputs, such as user queries and contextual information
4. Employing a dual-evaluation strategy with consensus to ensure quality and consistency

This process creates a comprehensive and diverse set of training instances that enable accurate, domain-specific evaluations of LLM systems in generative AI products while minimizing human intervention.

Read more about the dataset construction from [here](https://www.flow-ai.com/blog/flow-judge#dataset-construction)


### Fine-tuning

For fine-tuning we used Axolotl's preprocessing to ensure input training data is consistent. We then conducted supervised fine-tuning based on microsoft/Phi-3.5-mini-instruct using RSLoRa. More detailed information about the fine-tuning process is provided in our [technical report](https://www.flow-ai.com/blog/flow-judge#fine-tuning).

## Usage

### Prompt format 

#### Prompt template with inputs 
```text 
# GOAL
Your job is to evaluate a task carried out by an AI system powered by a large language model.
You will be provided with the inputs and output of the task, as well as the evaluation criteria and scoring rubric. Your task is to evaluate the output of the AI system based on the evaluation criteria and scoring rubric provided.

# INPUT
Below are the inputs required for performing the task:
<inputs>
{INPUTS}
</inputs>

# OUTPUT
Below is the output of the task:
<output>
{OUTPUT}
</output>

# EVALUATION CRITERIA AND SCORING RUBRIC
Here are the evaluation criteria and the rubric that you need to use for evaluating the task:
<evaluation_criteria>
{EVALUATION_CRITERIA}
</evaluation_criteria>

<scoring_rubric>
{RUBRIC}
</scoring_rubric>

# INSTRUCTIONS FOR THE EVALUATION
1. Understand the task and criteria: Familiarize yourself with the task to be evaluated. Review the evaluation criteria and scoring rubric to understand the different levels of performance and the descriptions for each score.
2. Review the inputs and output: Look at the inputs provided for the task. Examine the output generated from completing the task.
3. Compare output to score descriptions: Compare the output against the criteria and score descriptions in the scoring rubric. For each criterion,decide which description best matches the output.
4. After comparing the output to the score descriptions, pay attention to the small details that might impact the final score that you assign. Sometimes a small difference can dictate the final score.
5. Write verbal feedback justifying your evaluation that includes a detailed rationale, referring to specific aspects of the output and comparing them to the rubric.
6. Assign a final score based on the scoring rubric.

## FORMAT FOR THE EVALUATION
- Write the verbal feedback inside <feedback> tags without any additional surrounding text.
- Write the numeric score inside <score> tags, without any additional surrounding text and always after the feedback.

Please accurately evaluate the task. Strictly adhere to the evaluation criteria and rubric.
```

#### Prompt template without inputs
```text
# GOAL
Your job is to evaluate a task carried out by an AI system powered by a large language model.

You will be provided the output of the task, as well as the evaluation criteria and scoring rubric. Your task is to evaluate the output of the AI system based on the evaluation criteria and scoring rubric provided.

# OUTPUT
Below is the output of the task:
<output>
{OUTPUT}
</output>

# EVALUATION CRITERIA AND SCORING RUBRIC
Here are the evaluation criteria and the rubric that you need to use for evaluating the task:
<evaluation_criteria>
{EVALUATION_CRITERIA}
</evaluation_criteria>

<scoring_rubric>
{RUBRIC}
</scoring_rubric>

# INSTRUCTIONS FOR THE EVALUATION
1. Understand the task and criteria: Familiarize yourself with the task to be evaluated. Review the evaluation criteria and scoring rubric to understand the different levels of performance and the descriptions for each score.
2. Review the output: Examine the output generated from completing the task.
3. Compare output to score descriptions: Compare the output against the criteria and score descriptions in the scoring rubric. For each criterion,decide which description best matches the output.
4. After comparing the output to the score descriptions, pay attention to the small details that might impact the final score that you assign. Sometimes a small difference can dictate the final score.
5. Write verbal feedback justifying your evaluation that includes a detailed rationale, referring to specific aspects of the output and comparing them to the rubric.
6. Assign a final score based on the scoring rubric.

## FORMAT FOR THE EVALUATION
- Write the verbal feedback inside <feedback> tags without any additional surrounding text.
- Write the numeric score inside <score> tags, without any additional surrounding text and always after the feedback.

Please accurately evaluate the task. Strictly adhere to the evaluation criteria and rubric.
``` 

#### Formatted prompt example with inputs
```text
# GOAL
Your job is to evaluate a task carried out by an AI system powered by a large language model.
You will be provided with the inputs and output of the task, as well as the evaluation criteria and scoring rubric. Your task is to evaluate the output of the AI system based on the evaluation criteria and scoring rubric provided.
# INPUT/s
Below are the inputs required for performing the task:
<inputs>
<customer_query>
Subject: Issues with recent order #12345
Hello,
I recently received my order #12345, but I'm having a few problems:
1. The blue t-shirt I ordered is actually green. Can I exchange it?
2. The phone case doesn't fit my iPhone 13 Pro Max. The website said it was compatible.
3. I was charged for express shipping, but it took over a week to arrive. Can I get a refund on the shipping cost?
Please let me know how we can resolve these issues. I've been a loyal customer for years and this is the first time I've had problems like this.
Thank you,
Jane Smith
</customer_query>
</inputs>

# OUTPUT
Below is the output of the task:
<output>
Dear Jane Smith,
Thank you for reaching out about the issues with your recent order #12345. We sincerely apologize for the inconvenience you've experienced. Let me address each of your concerns:
1. T-shirt color discrepancy: We're sorry about the mix-up with the t-shirt color. We'd be happy to exchange it for the correct blue t-shirt. I'll send you a prepaid return label for the green shirt, and we'll ship out the blue one as soon as we receive the return.
2. Phone case compatibility: We apologize for the confusion regarding the phone case compatibility. Our website information should have been more accurate. We'll gladly accept a return of the incompatible case and issue a full refund for it. Additionally, I can recommend a case that will fit your iPhone 13 Pro Max if you're interested.
3. Shipping charge: You're absolutely right about the shipping charge. Since the delivery didn't meet our express shipping standards, we will refund the entire shipping cost to your original payment method. This refund should process within 3-5 business days.
To initiate these resolutions, please reply to this email confirming that you'd like to proceed with the t-shirt exchange and phone case return. Once confirmed, I'll send you the necessary return labels and process the shipping refund immediately.
We truly value your loyalty as a long-time customer and sincerely regret that you've encountered these issues. Rest assured, we're taking steps to prevent similar problems in the future. As a gesture of goodwill, we'd like to offer you a 20% discount on your next order.
If you have any further questions or concerns, please don't hesitate to reach out. We're here to ensure your complete satisfaction.
Best regards,
Alex Johnson
Customer Service Representative
</output>

# EVALUATION CRITERIA AND SCORING RUBRIC
Here are the evaluation criteria and the rubric that you need to use for evaluating the task:
<evaluation_criteria>
How well the response addresses the specific issues raised in the customer's query?
</evaluation_criteria>
<scoring_rubric>
- Score 1: The response completely fails to address the customer's needs and ignores the specific issues raised.
- Score 2: The response barely addresses the customer's query and misses most of the specific issues raised.
- Score 3: The response partially addresses the customer's query, touching on some of the specific issues but leaving others unaddressed.
- Score 4: The response adequately addresses most aspects of the customer's query and the specific issues raised.
- Score 5: The response fully and comprehensively addresses all aspects of the customer's query and all specific issues raised in a highly satisfactory manner.
</scoring_rubric>

# INSTRUCTIONS FOR THE EVALUATION
1. Understand the task and criteria: Familiarize yourself with the task to be evaluated. Review the evaluation criteria and scoring rubric to understand the different levels of performance and the descriptions for each score.
2. Review the inputs and output: Look at the inputs provided for the task. Examine the output generated from completing the task.
3. Compare output to score descriptions: Compare the output against the criteria and score descriptions in the scoring rubric. For each criterion,decide which description best matches the output.
4. After comparing the output to the score descriptions, pay attention to the small details that might impact the final score that you assign. Sometimes a small difference can dictate the final score.
5. Write verbal feedback justifying your evaluation that includes a detailed rationale, referring to specific aspects of the output and comparing them to the rubric.
6. Assign a final score based on the scoring rubric.

## FORMAT FOR THE EVALUATION
- Write the verbal feedback inside <feedback> tags without any additional surrounding text.
- Write the numeric score inside <score> tags, without any additional surrounding text and always after the feedback.
Please accurately evaluate the task. Strictly adhere to the evaluation criteria and rubric.
```
>Note that inputs and output are formatted with XML tags. See [flow-judge](https://github.com/flowaicom/flow-judge) repository formatting functions for more details.

### Inference

Evaluations can easily be run using our [flow-judge](https://github.com/flowaicom/flow-judge) library. It currently supports both Transformers and vllm engine.

To run Flow Judge efficiently, ensure your hardware meets the following requirements:

- Modern GPU with at least 4 GB VRAM (e.g., NVIDIA RTX series)
- Minimum of 8 GB of system memory
- At least 10GB of free storage for model files and dependencies.

## Evaluation
### Held-out test sets  

<table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: auto;">
  <thead>
    <tr>
      <th rowspan="2" style="text-align: left;">Evaluator</th>
      <th colspan="3" style="text-align: center;">Pass / Fail Held-out Test set</th>
    </tr>
    <tr>
      <th style="text-align: center;">Precision</th>
      <th style="text-align: center;">Recall</th>
      <th style="text-align: center;">F1</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="text-align: left;">microsoft/Phi-3.5-mini-instruct</td>
      <td style="text-align: center;">0.685</td>
      <td style="text-align: center;"><strong>1.000</strong></td>
      <td style="text-align: center;">0.813</td>
    </tr>
    <tr>
      <td style="text-align: left;">meta-llama/Meta-Llama-3.1-8B-Instruct</td>
      <td style="text-align: center;"><u>0.870</u></td>
      <td style="text-align: center;">0.982</td>
      <td style="text-align: center;"><u>0.923</u></td>
    </tr>
    <tr>
      <td style="text-align: left;">mistralai/Mistral-Nemo-Instruct-2407</td>
      <td style="text-align: center;">0.709</td>
      <td style="text-align: center;"><u>0.994</u></td>
      <td style="text-align: center;">0.827</td>
    </tr>
    <tr>
      <td style="text-align: left;">gpt-4o-mini</td>
      <td style="text-align: center;">0.834</td>
      <td style="text-align: center;">1.000</td>
      <td style="text-align: center;">0.910</td>
    </tr>
    <tr>
      <td style="text-align: left;">flowaicom/Flow-Judge-v0.1</td>
      <td style="text-align: center;"><strong>0.940</strong></td>
      <td style="text-align: center;">0.972</td>
      <td style="text-align: center;"><strong>0.955</strong></td>
    </tr>
  </tbody>
</table>

<table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: auto;">
  <thead>
    <tr>
      <th rowspan="2" style="text-align: left;">Evaluator</th>
      <th colspan="3" style="text-align: center;">3-Likert Held-out Test set</th>
      <th colspan="3" style="text-align: center;">5-Likert Held-out Test set</th>
    </tr>
    <tr>
      <th style="text-align: center;">pearsonr</th>
      <th style="text-align: center;">spearmanr</th>
      <th style="text-align: center;">kendall-tau</th>
      <th style="text-align: center;">pearsonr</th>
      <th style="text-align: center;">spearmanr</th>
      <th style="text-align: center;">kendall-tau</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="text-align: left;">microsoft/Phi-3.5-mini-instruct</td>
      <td style="text-align: center;">0.756</td>
      <td style="text-align: center;">0.749</td>
      <td style="text-align: center;">0.695</td>
      <td style="text-align: center;">0.808</td>
      <td style="text-align: center;">0.819</td>
      <td style="text-align: center;">0.739</td>
    </tr>
    <tr>
      <td style="text-align: left;">prometheus-eval/prometheus-7b-v2.0*</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;"><u>0.910</u></td>
      <td style="text-align: center;"><u>0.908</u></td>
      <td style="text-align: center;"><u>0.838</u></td>
    </tr>
    <tr>
      <td style="text-align: left;">meta-llama/Meta-Llama-3.1-8B-Instruct</td>
      <td style="text-align: center;"><u>0.836</u></td>
      <td style="text-align: center;"><u>0.833</u></td>
      <td style="text-align: center;"><u>0.789</u></td>
      <td style="text-align: center;">0.854</td>
      <td style="text-align: center;">0.868</td>
      <td style="text-align: center;">0.791</td>
    </tr>
    <tr>
      <td style="text-align: left;">mistralai/Mistral-Nemo-Instruct-2407</td>
      <td style="text-align: center;">0.813</td>
      <td style="text-align: center;">0.807</td>
      <td style="text-align: center;">0.758</td>
      <td style="text-align: center;">0.870</td>
      <td style="text-align: center;">0.867</td>
      <td style="text-align: center;">0.789</td>
    </tr>
    <tr>
      <td style="text-align: left;">gpt-4o-mini</td>
      <td style="text-align: center;">0.890</td>
      <td style="text-align: center;">0.888</td>
      <td style="text-align: center;">0.851</td>
      <td style="text-align: center;">0.923</td>
      <td style="text-align: center;">0.923</td>
      <td style="text-align: center;">0.864</td>
    </tr>
    <tr>
      <td style="text-align: left;">flowaicom/Flow-Judge-v0.1</td>
      <td style="text-align: center;"><strong>0.888</strong></td>
      <td style="text-align: center;"><strong>0.888</strong></td>
      <td style="text-align: center;"><strong>0.852</strong></td>
      <td style="text-align: center;"><strong>0.919</strong></td>
      <td style="text-align: center;"><strong>0.919</strong></td>
      <td style="text-align: center;"><strong>0.856</strong></td>
    </tr>
  </tbody>
</table>

\* _Reported in model paper_


### RAGTruth
<table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: auto;">
  <tr>
    <th rowspan="2" style="text-align: left;">Evaluator</th>
    <th colspan="3" style="text-align:center;">RAGTruth QA</th>
    <th colspan="3" style="text-align:center;">RAGTruth Data-to-Text</th>
    <th colspan="3" style="text-align:center;">RAGTruth Summarization</th>
  </tr>
  <tr>
    <th style="text-align:center;">Precision</th>
    <th style="text-align:center;">Recall</th>
    <th style="text-align:center;">F1</th>
    <th style="text-align:center;">Precision</th>
    <th style="text-align:center;">Recall</th>
    <th style="text-align:center;">F1</th>
    <th style="text-align:center;">Precision</th>
    <th style="text-align:center;">Recall</th>
    <th style="text-align:center;">F1</th>
  </tr>
  <tr>
    <td>microsoft/Phi-3.5-mini-instruct</td>
    <td style="text-align:center;">0.817</td>
    <td style="text-align:center;">0.963</td>
    <td style="text-align:center;">0.884</td>
    <td style="text-align:center;">0.356</td>
    <td style="text-align:center;"><strong>1.000</strong></td>
    <td style="text-align:center;">0.525</td>
    <td style="text-align:center;">0.776</td>
    <td style="text-align:center;"><strong>1.000</strong></td>
    <td style="text-align:center;"><strong>0.874</strong></td>
  </tr>
  <tr>
    <td>meta-llama/Meta-Llama-3.1-8B-Instruct</td>
    <td style="text-align:center;"><strong>0.844</strong></td>
    <td style="text-align:center;"><u>0.986</u></td>
    <td style="text-align:center;"><strong>0.910</strong></td>
    <td style="text-align:center;">0.382</td>
    <td style="text-align:center;">0.537</td>
    <td style="text-align:center;">0.447</td>
    <td style="text-align:center;"><u>0.797</u></td>
    <td style="text-align:center;"><u>0.940</u></td>
    <td style="text-align:center;">0.863</td>
  </tr>
  <tr>
    <td>mistralai/Mistral-Nemo-Instruct-2407</td>
    <td style="text-align:center;">0.821</td>
    <td style="text-align:center;"><strong>0.995</strong></td>
    <td style="text-align:center;"><u>0.900</u></td>
    <td style="text-align:center;">0.357</td>
    <td style="text-align:center;"><strong>1.000</strong></td>
    <td style="text-align:center;">0.526</td>
    <td style="text-align:center;">0.775</td>
    <td style="text-align:center;"><strong>1.000</strong></td>
    <td style="text-align:center;"><u>0.873</u></td>
  </tr>
  <tr>
    <td>gpt-4o-mini</td>
    <td style="text-align:center;">0.830</td>
    <td style="text-align:center;">0.966</td>
    <td style="text-align:center;">0.893</td>
    <td style="text-align:center;">0.398</td>
    <td style="text-align:center;">0.994</td>
    <td style="text-align:center;">0.569</td>
    <td style="text-align:center;">0.786</td>
    <td style="text-align:center;">0.997</td>
    <td style="text-align:center;">0.879</td>
  </tr>
  <tr>
    <td>Luna*</td>
    <td style="text-align:center;">0.378</td>
    <td style="text-align:center;">0.800</td>
    <td style="text-align:center;">0.513</td>
    <td style="text-align:center;">0.649</td>
    <td style="text-align:center;">0.912</td>
    <td style="text-align:center;"><u>0.759</u></td>
    <td style="text-align:center;">0.400</td>
    <td style="text-align:center;">0.765</td>
    <td style="text-align:center;">0.525</td>
  </tr>
  <tr>
    <td>RAGAS Faithfuless*</td>
    <td style="text-align:center;">0.312</td>
    <td style="text-align:center;">0.419</td>
    <td style="text-align:center;">0.357</td>
    <td style="text-align:center;"><strong>0.792</strong></td>
    <td style="text-align:center;">0.508</td>
    <td style="text-align:center;">0.619</td>
    <td style="text-align:center;">0.642</td>
    <td style="text-align:center;">0.299</td>
    <td style="text-align:center;">0.408</td>
  </tr>
  <tr>
    <td>Trulens Groundedness*</td>
    <td style="text-align:center;">0.228</td>
    <td style="text-align:center;">0.925</td>
    <td style="text-align:center;">0.366</td>
    <td style="text-align:center;"><u>0.669</u></td>
    <td style="text-align:center;"><u>0.965</u></td>
    <td style="text-align:center;"><strong>0.790</strong></td>
    <td style="text-align:center;">0.402</td>
    <td style="text-align:center;">0.500</td>
    <td style="text-align:center;">0.445</td>
  </tr>
  <tr>
    <td>flowaicom/Flow-Judge-v0.1</td>
    <td style="text-align:center;"><u>0.835</u></td>
    <td style="text-align:center;">0.961</td>
    <td style="text-align:center;">0.894</td>
    <td style="text-align:center;">0.541</td>
    <td style="text-align:center;">0.249</td>
    <td style="text-align:center;">0.341</td>
    <td style="text-align:center;"><strong>0.834</strong></td>
    <td style="text-align:center;">0.836</td>
    <td style="text-align:center;">0.835</td>
  </tr>
</table>

\* _reported in model paper_


### HaluEval, Covid-QA, PubMedQA 
<table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: auto;">
  <thead>
    <tr>
      <th rowspan="2" style="text-align: left;">Evaluator</th>
      <th colspan="4" style="text-align: center;">HaluEval</th>
      <th colspan="4" style="text-align: center;">Covid-QA</th>
      <th colspan="4" style="text-align: center;">PubMedQA</th>
    </tr>
    <tr>
      <th style="text-align: center;">Precision</th>
      <th style="text-align: center;">Recall</th>
      <th style="text-align: center;">F1</th>
      <th style="text-align: center;">Accuracy</th>
      <th style="text-align: center;">Precision</th>
      <th style="text-align: center;">Recall</th>
      <th style="text-align: center;">F1</th>
      <th style="text-align: center;">Accuracy</th>
      <th style="text-align: center;">Precision</th>
      <th style="text-align: center;">Recall</th>
      <th style="text-align: center;">F1</th>
      <th style="text-align: center;">Accuracy</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="text-align: left;">microsoft/Phi-3.5-mini-instruct</td>
      <td style="text-align: center;">0.730</td>
      <td style="text-align: center;"><u>0.914</u></td>
      <td style="text-align: center;">0.812</td>
      <td style="text-align: center;">0.788</td>
      <td style="text-align: center;">0.617</td>
      <td style="text-align: center;">0.964</td>
      <td style="text-align: center;">0.752</td>
      <td style="text-align: center;">0.681</td>
      <td style="text-align: center;">0.623</td>
      <td style="text-align: center;"><u>0.986</u></td>
      <td style="text-align: center;">0.764</td>
      <td style="text-align: center;">0.696</td>
    </tr>
    <tr>
      <td style="text-align: left;">meta-llama/Meta-Llama-3.1-8B-Instruct</td>
      <td style="text-align: center;"><strong>0.864</strong></td>
      <td style="text-align: center;">0.891</td>
      <td style="text-align: center;"><strong>0.878</strong></td>
      <td style="text-align: center;"><u>0.874</u></td>
      <td style="text-align: center;"><u>0.663</u></td>
      <td style="text-align: center;"><u>0.976</u></td>
      <td style="text-align: center;"><u>0.790</u></td>
      <td style="text-align: center;">0.734</td>
      <td style="text-align: center;"><u>0.681</u></td>
      <td style="text-align: center;">0.962</td>
      <td style="text-align: center;"><strong>0.797</strong></td>
      <td style="text-align: center;">0.750</td>
    </tr>
    <tr>
      <td style="text-align: left;">mistralai/Mistral-Nemo-Instruct-2407</td>
      <td style="text-align: center;">0.655</td>
      <td style="text-align: center;"><strong>0.993</strong></td>
      <td style="text-align: center;">0.789</td>
      <td style="text-align: center;">0.735</td>
      <td style="text-align: center;">0.651</td>
      <td style="text-align: center;"><strong>0.982</strong></td>
      <td style="text-align: center;">0.783</td>
      <td style="text-align: center;">0.728</td>
      <td style="text-align: center;">0.602</td>
      <td style="text-align: center;"><strong>0.994</strong></td>
      <td style="text-align: center;"><u>0.750</u></td>
      <td style="text-align: center;">0.669</td>
    </tr>
    <tr>
      <td style="text-align: left;">gpt-4o-mini</td>
      <td style="text-align: center;">0.846</td>
      <td style="text-align: center;">0.940</td>
      <td style="text-align: center;">0.891</td>
      <td style="text-align: center;">0.885</td>
      <td style="text-align: center;">0.795</td>
      <td style="text-align: center;">0.964</td>
      <td style="text-align: center;">0.872</td>
      <td style="text-align: center;">0.858</td>
      <td style="text-align: center;">0.791</td>
      <td style="text-align: center;">0.904</td>
      <td style="text-align: center;">0.843</td>
      <td style="text-align: center;">0.832</td>
    </tr>
    <tr>
      <td style="text-align: left;">flowaicom/Flow-Judge-v0.1</td>
      <td style="text-align: center;"><u>0.826</u></td>
      <td style="text-align: center;">0.895</td>
      <td style="text-align: center;"><u>0.859</u></td>
      <td style="text-align: center;">0.854</td>
      <td style="text-align: center;"><strong>0.767</strong></td>
      <td style="text-align: center;">0.877</td>
      <td style="text-align: center;"><strong>0.818</strong></td>
      <td style="text-align: center;">0.807</td>
      <td style="text-align: center;"><strong>0.874</strong></td>
      <td style="text-align: center;">0.624</td>
      <td style="text-align: center;">0.728</td>
      <td style="text-align: center;">0.767</td>
    </tr>
    <tr>
      <td style="text-align: left;">gpt-4o*</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.879</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.821</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.821</td>
    </tr>
    <tr>
      <td style="text-align: left;">Claude 3 Sonnet*</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.845</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.829</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.829</td>
    </tr>
    <tr>
      <td style="text-align: left;">RAGAS Faithfulness*</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.706</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.750</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.669</td>
    </tr>
    <tr>
      <td style="text-align: left;">Lynx 8B*</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">0.857</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;"><u>0.963</u></td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;"><u>0.852</u></td>
    </tr>
    <tr>
      <td style="text-align: left;">Lynx 70B*</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;"><strong>0.884</strong></td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;"><strong>0.975</strong></td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;">-</td>
      <td style="text-align: center;"><strong>0.904</strong></td>
    </tr>
  </tbody>
</table>

\* _reported in model paper_
### Feedback Bench 

<table border="1" cellpadding="10" cellspacing="0" style="border-collapse: collapse; width: auto;">
  <tr>
    <th rowspan="2">Evaluator</th>
    <th colspan="3" style="text-align:center;">Feedback bench</th>
  </tr>
  <tr>
    <th style="text-align:center;">pearsonr</th>
    <th style="text-align:center;">spearmanr</th>
    <th style="text-align:center;">kendall-tau</th>
  </tr>
  <tr>
    <td>microsoft/Phi-3.5-mini-instruct</td>
    <td style="text-align:center;">0.710</td>
    <td style="text-align:center;">0.721</td>
    <td style="text-align:center;">0.622</td>
  </tr>
  <tr>
    <td>prometheus-eval/prometheus-7b-v2.0*</td>
    <td style="text-align:center;"><strong>0.878</strong></td>
    <td style="text-align:center;"><strong>0.909</strong></td>
    <td style="text-align:center;"><strong>0.773</strong></td>
  </tr>
  <tr>
    <td>meta-llama/Meta-Llama-3.1-8B-Instruct</td>
    <td style="text-align:center;">0.742</td>
    <td style="text-align:center;">0.749</td>
    <td style="text-align:center;">0.654</td>
  </tr>
  <tr>
    <td>mistralai/Mistral-Nemo-Instruct-2407</td>
    <td style="text-align:center;">0.720</td>
    <td style="text-align:center;">0.724</td>
    <td style="text-align:center;">0.632</td>
  </tr>
  <tr>
    <td>gpt-4o-mini</td>
    <td style="text-align:center;">0.797</td>
    <td style="text-align:center;">0.795</td>
    <td style="text-align:center;">0.701</td>
  </tr>
  <tr>
    <td>flowaicom/Flow-Judge-v0.1</td>
    <td style="text-align:center;"><u>0.787</u></td>
    <td style="text-align:center;"><u>0.789</u></td>
    <td style="text-align:center;"><u>0.688</u></td>
  </tr>
</table>

\* _reported in model paper using reference answers_

## License
We opted for the Apache 2.0 license for Flow Judge to provide the community with an open, small yet powerful LM evaluator. Our goal is to support the wider adoption of rigorous evaluation techniques in LLM system development, making them more accessible to practitioners and researchers.

## Limitations and future work
Multilingual evaluation: Flow Judge has been fine-tuned exclusively on English data. While the foundation model (Phi-3.5-mini-instruct [17]) may possess multilingual capabilities, we have not systematically evaluated Flow Judge performance in non-English contexts. We plan to explore multi-lingual LM evaluators in the future.

Long context and structured Inputs: Our training dataset encompasses a wide range of custom metrics relevant to evaluating LLM systems. However, it does not include examples with long context inputs or structured data formats such as JSON, since these are harder to synthetically generate. This limitation may impact Flow Judge's performance when evaluating responses that require processing extensive context or parsing structured input. Extending our model’s capabilities to handle these input types represents an important area for future research.

Math and coding: The current version has not been trained on specific task domains such as arithmetic problems or code evaluation. As a result, its performance in these specialized areas may be limited. Future iterations of the model should address these gaps.

Domain-specific knowledge and complex multi-step evaluations: Flow Judge may struggle with highly specialized domain knowledge or proprietary data outside the training scope of its foundation model. Additionally, evaluation tasks requiring multi-step reasoning or complex logical processes may challenge the model's capabilities. We strongly recommend conducting meta-evaluations of the model performance before deploying it in specialized or highly complex evaluation scenarios.