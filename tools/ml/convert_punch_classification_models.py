"""Convert the trusted punch-classification PyTorch checkpoints to ONNX.

This tool is intentionally not part of the Backend runtime.  Run it only in a
trusted development environment that has PyTorch installed.  The role mapping
is mandatory so an undocumented Node1/Node2 guess can never enter Production.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch


ROLE_CHOICES = ("holder_left_pad", "holder_right_pad")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--handover-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--node1-role", choices=ROLE_CHOICES, required=True)
    parser.add_argument("--node2-role", choices=ROLE_CHOICES, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.node1_role == args.node2_role:
        raise SystemExit("Node1 and Node2 must map to different Input Roles")

    essay = args.handover_root / "Code" / "essay"
    segmentation_checkpoint = essay / "exp" / "second" / "model_best.pt"
    classifier_checkpoint = essay / "exp" / "first" / "lstm" / "lstm_classifier.pt"
    for checkpoint in (segmentation_checkpoint, classifier_checkpoint):
        if not checkpoint.is_file():
            raise SystemExit(f"Checkpoint not found: {checkpoint}")

    sys.path.insert(0, str(essay))
    from run_random30_all_models_experiment import LSTMPunchClassifier  # noqa: PLC0415
    from segmentation.supervised_model import TemporalConvNet  # noqa: PLC0415

    seg = torch.load(segmentation_checkpoint, map_location="cpu", weights_only=False)
    seg_config = dict(seg["config"])
    seg_features = [str(value) for value in seg["feature_cols"]]
    segmentation = TemporalConvNet(
        input_size=len(seg_features),
        num_classes=int(seg_config["num_classes"]),
        hidden_size=int(seg_config["hidden_size"]),
        num_conv_layers=int(seg_config["num_conv_layers"]),
        lstm_hidden=int(seg_config["lstm_hidden"]),
        dropout=float(seg_config["dropout"]),
    )
    segmentation.load_state_dict(seg["model_state"])
    segmentation.eval()

    clf = torch.load(classifier_checkpoint, map_location="cpu", weights_only=False)
    classes = [str(value) for value in clf["classes"]]
    classifier_features = [str(value) for value in clf["axis_features"]]
    classifier = LSTMPunchClassifier(
        len(classifier_features),
        int(clf["hidden_dim"]),
        len(classes),
        float(clf["dropout"]),
    )
    classifier.load_state_dict(clf["model_state"])
    classifier.eval()

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    seg_path = output / "segmentation.onnx"
    classifier_path = output / "classifier.onnx"
    normalization_path = output / "normalization.npz"
    reference_path = output / "reference_outputs.npz"

    window_size = int(seg_config.get("window_size", 384))
    sequence_length = int(clf["seq_len"])
    torch.manual_seed(2312)
    seg_input = torch.randn(1, window_size, len(seg_features), dtype=torch.float32)
    classifier_input = torch.randn(
        2, sequence_length, len(classifier_features), dtype=torch.float32
    )
    torch.onnx.export(
        segmentation,
        seg_input,
        seg_path,
        input_names=["frames"],
        output_names=["logits"],
        dynamic_axes={"frames": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    torch.onnx.export(
        classifier,
        classifier_input,
        classifier_path,
        input_names=["segments"],
        output_names=["logits"],
        dynamic_axes={"segments": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )

    seg_mean = np.asarray(seg["mean"], dtype=np.float32)
    seg_std = np.asarray(seg["std"], dtype=np.float32)
    classifier_mean = np.asarray(clf["normalization"]["mean"], dtype=np.float32)
    classifier_std = np.asarray(clf["normalization"]["std"], dtype=np.float32)
    np.savez_compressed(
        normalization_path,
        segmentation_mean=seg_mean,
        segmentation_std=seg_std,
        classifier_mean=classifier_mean,
        classifier_std=classifier_std,
    )

    with torch.no_grad():
        seg_logits = segmentation(seg_input).numpy()
        seg_probabilities = torch.softmax(torch.from_numpy(seg_logits), dim=-1).numpy()
        classifier_logits = classifier(classifier_input).numpy()
        classifier_probabilities = torch.softmax(
            torch.from_numpy(classifier_logits), dim=-1
        ).numpy()
    seg_labels = seg_probabilities.argmax(axis=-1)
    positive = seg_labels[0] > 0
    reference_segments: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(positive):
        if value and start is None:
            start = index
        if start is not None and (not value or index == len(positive) - 1):
            end = index if value and index == len(positive) - 1 else index - 1
            if end - start + 1 >= 20:
                reference_segments.append((start, end))
            start = None

    onnx_segmentation = ort.InferenceSession(
        str(seg_path), providers=["CPUExecutionProvider"]
    ).run(None, {"frames": seg_input.numpy()})[0]
    onnx_classifier = ort.InferenceSession(
        str(classifier_path), providers=["CPUExecutionProvider"]
    ).run(None, {"segments": classifier_input.numpy()})[0]
    np.testing.assert_allclose(onnx_segmentation, seg_logits, rtol=1e-4, atol=1e-5)
    np.testing.assert_allclose(onnx_classifier, classifier_logits, rtol=1e-4, atol=1e-5)
    if not np.array_equal(onnx_segmentation.argmax(axis=-1), seg_labels):
        raise RuntimeError("ONNX segmentation labels differ from PyTorch")
    if not np.array_equal(onnx_classifier.argmax(axis=-1), classifier_probabilities.argmax(axis=-1)):
        raise RuntimeError("ONNX classifier labels differ from PyTorch")
    np.savez_compressed(
        reference_path,
        segmentation_input=seg_input.numpy(),
        segmentation_logits=seg_logits,
        segmentation_probabilities=seg_probabilities,
        segmentation_labels=seg_labels,
        segmentation_segments=np.asarray(reference_segments, dtype=np.int64).reshape(-1, 2),
        classifier_input=classifier_input.numpy(),
        classifier_logits=classifier_logits,
        classifier_probabilities=classifier_probabilities,
        classifier_labels=classifier_probabilities.argmax(axis=-1),
    )

    manifest = {
        "bundle_version": 1,
        "algorithm_version": "mitt_tcn_bilstm_lstm_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "runtime": "onnxruntime-cpu",
        "sample_rate_hz": 400,
        "role_mapping": {
            "Node1": args.node1_role,
            "Node2": args.node2_role,
        },
        "segmentation": {
            "file": seg_path.name,
            "checkpoint_sha256": sha256(segmentation_checkpoint),
            "features": seg_features,
            "feature_count": len(seg_features),
            "window_size": window_size,
            "stride": int(seg_config.get("stride", 128)),
            "minimum_segment_frames": 20,
            "postprocess": "average_overlap_probabilities_then_positive_contiguous_min20",
            "output_classes": int(seg_config["num_classes"]),
        },
        "classifier": {
            "file": classifier_path.name,
            "checkpoint_sha256": sha256(classifier_checkpoint),
            "features": classifier_features,
            "feature_count": len(classifier_features),
            "sequence_length": sequence_length,
            "labels": classes,
            "acceleration_mode": str(clf.get("acc_mode", "raw")),
        },
        "normalization_file": normalization_path.name,
        "reference_outputs_file": reference_path.name,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    manifest["files"] = {
        path.name: sha256(path)
        for path in (seg_path, classifier_path, normalization_path, reference_path)
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
