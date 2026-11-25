"""One frozen CPU encoder comparison and seven video-held-out validations.

No generated replies are read. Original annotator distributions are preserved;
each unique utterance has total training/evaluation weight one. This detects
observed behavior, never professional appropriateness or helpfulness.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import time
import warnings

from .behavior import ANNOMI_BLOB, fnv1a, read_annomi
from .rs_tasks import deduplicate_utterances, write_once

PROTOCOL = "pmrl1-j-behavior-local-encoder-seven-video-v1"
EXPECTED_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
EXPECTED_WEIGHTS_SHA256 = "3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad"


def sha(path):
    result=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(2**20),b""):
            result.update(chunk)
    return result.hexdigest()


def labels_expanded(rows):
    indices, labels, weights = [], [], []
    for i, row in enumerate(rows):
        annotations=row["annotations"]
        for annotation in annotations:
            indices.append(i)
            labels.append(annotation["main_therapist_behaviour"])
            weights.append(1.0/len(annotations))
    return indices, labels, weights


def score_distribution(rows, predictions, classes):
    from sklearn.metrics import classification_report, confusion_matrix
    true, predicted, weights = [], [], []
    per_annotator=defaultdict(lambda:dict(n=0,correct=0))
    item_scores=[]
    strata=defaultdict(list)
    for row,prediction in zip(rows,predictions):
        labels=[a["main_therapist_behaviour"] for a in row["annotations"]]
        item_score=labels.count(prediction)/len(labels)
        item_scores.append(item_score)
        strata["unanimous" if len(set(labels))==1 else "disagreeing"].append(item_score)
        for annotation in row["annotations"]:
            true.append(annotation["main_therapist_behaviour"])
            predicted.append(prediction)
            weights.append(1/len(labels))
            annotator=per_annotator[annotation["annotator_id"]]
            annotator["n"]+=1
            annotator["correct"]+=int(annotation["main_therapist_behaviour"]==prediction)
    return dict(unique_utterances=len(rows),annotation_rows=len(true),
        expected_accuracy=sum(item_scores)/len(item_scores),
        class_labels=classes,
        fractional_confusion=confusion_matrix(true,predicted,labels=classes,sample_weight=weights).tolist(),
        classification=classification_report(true,predicted,labels=classes,sample_weight=weights,output_dict=True,zero_division=0),
        disagreement_strata={k:dict(n=len(v),expected_accuracy=sum(v)/len(v)) for k,v in strata.items()},
        per_annotator={k:dict(**v,accuracy=v["correct"]/v["n"]) for k,v in sorted(per_annotator.items())})


def run(annomi, model_path, output, *, cpu_seconds=1200):
    start=time.monotonic()
    output=Path(output)
    if output.exists():
        raise FileExistsError("new output directory required; preserve prior comparison")
    model_path=Path(model_path).resolve()
    if model_path.name!=EXPECTED_REVISION:
        raise ValueError("unexpected local BGE-small snapshot")
    weight=model_path/"model.safetensors"
    if sha(weight)!=EXPECTED_WEIGHTS_SHA256:
        raise ValueError("local encoder weights differ")
    for key in ("HF_HUB_OFFLINE","TRANSFORMERS_OFFLINE"):
        os.environ[key]="1"
    os.environ["CUDA_VISIBLE_DEVICES"]=""
    import numpy as np
    import sklearn
    import torch
    import transformers
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from transformers import AutoModel, AutoTokenizer
    torch.set_num_threads(4)
    torch.set_num_interop_threads(1)
    torch.manual_seed(0)
    rows=[r for r in deduplicate_utterances(read_annomi(annomi)) if r["interlocutor"]=="therapist"]
    classes=sorted({a["main_therapist_behaviour"] for r in rows for a in r["annotations"]})
    multi_families=sorted({r["video_family"] for r in rows if len(r["annotations"])>1})
    if len(multi_families)!=7:
        raise ValueError("expected the fixed seven multiply annotated video families")
    identity=dict(protocol=PROTOCOL, source_git_blob=ANNOMI_BLOB, source_sha256=sha(annomi),
        model="BAAI/bge-small-en-v1.5",revision=EXPECTED_REVISION,
        files_sha256={name:sha(model_path/name) for name in ("model.safetensors","config.json","tokenizer.json","tokenizer_config.json","vocab.txt")},
        device="cpu",dtype="float32",cpu_threads=4,batch_size=16,max_length=512,
        pooling="L2-normalized last-layer CLS; no retrieval query instruction",
        classifier=dict(C=1.0,solver="lbfgs",max_iter=2000,random_state=0,class_weight=None),
        tfidf=dict(ngram_range=[1,2],min_df=3,max_features=50000,sublinear_tf=True),
        torch_version=torch.__version__,transformers_version=transformers.__version__,sklearn_version=sklearn.__version__,
        cpu_wall_cap_seconds=cpu_seconds,hyperparameter_search=False,
        representation_fit="encoder frozen; TF-IDF fit separately on each training fold",
        train_weighting="each original annotation weighted 1/n for its unique utterance",
        fold_rule="all other video families train; hold each of seven multiannotated families out once; no same-family train rows",
        prior_development_exposure=True,independent_final_confirmation=False,
        limits=["All source labels were previously exposed in development; held-out-fold fitting is not a pristine confirmatory study.",
                "No GPU, model download, generative judge, clinical outcome or task-reward qualification.",
                "One fixed local encoder comparison; no best-seed/model/hyperparameter selection."])
    write_once(output/"PRECOMMITTED_CONFIG.json",identity)
    tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True,trust_remote_code=False)
    model=AutoModel.from_pretrained(model_path,local_files_only=True,trust_remote_code=False,attn_implementation="eager").to("cpu").eval()
    texts=[r["utterance_text"] for r in rows]
    lengths=[len(tokenizer.encode(t,add_special_tokens=True,truncation=False)) for t in texts]
    order=sorted(range(len(rows)),key=lambda i:(lengths[i],i))
    features=np.empty((len(rows),384),dtype=np.float32)
    encoding_start=time.monotonic()
    with torch.inference_mode():
        for at in range(0,len(order),16):
            if time.monotonic()-start>cpu_seconds:
                write_once(output/"STOPPED.json",dict(reason="precommitted_cpu_wall_limit",encoded=at,total=len(rows)))
                raise TimeoutError("bounded CPU encoder comparison stopped")
            batch_indices=order[at:at+16]
            encoded=tokenizer([texts[i] for i in batch_indices],return_tensors="pt",padding=True,truncation=True,max_length=512)
            embedding=model(**encoded).last_hidden_state[:,0]
            embedding=torch.nn.functional.normalize(embedding,p=2,dim=1).cpu().numpy()
            features[batch_indices]=embedding
            if at%512==0:
                print(json.dumps(dict(event="cpu_embedding_progress",completed=min(at+16,len(rows)),total=len(rows))),flush=True)
    np.save(output/"frozen_encoder_features.private.npy",features)
    encoding=dict(unique_utterances=len(rows),elapsed_seconds=time.monotonic()-encoding_start,
                  truncated_utterances=sum(n>512 for n in lengths),max_original_tokens=max(lengths),
                  omitted_tokens=sum(max(0,n-512) for n in lengths),
                  features_sha256=sha(output/"frozen_encoder_features.private.npy"))
    del model
    folds=[]
    predictions_private=[]

    def fit_and_evaluate(train_indices,test_indices,name):
        train_rows=[rows[i] for i in train_indices];test_rows=[rows[i] for i in test_indices]
        ix,y,w=labels_expanded(train_rows)
        if {r["video_family"] for r in train_rows}&{r["video_family"] for r in test_rows}:
            raise ValueError("video leakage")
        results={}
        for method in ("tfidf_equal_utterance","bge_small_frozen_equal_utterance"):
            if method.startswith("tfidf"):
                vectorizer=TfidfVectorizer(ngram_range=(1,2),min_df=3,max_features=50000,lowercase=True,sublinear_tf=True)
                train_x=vectorizer.fit_transform([r["utterance_text"] for r in train_rows])
                test_x=vectorizer.transform([r["utterance_text"] for r in test_rows])
            else:
                train_x=features[train_indices];test_x=features[test_indices]
            classifier=LogisticRegression(C=1.0,max_iter=2000,random_state=0,solver="lbfgs",class_weight=None)
            with warnings.catch_warnings(record=True) as caught:
                classifier.fit(train_x[ix],y,sample_weight=w)
            pred=classifier.predict(test_x)
            measured=score_distribution(test_rows,pred,classes)
            measured["fit_warnings"]=[str(x.message) for x in caught]
            measured["iterations"]=classifier.n_iter_.tolist()
            multi=[i for i,r in enumerate(test_rows) if len(r["annotations"])>1]
            measured["multiannotator_only"]=score_distribution([test_rows[i] for i in multi],[pred[i] for i in multi],classes) if multi else None
            results[method]=measured
            predictions_private.extend(dict(fold=name,method=method,key=rows[idx]["key"],video_family=rows[idx]["video_family"],
                annotation_distribution=rows[idx]["labels"]["main_therapist_behaviour"]["counts"],
                predicted=str(p)) for idx,p in zip(test_indices,pred))
        return dict(fold=name,train_unique=len(train_rows),test_unique=len(test_rows),train_annotations=len(y),
            train_families=len({r["video_family"] for r in train_rows}),test_families=len({r["video_family"] for r in test_rows}),
            family_overlap=0,results=results)

    train=[i for i,r in enumerate(rows) if fnv1a(r["video_family"])%5!=0]
    test=[i for i,r in enumerate(rows) if fnv1a(r["video_family"])%5==0]
    old_split=fit_and_evaluate(train,test,"old_96_23_development_split")
    write_once(output/"old_split_results.json",old_split)
    for ordinal,held in enumerate(multi_families):
        if time.monotonic()-start>cpu_seconds:
            raise TimeoutError("bounded CPU comparison stopped before all folds")
        train=[i for i,r in enumerate(rows) if r["video_family"]!=held]
        test=[i for i,r in enumerate(rows) if r["video_family"]==held]
        fold=fit_and_evaluate(train,test,f"multi_video_holdout_{ordinal+1}")
        fold["held_video_family_private"]=held
        folds.append(fold)
        print(json.dumps(dict(event="fold_complete",fold=ordinal+1,test_unique=len(test))),flush=True)
    combined={}
    for method in ("tfidf_equal_utterance","bge_small_frozen_equal_utterance"):
        selected=[r for r in predictions_private if r["fold"].startswith("multi_video") and r["method"]==method]
        keyed={tuple(r["key"]):r for r in rows}
        test_rows=[keyed[tuple(p["key"])] for p in selected]
        pred=[p["predicted"] for p in selected]
        combined[method]=score_distribution(test_rows,pred,classes)
    report=dict(protocol=PROTOCOL,model_identity=identity,encoding=encoding,old_split=old_split,
        seven_video_folds=folds,group_out_combined=combined,elapsed_seconds=time.monotonic()-start,
        fully_completed=True,model_selected=False,reward_qualified=False,
        source_private_files_not_for_publication=True)
    write_once(output/"predictions.private.jsonl",predictions_private,lines=True)
    write_once(output/"RESULTS.json",report)
    write_once(output/"MANIFEST.json",dict(protocol=PROTOCOL,files={p.name:sha(p) for p in sorted(output.iterdir())},
        generated_g0e_calls=0,gpu_loads=0,paid_calls=0))
    return report


def uncertainty_from_existing(existing, output):
    """Paired video bootstrap; uses already-produced predictions, no refit."""
    import numpy as np
    existing,output=Path(existing),Path(output)
    rows=[json.loads(x) for x in (existing/"predictions.private.jsonl").read_text().splitlines()]
    selected=[r for r in rows if r["fold"].startswith("multi_video")]
    paired=defaultdict(dict)
    for row in selected:
        counts=row["annotation_distribution"]
        paired[(row["video_family"],tuple(row["key"]))][row["method"]]=counts.get(row["predicted"],0)/sum(counts.values())
    grouped=defaultdict(list)
    for (family,_),scores in paired.items():
        grouped[family].append(scores["bge_small_frozen_equal_utterance"]-scores["tfidf_equal_utterance"])
    families=sorted(grouped)
    rng=np.random.default_rng(20261125)
    boot=[]
    for _ in range(2000):
        chosen=rng.integers(0,len(families),len(families))
        differences=[d for index in chosen for d in grouped[families[index]]]
        boot.append(float(np.mean(differences)))
    report=dict(protocol=PROTOCOL+"-paired-uncertainty-v1",groups=len(families),unique_utterances=len(paired),
        expected_accuracy_difference_bge_minus_tfidf=float(np.mean([d for values in grouped.values() for d in values])),
        video_cluster_percentile_95ci=[float(x) for x in np.quantile(boot,[.025,.975])],
        bootstrap_samples=2000,seed=20261125,predictions_sha256=sha(existing/"predictions.private.jsonl"),
        limits="Seven exposed development video families; descriptive paired uncertainty, not a confirmatory superiority test or task-reward qualification.",
        model_refits=0,new_generation_calls=0)
    write_once(output/"PAIRED_UNCERTAINTY.json",report)
    return report


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annomi");parser.add_argument("--model")
    parser.add_argument("--output",required=True);parser.add_argument("--cpu-seconds",type=int,default=1200)
    parser.add_argument("--summarize-existing")
    args=parser.parse_args()
    if args.summarize_existing:
        print(json.dumps(uncertainty_from_existing(args.summarize_existing,args.output)))
    else:
        if not args.annomi or not args.model:parser.error("--annomi and --model required for the one model comparison")
        report=run(args.annomi,args.model,args.output,cpu_seconds=args.cpu_seconds)
        print(json.dumps(dict(protocol=PROTOCOL,complete=report["fully_completed"],elapsed_seconds=report["elapsed_seconds"])))
