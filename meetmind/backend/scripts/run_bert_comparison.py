"""Run full BERT-base candidates, evaluate validation, and compare without loading test."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from nlp.data import write_json
from scripts.compare_bert import compare


def run(configs, output, reference=None, resume=False):
    output = Path(output)
    if (output / 'comparison.json').exists():
        raise ValueError('Comparison already finished; preserve its evidence')
    reports = [Path(reference)] if reference else []
    for config in configs:
        cfg = json.loads(Path(config).read_text(encoding='utf-8'))
        if cfg.get('stage') != 'full-training-candidate' or cfg.get('max_train_examples', 0):
            raise ValueError('Use full-data BERT-base candidate configurations')
        directory = Path(cfg['output'])
        state = directory / 'status.json'
        completed = state.is_file() and json.loads(state.read_text(encoding='utf-8'))['status'] == 'completed'
        command = [sys.executable, '-u', '-m', 'scripts.train_bert', '--config', str(config)]
        if not completed:
            if resume and (directory / 'run_config.json').is_file():
                command.append('--resume')
            subprocess.check_call(command)
        else:
            saved = json.loads((directory / 'run_config.json').read_text(encoding='utf-8'))
            if any(saved.get(k) != v for k, v in cfg.items()):
                raise ValueError('Completed run configuration differs from requested candidate')
        report = directory / 'validation.json'
        if not report.exists():
            subprocess.check_call([sys.executable, '-u', '-m', 'scripts.evaluate_bert',
                                   '--checkpoint', str(directory / 'best'), '--data', cfg['data'],
                                   '--split', 'validation', '--output', str(report)])
        reports.append(report)
    result = compare(reports, output, reference)
    write_json(output / 'experiment_plan.json', {'configs': [str(p) for p in configs],
               'reference': str(reference) if reference else None, 'test_evaluated': False,
               'selected_report': result['selected_report']})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configs', nargs='+', type=Path, required=True)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    run(args.configs, args.output, args.reference, args.resume)
