"""CPU-only observed-behaviour baseline; never a support-quality reward.

The URL split exactly follows the supplied web probe. Hyperparameters below are
fixed before inspecting this development split; no search or outcome selection.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from pathlib import Path

ANNOMI_BLOB = "dd8aba7b07953bf6c37c3e6e4771485e62e36b32"
PROTOCOL = "pmrl1-j-observed-behavior-tfidf-logistic-v1"


def family(url):
    url = re.sub(r"^https?://(www\.)?", "", url.strip())
    url = re.sub(r"#.*$", "", url)
    return re.sub(r"&(?:t|start)=.*$", "", url)


def fnv1a(text):
    value = 2166136261
    # URLs in the fixed source are ASCII, matching the JavaScript probe exactly.
    for char in text:
        value = ((value ^ ord(char)) * 16777619) & 0xFFFFFFFF
    return value


def read_annomi(path):
    data = Path(path).read_bytes()
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if blob != ANNOMI_BLOB:
        raise ValueError("AnnoMI Git blob mismatch: " + blob)
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def _write_once(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def train_baseline(source, output):
    import joblib
    import sklearn
    from sklearn.dummy import DummyClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
    from sklearn.pipeline import make_pipeline

    output = Path(output)
    if output.exists():
        raise FileExistsError("refuse to overwrite frozen behavior output")
    rows = [r for r in read_annomi(source) if r["interlocutor"] == "therapist"]
    train = [r for r in rows if fnv1a(family(r["video_url"])) % 5 != 0]
    test = [r for r in rows if fnv1a(family(r["video_url"])) % 5 == 0]
    train_groups = {family(r["video_url"]) for r in train}
    test_groups = {family(r["video_url"]) for r in test}
    assert not train_groups & test_groups
    xtrain = [r["utterance_text"] for r in train]
    xtest = [r["utterance_text"] for r in test]
    ytrain = [r["main_therapist_behaviour"] for r in train]
    ytest = [r["main_therapist_behaviour"] for r in test]
    labels = sorted(set(ytrain))
    params = dict(ngram_range=(1, 2), min_df=3, max_features=50000,
                  lowercase=True, sublinear_tf=True)
    classifier_params = dict(C=1.0, max_iter=2000, random_state=0,
                             solver="lbfgs", class_weight=None)
    model = make_pipeline(TfidfVectorizer(**params), LogisticRegression(**classifier_params))
    model.fit(xtrain, ytrain)
    predictions = model.predict(xtest)
    majority = DummyClassifier(strategy="most_frequent").fit([[0]] * len(train), ytrain)
    majority_predictions = majority.predict([[0]] * len(test))

    def metrics(predicted):
        return dict(correct=sum(p == y for p, y in zip(predicted, ytest)), n=len(test),
                    accuracy=accuracy_score(ytest, predicted),
                    classification=classification_report(ytest, predicted, labels=labels,
                                                        output_dict=True, zero_division=0),
                    labels=labels, confusion=confusion_matrix(ytest, predicted, labels=labels).tolist())

    result = dict(protocol=PROTOCOL, source_git_blob=ANNOMI_BLOB,
                  source_sha256=hashlib.sha256(Path(source).read_bytes()).hexdigest(),
                  sklearn_version=sklearn.__version__, vectorizer=params,
                  classifier=classifier_params, train=len(train), test=len(test),
                  train_groups=len(train_groups), test_groups=len(test_groups), group_overlap=0,
                  split="FNV-1a(normalized video URL) modulo 5 == 0: development test",
                  tfidf_logistic=metrics(predictions), majority=metrics(majority_predictions),
                  reward_qualified=False, prior_web_development_exposure=True,
                  limitations=["Observed response behavior recognition, not next-action appropriateness.",
                               "No generated G0e response or clinical/helpfulness inference.",
                               "URL family grouping does not verify independent practitioners.",
                               "No held-out calibration or semantic task-reward qualification."])
    _write_once(output / "metrics.json", result)
    _write_once(output / "predictions.private.json", [dict(transcript_id=r["transcript_id"],
                     utterance_id=r["utterance_id"], video_family=family(r["video_url"]),
                     observed=r["main_therapist_behaviour"], predicted=str(p)) for r, p in zip(test, predictions)])
    joblib.dump(model, output / "model.private.joblib")
    _write_once(output / "model_identity.json", dict(model_sha256=hashlib.sha256(
        (output / "model.private.joblib").read_bytes()).hexdigest(), protocol=PROTOCOL))
    return result


def train_utterance_baseline(source, output, row_model):
    """Equal-utterance training preserving each annotator's label distribution.

    TF-IDF is fit once per unique utterance. Logistic training expands its
    annotations with 1/n weight, exactly a soft-label cross-entropy objective.
    Ties and disagreement remain in labels; no consensus filtering is applied.
    """
    from collections import Counter, defaultdict
    import joblib
    import numpy as np
    import sklearn
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.pipeline import make_pipeline
    from .rs_tasks import deduplicate_utterances

    output = Path(output)
    if output.exists():
        raise FileExistsError("refuse to overwrite unique-utterance output")
    rows = read_annomi(source)
    utterances = deduplicate_utterances(rows)
    therapists = [u for u in utterances if u["interlocutor"] == "therapist"]
    train = [u for u in therapists if fnv1a(u["video_family"]) % 5 != 0]
    test = [u for u in therapists if fnv1a(u["video_family"]) % 5 == 0]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=50000,
                                 lowercase=True, sublinear_tf=True)
    matrix = vectorizer.fit_transform([u["utterance_text"] for u in train])
    indices, labels, weights = [], [], []
    for i, row in enumerate(train):
        n = len(row["annotations"])
        for annotation in row["annotations"]:
            indices.append(i)
            labels.append(annotation["main_therapist_behaviour"])
            weights.append(1.0 / n)
    classifier = LogisticRegression(C=1.0, max_iter=2000, random_state=0, solver="lbfgs", class_weight=None)
    classifier.fit(matrix[indices], labels, sample_weight=weights)
    model = make_pipeline(vectorizer, classifier)
    predictions = model.predict([u["utterance_text"] for u in test])
    old_model = joblib.load(row_model)
    old_predictions = old_model.predict([u["utterance_text"] for u in test])
    classes = sorted(set(labels))

    def evaluate(predicted):
        actual, expanded_predicted, sample_weights = [], [], []
        by_annotator = defaultdict(lambda: dict(n=0, correct=0))
        unique_scores, per_family = [], defaultdict(list)
        unanimous_actual, unanimous_predicted, consensus_actual, consensus_predicted = [], [], [], []
        multi_scores, ties = [], 0
        for row, prediction in zip(test, predicted):
            annotations = row["annotations"]
            counts = Counter(a["main_therapist_behaviour"] for a in annotations)
            score = counts[prediction] / len(annotations)
            unique_scores.append(score)
            per_family[row["video_family"]].append(score)
            if len(annotations) > 1:
                multi_scores.append(score)
            for annotation in annotations:
                actual.append(annotation["main_therapist_behaviour"])
                expanded_predicted.append(prediction)
                sample_weights.append(1 / len(annotations))
                a = by_annotator[annotation["annotator_id"]]
                a["n"] += 1
                a["correct"] += int(annotation["main_therapist_behaviour"] == prediction)
            winners = [k for k, n in counts.items() if n == max(counts.values())]
            if len(winners) == 1:
                consensus_actual.append(winners[0]); consensus_predicted.append(prediction)
            else:
                ties += 1
            if len(counts) == 1:
                unanimous_actual.append(next(iter(counts))); unanimous_predicted.append(prediction)
        rng = np.random.default_rng(20261125)
        families = sorted(per_family)
        bootstrap = []
        for _ in range(2000):
            chosen = rng.integers(0, len(families), len(families))
            values = [v for i in chosen for v in per_family[families[i]]]
            bootstrap.append(float(np.mean(values)))
        return dict(unique_utterances=len(test), annotation_rows=len(actual),
                    expected_accuracy=float(np.mean(unique_scores)),
                    video_cluster_percentile_95ci=[float(x) for x in np.quantile(bootstrap, [.025, .975])],
                    fractional_label_confusion=confusion_matrix(actual, expanded_predicted, labels=classes, sample_weight=sample_weights).tolist(),
                    distribution_weighted_classification=classification_report(actual, expanded_predicted, labels=classes,
                        sample_weight=sample_weights, output_dict=True, zero_division=0),
                    per_annotator={k: dict(**v, accuracy=v["correct"]/v["n"]) for k, v in sorted(by_annotator.items())},
                    multiannotator_test_utterances=len(multi_scores),
                    multiannotator_expected_accuracy=float(np.mean(multi_scores)) if multi_scores else None,
                    consensus_sensitivity=dict(n=len(consensus_actual), tie_unknown=ties,
                        classification=classification_report(consensus_actual, consensus_predicted, labels=classes, output_dict=True, zero_division=0)),
                    unanimous_sensitivity=dict(n=len(unanimous_actual),
                        classification=classification_report(unanimous_actual, unanimous_predicted, labels=classes, output_dict=True, zero_division=0)))

    def agreement(items, field):
        counts = []
        for u in items:
            labels = [a[field] for a in u["annotations"] if a[field] and a[field] != "n/a"]
            if len(labels) >= 2:
                counts.append(Counter(labels))
        if not counts:
            return dict(n=0, kappa=None)
        nraters = Counter(sum(c.values()) for c in counts)
        pairwise = [sum(n*(n-1) for n in c.values())/(sum(c.values())*(sum(c.values())-1)) for c in counts]
        categories = sorted({k for c in counts for k in c})
        marginals = {k: sum(c[k]/sum(c.values()) for c in counts)/len(counts) for k in categories}
        observed = sum(pairwise)/len(pairwise)
        expected = sum(p*p for p in marginals.values())
        return dict(n=len(counts), annotations_per_item=dict(nraters),
                    exact_unanimity=sum(len(c)==1 for c in counts)/len(counts),
                    mean_pairwise_agreement=observed, chance_agreement=expected,
                    fleiss_kappa=(observed-expected)/(1-expected) if expected < 1 else None,
                    category_marginals=marginals,
                    definition="Fleiss kappa on equally weighted items; subtypes use only applicable non-n/a labels and may have variable n")

    multi = [u for u in therapists if len(u["annotations"]) > 1]
    group_counts = Counter(u["transcript_id"] for u in multi)
    disagreement = Counter()
    for u in multi:
        distribution = u["labels"]["main_therapist_behaviour"]
        disagreement["unanimous" if distribution["unanimous"] else "disagreeing"] += 1
        disagreement["majority_ties"] += int(distribution["tie"])
    iaa = {field: agreement(multi, field) for field in ("main_therapist_behaviour", "reflection_subtype", "question_subtype", "therapist_input_subtype")}
    result = dict(protocol=PROTOCOL + "-equal-utterance-v1", source_git_blob=ANNOMI_BLOB,
        sklearn_version=sklearn.__version__, annotation_rows=len(rows), unique_utterances=len(utterances),
        therapist_annotation_rows=sum(u["interlocutor"]=="therapist" for u in rows),
        unique_therapist_utterances=len(therapists), train_unique=len(train), test_unique=len(test),
        train_annotation_rows=len(indices), train_total_weight=sum(weights),
        train_groups=len({u["video_family"] for u in train}), test_groups=len({u["video_family"] for u in test}),
        group_overlap=len({u["video_family"] for u in train}&{u["video_family"] for u in test}),
        weighting="TF-IDF unique-text fit; each utterance has total logistic loss weight=1 across original annotator labels",
        labels_collapsed_for_training=False, hyperparameters_retuned=False,
        previous_row_model_same_unique_test=evaluate(old_predictions), retrained_equal_utterance=evaluate(predictions),
        interannotator=dict(multiply_annotated_transcripts=dict(group_counts), n_transcripts=len(group_counts),
            n_utterances=len(multi), disagreement_counts=dict(disagreement), measures=iaa,
            per_transcript={tid: agreement([u for u in multi if u["transcript_id"]==tid], "main_therapist_behaviour") for tid in group_counts}),
        reward_qualified=False,
        limitations=["Development split already exposed in original web probe.",
                     "Agreement estimates cover only seven multiply annotated transcripts, not all source transcripts or independent practitioners.",
                     "Majority/tie and unanimity subsets are sensitivities; all annotation distributions remain in the training target and primary scoring.",
                     "Single-annotation test items cannot measure disagreement or calibrate consensus reliability.",
                     "No best-model selection, G generation, or automatic task reward qualification."])
    _write_once(output / "metrics.json", result)
    _write_once(output / "label_distributions.private.json", [dict(key=u["key"], video_family=u["video_family"], labels=u["labels"], annotations=u["annotations"]) for u in therapists])
    _write_once(output / "predictions.private.json", [dict(key=u["key"], video_family=u["video_family"], observed_distribution=u["labels"]["main_therapist_behaviour"], predicted=str(p), row_model_predicted=str(q)) for u,p,q in zip(test,predictions,old_predictions)])
    joblib.dump(model, output / "model.private.joblib")
    _write_once(output / "model_identity.json", dict(protocol=result["protocol"],
        model_sha256=hashlib.sha256((output/"model.private.joblib").read_bytes()).hexdigest(),
        compared_row_model_sha256=hashlib.sha256(Path(row_model).read_bytes()).hexdigest()))
    return result


def role_agreement(source):
    """Exact 10-annotator agreement, including client labels used in probes."""
    from collections import Counter
    from .rs_tasks import deduplicate_utterances
    rows = deduplicate_utterances(read_annomi(source))
    result = dict(source_git_blob=ANNOMI_BLOB,
                  unique_by_role=dict(Counter(r["interlocutor"] for r in rows)), groups={})
    for role, field in (("client", "client_talk_type"), ("therapist", "main_therapist_behaviour")):
        multi = [r for r in rows if r["interlocutor"] == role and len(r["annotations"]) > 1]
        counts = [Counter(a[field] for a in r["annotations"]) for r in multi]
        n = len(counts)
        categories = sorted({k for c in counts for k in c})
        marginal = {k: sum(c[k]/sum(c.values()) for c in counts)/n for k in categories}
        observed = sum(sum(v*(v-1) for v in c.values())/(sum(c.values())*(sum(c.values())-1)) for c in counts)/n
        chance = sum(v*v for v in marginal.values())
        result["groups"][role] = dict(field=field, n_unique_multiannotated=n,
            n_transcripts=len({r["transcript_id"] for r in multi}),
            labels_per_utterance=dict(Counter(len(r["annotations"]) for r in multi)),
            unanimous=sum(len(c)==1 for c in counts), any_disagreement=sum(len(c)>1 for c in counts),
            top_count_tie=sum(sum(v==max(c.values()) for v in c.values())>1 for c in counts),
            without_strict_majority=sum(max(c.values())<=sum(c.values())/2 for c in counts),
            pairwise_agreement=observed, fleiss_kappa=(observed-chance)/(1-chance), marginals=marginal)
    result["limitation"] = "Seven multiply annotated transcripts only. Plurality is not unanimous consensus or necessarily an absolute majority; no labels are collapsed for the unique-utterance model."
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annomi", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--equal-utterance", action="store_true")
    parser.add_argument("--agreement-only", action="store_true")
    parser.add_argument("--row-model")
    args = parser.parse_args()
    if args.agreement_only:
        result = role_agreement(args.annomi)
        _write_once(Path(args.output) / "role_agreement_supplement.json", result)
    elif args.equal_utterance:
        if not args.row_model:
            parser.error("--equal-utterance requires --row-model")
        result = train_utterance_baseline(args.annomi, args.output, args.row_model)
    else:
        result = train_baseline(args.annomi, args.output)
    print(json.dumps(result, indent=2))
