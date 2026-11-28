"""Gold-free shared WP3 rendering contract for B runtime and A evaluation."""
PROTOCOL='naa-short-mcq-v1'
MAX_NEW_TOKENS=64
SHORT_SUFFIX=('Please choose the best answer. Reply with exactly one line: Final Answer: A '
              '(replace A with B, C, or D if needed). Do not include brackets or reasoning.')


def instruction(options):
    if [o['id'] for o in options]!=list('ABCD'):raise ValueError('frozen four-option order required')
    return 'Please choose the best answer from the following options:\n\n'+'\n'.join(
        o['id']+'. '+o['text'] for o in options)+'\n\n'+SHORT_SUFFIX
