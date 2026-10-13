"""Diagnose recorded validation failures and input truncation; never read final test."""
import argparse
import json
from pathlib import Path
from nlp.data import contextualize,load_split,sha256,write_json
from nlp.encoding import encode_pairs


def audit(data,checkpoint,report,output):
    from transformers import AutoTokenizer
    rows,manifest=load_split(data,'validation')
    recorded=json.loads(Path(report).read_text())
    if recorded['dataset_manifest_sha256'] != sha256(Path(data)/'manifest.json'):
        raise ValueError('Recorded results do not match frozen dataset')
    tokenizer=AutoTokenizer.from_pretrained(checkpoint,local_files_only=True)
    score=recorded['scores']['bert']
    labels=score['label_order']
    per_class=sorted([{'label':label,'support':int(score['per_class'][label]['support']),
                      'f1':score['per_class'][label]['f1-score']} for label in labels],key=lambda r:r['f1'])
    confusions=sorted([{'gold':labels[i],'predicted':labels[j],'count':count}
                       for i,row in enumerate(score['confusion_matrix']) for j,count in enumerate(row)
                       if i!=j and count],key=lambda r:-r['count'])[:12]
    views=[]
    for name,k,length,order,strategy in [('current',2,128,'chronological','longest_first'),
                                       ('context4',4,192,'recent_first','target_first'),
                                       ('context8',8,256,'recent_first','target_first')]:
        view=contextualize(rows,k,order)
        target_lost=context_lost=target_total=0
        for start in range(0,len(rows),128):
            batch=view[start:start+128]
            texts=[r['text'] for r in batch];context=[r['context'] for r in batch]
            targets=tokenizer(texts,add_special_tokens=False,return_length=True,verbose=False)['length']
            full=tokenizer(texts,context,return_length=True,verbose=False)['length']
            encoded=encode_pairs(tokenizer,texts,context,length,strategy=strategy)
            for t,f,types in zip(targets,full,encoded['token_type_ids']):
                kept=types.count(0)-2
                target_lost+=t>kept
                context_lost+=f>len(types)
                target_total+=t-kept
        views.append({'name':name,'context_turns':k,'max_length':length,'pair_truncation':strategy,
                      'rows':len(rows),'target_truncated_rows':target_lost,
                      'any_truncated_rows':context_lost,'target_tokens_removed':target_total})
    result={'scope':'Diagnosis of existing validation results, not a new trained-model score',
            'dataset_manifest_sha256':recorded['dataset_manifest_sha256'],
            'baseline_macro_f1':score['macro_f1'],'baseline_weighted_f1':score['weighted_f1'],
            'target_macro_f1':.73,'test_loaded':False,'classes_by_f1':per_class,
            'largest_confusions':confusions,'input_views':views}
    if Path(output).exists():raise ValueError('Preserve existing audit output')
    write_json(output,result);print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/ami-da-v1'))
    parser.add_argument('--checkpoint',type=Path,default=Path('models/dialogue-bert-base-v1'))
    parser.add_argument('--report',type=Path,default=Path('reports/bert-base-comparison-v1/bert-base-gpu-lr3e5/validation_metrics.json'))
    parser.add_argument('--output',type=Path,default=Path('reports/bert-f1-improvement-v2/input-audit.json'))
    args=parser.parse_args();audit(args.data,args.checkpoint,args.report,args.output)
