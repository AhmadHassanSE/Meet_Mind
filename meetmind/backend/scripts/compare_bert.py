"""Compare actually evaluated checkpoints on matching validation rows."""
import argparse
from pathlib import Path
from nlp.data import write_json
from nlp.experiments import comparison


def compare(reports, output, reference=None):
    output = Path(output)
    if output.exists():
        raise ValueError('Choose a new comparison output; preserve previous evidence')
    result = comparison(reports, reference)
    write_json(output / 'comparison.json', result)
    rows = ['| Model/run | Training rows | Macro F1 | Accuracy |', '|---|---:|---:|---:|']
    for candidate in result['ranked_candidates']:
        name = (candidate['model_name'] or candidate['report']).replace('|', '\\|')
        rows.append(f"| {name} | {candidate['train_examples']} | {candidate['scores']['macro_f1']:.4f} | {candidate['scores']['accuracy']:.4f} |")
    (output / 'comparison.md').write_text('# Validation comparison\n\n' + '\n'.join(rows) +
        '\n\nSelection uses validation macro F1. Training budget differences are not controlled architecture comparisons. No test results were used.\n', encoding='utf-8')
    print((output / 'comparison.md').read_text(encoding='utf-8'))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, nargs='+', required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    compare(args.reports, args.output, args.reference)
