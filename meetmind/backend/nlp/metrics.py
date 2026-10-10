from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score


def classification_metrics(gold, predicted, labels):
    return {'accuracy': accuracy_score(gold, predicted),
            'macro_f1': f1_score(gold, predicted, labels=labels, average='macro', zero_division=0),
            'weighted_f1': f1_score(gold, predicted, labels=labels, average='weighted', zero_division=0),
            'per_class': classification_report(gold, predicted, labels=labels, output_dict=True, zero_division=0),
            'confusion_matrix': confusion_matrix(gold, predicted, labels=labels).tolist(),
            'label_order': labels, 'examples': len(gold)}
