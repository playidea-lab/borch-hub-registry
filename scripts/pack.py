"""학습이 뱉은 화물을 **레지스트리 항목**으로 만든다.

    uv run --with jsonschema python scripts/pack.py \
        --cargo ~/git/borch-hub/out --name cifar10-resnet18 --version 1.0.0 \
        --base https://<CDN 주소>/cifar10-resnet18/1.0.0

`--base` 를 인자로 받는 이유는 CDN 주소가 코드에 있으면 안 되기 때문이다. 주소는
운영이 정하는 값이고, 여기 박아 두면 옮기는 날 이 저장소를 고쳐야 한다.

**가중치는 안 옮긴다.** 이 스크립트가 만드는 것은 매니페스트와 그 옆에 사는
작은 파일들뿐이다. 45MB 를 CDN 에 올리는 것은 사람이 따로 하고, 그 순서가 먼저다 —
바이트 없는 매니페스트를 병합하면 받는 쪽이 404 를 만난다.

## 해시를 여기서 다시 잰다

`summary.json` 이 적어 온 값을 그대로 믿지 않는다. 그 파일과 `model.safetensors`
사이에서 무슨 일이 있었는지(옮겨졌는지, 덮였는지) 이 스크립트는 모르고, 매니페스트에
적히는 순간 그 해시는 **받는 쪽이 믿을 값**이 된다.
"""

import argparse
import hashlib
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

SIBLINGS = ("sample.in.safetensors", "sample.out.safetensors")


def build(args: argparse.Namespace) -> int:
    cargo = pathlib.Path(args.cargo).expanduser().resolve()
    summary_path = cargo / "summary.json"
    weights_path = cargo / "model.safetensors"
    for path in (summary_path, weights_path, *(cargo / s for s in SIBLINGS)):
        if not path.exists():
            print(f"화물에 없다: {path}", file=sys.stderr)
            return 2

    summary = json.loads(summary_path.read_text())
    if "invalid" in summary:
        print(f"이 화물은 무효 표시가 붙어 있다: {summary['invalid']}", file=sys.stderr)
        return 2

    raw = weights_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != summary.get("sha256"):
        print("경고: 요약이 적은 해시와 파일의 해시가 다르다.\n"
              f"  요약 {summary.get('sha256')}\n  파일 {digest}\n"
              "  파일 쪽을 적는다 — 매니페스트는 바이트를 가리키는 것이다.", file=sys.stderr)

    out = ROOT / "models" / args.name / args.version
    out.mkdir(parents=True, exist_ok=True)
    for sibling in SIBLINGS:
        shutil.copy2(cargo / sibling, out / sibling)

    manifest = {
        "schemaVersion": 1,
        "name": args.name,
        "version": args.version,
        "description": args.description,
        "task": args.task,
        "dataset": args.dataset,
        "tags": args.tags.split(",") if args.tags else [],
        "arch": {"factory": args.factory, "args": {"numClasses": args.classes}},
        "weights": {
            "url": f"{args.base.rstrip('/')}/model.safetensors",
            "sha256": digest,
            "bytes": len(raw),
            "format": "safetensors",
        },
        "runtime": {
            "ts": args.ts, "py": None,
            "webgpu": {"required": True, "limits": {}},
        },
        "sample": {
            "inputUrl": "sample.in.safetensors",
            "outputUrl": "sample.out.safetensors",
            "rtol": args.rtol, "atol": args.atol,
        },
        "metrics": {
            "values": {"top1": round(summary["finalTest"], 4),
                       "top1_best": round(summary["bestTest"], 4)},
            "measuredBy": f"borch.ts / {summary['adapter']}",
            "measuredAt": args.date,
        },
        "origin": "trained-by-borch",
        "license": {"weights": args.license, "data": args.data_license},
        "attestation": None,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    record = out / "training.md"
    if not record.exists():
        rows = summary.get("rows", [])
        seconds = sum(r.get("seconds", 0) for r in rows)
        lines = [
            f"# {args.name} {args.version}",
            "",
            "손으로 돌린 실행이다. 자동 기록이 없으므로 이 파일이 유일한 증거다.",
            "",
            f"- 어댑터: {summary['adapter']}",
            f"- 학습 {summary['trainImages']}장 · {len(rows)} 에폭 · 총 {seconds / 60:.1f}분",
            f"- 마지막 시험 정확도 {summary['finalTest'] * 100:.2f}% · "
            f"가장 좋은 것 {summary['bestTest'] * 100:.2f}%",
            f"- sha256 `{digest}`",
            "",
            "## 에폭",
            "",
            "| 에폭 | 학습 | 시험 | 손실 | 초 |",
            "|---|---|---|---|---|",
            *[f"| {r['epoch']} | {r['train']:.3f} | {r['test']:.3f} | "
              f"{r['loss']:.4f} | {r['seconds']:.1f} |" for r in rows],
            "",
            "## 레시피",
            "",
            "코어(`borch`)의 `accuracy.ts` 와 같은 값이다. 새로 고르면 나온 정확도가",
            "코어가 발표한 수와 비교 불가능해진다. 나머지 하이퍼파라미터는",
            "`model.safetensors` 의 `__metadata__` 에 들어 있다.",
        ]
        record.write_text("\n".join(lines) + "\n")
        print(f"기록 초안을 썼다: {record.relative_to(ROOT)} — 사람이 읽고 보태라")

    print(f"만들었다: models/{args.name}/{args.version}/")
    print(f"  가중치 주소: {manifest['weights']['url']}")
    print(f"  sha256: {digest}")
    print("\n다음: 가중치를 그 주소에 올리고, `scripts/validate.py` 를 돌린 뒤 PR 을 연다.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cargo", required=True, help="학습이 뱉은 디렉터리 (out/)")
    p.add_argument("--name", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--base", required=True, help="이 버전이 사는 CDN 주소")
    p.add_argument("--date", required=True, help="잰 날짜 (YYYY-MM-DD)")
    p.add_argument("--factory", default="resnet18")
    p.add_argument("--classes", type=int, default=10)
    p.add_argument("--task", default="image-classification")
    p.add_argument("--dataset", default="cifar-10")
    p.add_argument("--tags", default="vision,resnet,cifar-10")
    p.add_argument("--description", default=None)
    p.add_argument("--ts", default=">=0.1.0", help="npm borch 의 semver 범위")
    p.add_argument("--rtol", type=float, default=1e-4)
    p.add_argument("--atol", type=float, default=1e-5)
    p.add_argument("--license", default="Apache-2.0")
    p.add_argument("--data-license", dest="data_license", default="CIFAR-10 (research use)")
    return build(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
