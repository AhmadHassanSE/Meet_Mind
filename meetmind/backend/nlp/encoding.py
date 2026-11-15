"""Identical target-preserving BERT pair encoding for training and serving."""


def encode_pairs(tokenizer, texts, contexts, max_length, *, strategy='longest_first',
                 padding=False, return_tensors=None):
    if strategy == 'longest_first':
        return tokenizer(texts, contexts, truncation='longest_first', max_length=max_length,
                         padding=padding, return_tensors=return_tensors)
    if strategy != 'target_first':
        raise ValueError('Unknown pair truncation strategy')
    if len(texts) != len(contexts):
        raise ValueError('Target and context counts differ')
    budget = max_length - tokenizer.num_special_tokens_to_add(pair=True)
    if budget < 1:
        raise ValueError('Sequence length must retain at least one target token')
    targets = tokenizer(texts, add_special_tokens=False, verbose=False)['input_ids']
    histories = tokenizer(contexts, add_special_tokens=False, verbose=False)['input_ids']
    encoded = []
    for target, context in zip(targets, histories):
        target = target[:budget]
        context = context[:budget-len(target)]
        ids = tokenizer.build_inputs_with_special_tokens(target, context)
        encoded.append({'input_ids': ids, 'attention_mask': [1]*len(ids),
                        'token_type_ids': tokenizer.create_token_type_ids_from_sequences(target, context)})
    return tokenizer.pad(encoded, padding=padding, return_tensors=return_tensors)
