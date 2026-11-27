"""Gold-free official question construction; safe for runtime imports."""
RECALL_SUFFIX = " Please recall my related preferences from our conversation history to give personalized responses."


def instruction(options):
    return ("Please choose the best answer from the following options:\n\n" +
            "\n".join(f"{o['id']}. {o['text']}" for o in options) +
            "\n\nThink step by step about which answer best fits the user's query and conversation context. "
            "Provide your reasoning first, then give your final answer as 'Final Answer: [Letter]'")


def official_messages(task, history):
    """Exact upstream role/order; native backend adaptations must be versioned."""
    messages = list(history) + list(task.current_messages) + [
        {"role":"user", "content":task.user_query + RECALL_SUFFIX}]
    if task.task_mode == "mcq":
        messages.append({"role":"system", "content":instruction(task.options)})
    return messages

