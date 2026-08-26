"""화물을 **레지스트리 항목**으로 만든다 — 우리가 학습한 것과 남에게서 가져온 것.

    uv run --with jsonschema python scripts/pack.py \
        --cargo ~/git/borch-hub/out --name cifar10-resnet18 --version 1.0.0 \
        --base https://<CDN 주소>/cifar10-resnet18/1.0.0

`--base` 를 인자로 받는 이유는 CDN 주소가 코드에 있으면 안 되기 때문이다. 주소는
운영이 정하는 값이고, 여기 박아 두면 옮기는 날 이 저장소를 고쳐야 한다.

**가중치는 안 옮긴다.** 이 스크립트가 만드는 것은 매니페스트와 그 옆에 사는
작은 파일들뿐이다. 45MB 를 CDN 에 올리는 것은 사람이 따로 하고, 그 순서가 먼저다 —
바이트 없는 매니페스트를 병합하면 받는 쪽이 404 를 만난다.

## 출신이 둘이고, 그 둘을 섞지 않는다

`--origin converted-from-torch` 는 **남이 학습한 가중치를 옮겨 온 화물**이다(timm 등).
스키마가 그 이름을 먼저 두었고 까닭도 적어 두었다 — 우리가 잰 수와 남이 발표한 수를
처음부터 다른 이름으로 부르기 위해서다.

그래서 이 경로는 **`metrics` 를 안 쓴다.** 발표된 top-1 을 적으면 그 수가 우리 것으로
읽히고, 우리는 그것을 잰 적이 없다. "누가 언제 무엇으로 쟀는지가 없는 수는 수가
아니다" 는 스키마 자신의 문장이고, 없는 수를 적느니 자리를 비우는 편이 그 문장에
맞다. 대신 어디서 왔는지가 `provenance.md` 에 남는다.

학습 화물이 요구하는 것(에폭 표·최종 정확도·어댑터)도 여기서는 안 찾는다. 그 화물에
없는 값이고, 없는 것을 요구하면 만든 쪽이 지어내게 된다.

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


def _fail(what: str):
    raise SystemExit(f"{what} 가 없습니다 — 판 2 매니페스트는 전처리를 적어야 합니다.\n"
                     "  없으면 가중치는 실리는데 아무것도 못 넣습니다.")


def build(args: argparse.Namespace) -> int:
    cargo = pathlib.Path(args.cargo).expanduser().resolve()
    summary_path = cargo / "summary.json"
    weights_path = cargo / "model.safetensors"
    for path in (summary_path, weights_path, *(cargo / s for s in SIBLINGS)):
        if not path.exists():
            print(f"화물에 없다: {path}", file=sys.stderr)
            return 2

    summary = json.loads(summary_path.read_text())
    converted = args.origin == "converted-from-torch"
    if converted and summary.get("origin") != "converted-from-torch":
        print(f"화물이 스스로를 {summary.get('origin')!r} 라고 적었는데 "
              f"--origin 은 converted-from-torch 다. 둘 중 하나가 틀렸다.", file=sys.stderr)
        return 2
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

    # 이름 자체에 쉼표가 들어 있는 데이터셋이 있다(ImageNet 의 "tench, Tinca tinca").
    # 쉼표로 가르는 인자로는 그런 이름을 못 받으므로 파일도 받는다 — 한 줄에 하나.
    if args.classes_file:
        classes = [line.strip() for line in
                   pathlib.Path(args.classes_file).expanduser().read_text().splitlines()
                   if line.strip()]
    else:
        classes = [c.strip() for c in args.classes.split(",")] if args.classes else None
    if classes is None:
        print("--classes 가 없습니다 — 판 2 매니페스트는 나온 수를 읽는 법을 적어야 합니다.\n"
              "  없으면 받는 쪽은 argmax 가 3 이라는 것까지만 압니다.", file=sys.stderr)
        return 2

    def numbers(text, what):
        return [float(x) for x in text.split(",")] if text else _fail(what)

    manifest = {
        "schemaVersion": 2,
        "name": args.name,
        "version": args.version,
        "description": args.description,
        "task": args.task,
        "dataset": args.dataset,
        "tags": args.tags.split(",") if args.tags else [],
        "arch": {"library": args.library, "factory": args.factory,
                 "args": {"numClasses": len(classes)}},
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
        # 가져온 화물에는 metrics 가 없다 — 위 문단을 보라. 스키마도 이 필드를
        # 필수로 두지 않는다.
        **({} if converted else {"metrics": {
            "values": {"top1": round(summary["finalTest"], 4),
                       "top1_best": round(summary["bestTest"], 4)},
            "measuredBy": f"borch.ts / {summary['adapter']}",
            "measuredAt": args.date,
        }}),
        "preprocess": {
            "inputSize": [int(n) for n in args.input_size.split(",")],
            "valueRange": "unit",
            "mean": numbers(args.mean, "--mean"),
            "std": numbers(args.std, "--std"),
            # **둘을 비워 두면 이미지가 모델에 안 맞게 들어간다.** 32×32 로 학습한
            # 첫 화물은 크기를 맞추는 것만으로 충분했지만, ImageNet 계열은 짧은 변을
            # 키운 뒤 가운데를 자르는 것이 학습 때의 규칙이다. 안 적으면 받는 쪽이
            # 늘려 넣게 되고, 모델은 실리는데 이름이 틀리게 나온다(실측).
            "resize": (None if args.resize_short_side is None else
                       {"shortSide": args.resize_short_side,
                        "interpolation": args.interpolation}),
            "centerCrop": ([int(n) for n in args.center_crop.split(",")]
                           if args.center_crop else None),
        },
        "outputs": {"kind": "logits", "classes": classes},
        "origin": args.origin,
        "license": {"weights": args.license, "data": args.data_license},
        "attestation": None,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    if converted:
        return _provenance(out, args, summary, digest, manifest)

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


def _provenance(out, args, summary, digest, manifest) -> int:
    """가져온 화물의 기록. **학습 이력이 아니라 출처다.**

    이 파일이 빠지면 그 가중치가 어디서 왔는지 아는 사람이 세상에 한 명뿐이 되고, 그
    한 명도 반년 뒤에는 잊는다 — `training.md` 를 필수로 둔 이유와 같다. 다른 것은
    적을 내용뿐이다: 우리가 무엇을 했는지가 아니라 **누구의 것을 어떻게 옮겼는지.**
    """
    src = {**summary.get("source", {}), **summary.get("preprocess", {})}
    record = out / "provenance.md"
    if not record.exists():
        top1 = summary.get("publishedTop1")
        lines = [
            f"# {args.name} {args.version}",
            "",
            "**우리가 학습한 가중치가 아니다.** 남이 학습한 것을 옮겨 왔고, 이 파일이",
            "그 출처다.",
            "",
            f"- 출처: `{src.get('library')} {src.get('libraryVersion')}` 의 "
            f"`{src.get('model')}`",
            f"- 체크포인트: `{src.get('checkpointUrl')}`",
            f"- 가중치 라이선스: {src.get('license')}",
            f"- 열쇠 {summary.get('keys')}개 · {summary.get('bytes'):,} 바이트",
            f"- sha256 `{digest}`",
            "",
            "## 발표된 수 — 우리가 잰 것이 아니다",
            "",
            f"원저자가 발표한 top-1 은 {top1 if top1 is not None else '알려지지 않음'} 이다."
            if top1 is not None else "원저자가 발표한 top-1 을 이 화물은 모른다.",
            "",
            "매니페스트의 `metrics` 는 비어 있다. 그 자리는 **우리가 잰 수**를 위한",
            "것이고, 여기 적을 수는 우리 것이 아니다. 비트 동등은 borch 의 명시적",
            "비목표이므로 이 수를 그대로 물려받는다고 말할 수도 없다.",
            "",
            "## 옮긴 것이 같은 모델인지",
            "",
            "카탈로그(`bimm`) 쪽에 `browser/parity.py` 가 있다. timm 을 실제로 세워",
            "가중치·입력·출력을 받아 오고, 같은 가중치를 같은 입력에 통과시켜 수를",
            "나란히 놓는다 — 열쇠 집합과 출력 둘 다 본다.",
            "",
            # 보간이 원본과 같으면 "갈린 것" 문단은 거짓이 된다. 무엇을 못 옮겼는지
            # 적는 자리이지, 자리를 채우는 곳이 아니다.
            *([] if args.interpolation == src.get("interpolation") else [
                "## 옮기면서 갈린 것",
                "",
                f"원본은 resize 에 `{src.get('interpolation')}` 보간을 쓰는데 이 화물은",
                f"`{args.interpolation}` 로 적혀 있다. **그것이 원본과 다른 유일한 전처리",
                "항목이다.**",
                "",
            ]),
            "## 전처리",
            "",
            f"짧은 변을 `{src.get('resizeShortSide')}` 로 키운 뒤 가운데를",
            f"`{src.get('inputSize')}` 로 자른다(crop_pct {src.get('cropPct')}).",
            f"보간은 `{args.interpolation}` — 원본과"
            + (" 같다." if args.interpolation == src.get("interpolation") else " 다르다."),
            "",
            "## 샘플",
            "",
            f"`sample.in.safetensors` 는 시드 {summary.get('sampleSeed')} 로 만든",
            "전처리 완료 텐서이고, `sample.out.safetensors` 는 **원본이 낸 수**다.",
            "허브가 이 화물을 실을 때마다 그 수를 재현하는지 보게 된다.",
        ]
        record.write_text("\n".join(lines) + "\n")
        print(f"출처 기록을 썼다: {record.relative_to(ROOT)} — 사람이 읽고 보태라")

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
    p.add_argument("--library", default="borchvision",
                   help="factory 가 어느 카탈로그의 것인가 (borchvision·bimm)")
    p.add_argument("--factory", default="resnet18_cifar")
    p.add_argument("--classes", default=None,
                   help="logits 자리마다의 이름, 쉼표로. 판 2 에는 필수다")
    p.add_argument("--classes-file", dest="classes_file", default=None,
                   help="이름을 한 줄에 하나씩 적은 파일. 이름에 쉼표가 있을 때 쓴다")
    # **상수를 여기 박지 않는다.** CIFAR 의 mean/std 를 스크립트가 알고 있으면
    # 다음 데이터셋에서 조용히 틀린 값이 붙는다. 만든 쪽이 아는 값이므로 만든
    # 쪽이 말해야 하고, 그 값은 이 명령과 함께 training.md 에 남는다.
    p.add_argument("--input-size", dest="input_size", default="3,32,32", help="C,H,W")
    p.add_argument("--resize-short-side", dest="resize_short_side", type=int, default=None,
                   help="짧은 변을 이 크기로 (torchvision Resize(int) 규칙)")
    p.add_argument("--center-crop", dest="center_crop", default=None, help="H,W")
    p.add_argument("--interpolation", default="bilinear",
                   choices=("bilinear", "nearest", "bicubic"),
                   help="resize 의 보간. bicubic 은 코어 0.2.0 부터 있다")
    p.add_argument("--mean", default=None, help="채널마다, 쉼표로")
    p.add_argument("--std", default=None, help="채널마다, 쉼표로")
    p.add_argument("--task", default="image-classification")
    p.add_argument("--dataset", default="cifar-10")
    p.add_argument("--tags", default="vision,resnet,cifar-10")
    p.add_argument("--description", default=None)
    p.add_argument("--ts", default=">=0.1.0", help="npm borch 의 semver 범위")
    p.add_argument("--rtol", type=float, default=1e-4)
    p.add_argument("--atol", type=float, default=1e-5)
    p.add_argument("--license", default="Apache-2.0")
    p.add_argument("--data-license", dest="data_license", default="CIFAR-10 (research use)")
    p.add_argument("--origin", default="trained-by-borch",
                   choices=("trained-by-borch", "converted-from-torch"),
                   help="우리가 학습했는가, 남에게서 가져왔는가")
    return build(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
