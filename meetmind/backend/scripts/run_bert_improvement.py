"""Run a fixed BERT-base improvement study; report the actual goal outcome."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
from nlp.data import write_json
from nlp.experiments import comparison
from scripts.run_bert_comparison import run


def assess_goal(summary, target):
    if not math.isfinite(target) or not 0 < target <= 1:
        raise ValueError('Target macro F1 must be in (0, 1]')
    winner = summary['ranked_candidates'][0]
    score = winner['scores']['macro_f1']
    return {'metric':'15-class validation macro F1', 'target':target, 'achieved':score >= target,
            'measured_macro_f1':score, 'selected_report':winner['report'],
            'gain_over_reference':summary['selected_macro_f1_gain'],
            'test_used_for_selection':False, 'serving_model_changed':False,
            'note':'Selection uses validation; final test is reserved. A target is not a guaranteed outcome.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--configs', nargs='+', type=Path, required=True)
    parser.add_argument('--reference-run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target', type=float, default=.73)
    args = parser.parse_args()
    if not math.isfinite(args.target) or not 0 < args.target <= 1:
        raise ValueError('Invalid target')
    configs = [json.loads(path.read_text()) for path in args.configs]
    if any(cfg['model'] != 'google-bert/bert-base-uncased' for cfg in configs):
        raise ValueError('This study keeps the BERT-base architecture fixed')
    reference = args.reference_run/'validation.json'
    if not reference.exists():
        subprocess.check_call([sys.executable, '-u', '-m', 'scripts.evaluate_bert',
                               '--checkpoint', str(args.reference_run/'best'), '--data', configs[0]['data'],
                               '--output', str(reference), '--device', 'cuda', '--skip-baselines'])
    if (args.output/'comparison.json').exists():
        # Recompute metrics from all predictions rather than trust a cached score.
        saved = json.loads((args.output/'experiment_plan.json').read_text())
        if saved['configs'] != [str(path) for path in args.configs] or saved['reference'] != str(reference):
            raise ValueError('Completed comparison differs from requested study')
        for path, cfg in zip(args.configs, configs):
            resolved = json.loads((Path(cfg['output'])/'run_config.json').read_text())
            if any(resolved.get(k) != v for k,v in cfg.items()):
                raise ValueError('Completed candidate configuration differs')
        reports = [reference]+[Path(cfg['output'])/'validation.json' for cfg in configs]
        summary = comparison(reports, reference)
    else:
        summary = run(args.configs,args.output,reference,resume=True,skip_baselines=True)
    report = json.loads(reference.read_text())
    if len(report['scores']['bert']['label_order']) != 15:
        raise ValueError('The target is defined for all 15 AMI classes')
    goal = assess_goal(summary,args.target)
    write_json(args.output/'goal.json',goal)
    print(json.dumps(goal,indent=2),flush=True)


if __name__ == '__main__':main()
