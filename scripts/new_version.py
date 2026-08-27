"""**같은 가중치로 새 판을 낸다** — 매니페스트만 바뀔 때.

    uv run python scripts/new_version.py --model imagenet-resnet50 --from 1.0.0 --to 1.0.1
    uv run python scripts/new_version.py --all --from 1.0.0 --to 1.0.1 --write

## 왜 덮어쓰지 않는가

나간 매니페스트는 `immutable, max-age=1년` 으로 서 있다. 덮어써도 **이미 받아 간
브라우저와 CDN 엣지가 1 년 동안 옛 것을 쥔다** — 고친 내용을 그 사람은 영영 못 본다.
그리고 `upload.py` 가 애초에 거부한다: 버전 박힌 자산을 덮어쓰면 이미 나간 것이
거짓이 되고 그 손해는 되돌릴 수 없다.

스키마는 **필드를 늘리는 것**은 허용한다. 하지만 허용된다는 것과 **닿는다**는 것은
다른 문제고, 여기서 걸리는 것은 뒤엣것이다.

## 가중치는 옮기지 않는다

새 판의 매니페스트가 **옛 판의 바이트 주소를 그대로** 가리킨다. 같은 가중치를 두 번
올릴 이유가 없고, 45MB 를 이미 받아 둔 사람은 다시 안 받는다.
`cifar10-resnet18 1.0.1` 이 1.0.0 의 바이트를 쓰는 것과 같은 방식이다.

**목차를 만드는 쪽이 이것을 알아야 한다** — 가중치 주소에서 매니페스트 주소를
유도하면 1.0.1 이 1.0.0 의 매니페스트를 가리킨다. 실제로 그렇게 틀렸었다.
"""

import argparse
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
BESIDE = ("sample.in.safetensors", "sample.out.safetensors", "provenance.md",
          "training.md")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", action="append", default=[])
    ap.add_argument("--all", action="store_true", help="--from 판이 있는 모델 전부")
    ap.add_argument("--from", dest="old", required=True)
    ap.add_argument("--to", dest="new", required=True)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    names = args.model
    if args.all:
        names = sorted(d.name for d in MODELS.iterdir()
                       if (d / args.old / "manifest.json").exists())
    if not names:
        print("모델을 안 골랐다 — --model 또는 --all", file=sys.stderr)
        return 2

    made, skipped = [], []
    for name in names:
        old_dir = MODELS / name / args.old
        new_dir = MODELS / name / args.new
        if not (old_dir / "manifest.json").exists():
            print(f"없다: {name}/{args.old}", file=sys.stderr)
            return 1
        if new_dir.exists():
            skipped.append(f"{name}/{args.new} — 이미 있다")
            continue

        doc = json.loads((old_dir / "manifest.json").read_text())
        doc["version"] = args.new
        # **가중치는 옛 판을 그대로 가리킨다.** 바이트가 같으므로 주소도 같아야 한다.
        made.append(f"{name}  {args.old} → {args.new}  "
                    f"가중치: {doc['weights']['url'].split('/')[-2]}/…")
        if not args.write:
            continue
        new_dir.mkdir(parents=True)
        (new_dir / "manifest.json").write_text(
            json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        for beside in BESIDE:
            if (old_dir / beside).exists():
                shutil.copy2(old_dir / beside, new_dir / beside)

    print(f"{'만들었다' if args.write else '미리보기 — 안 만든다'} · {len(made)}개\n")
    for line in made:
        print(f"  {line}")
    for line in skipped:
        print(f"  건너뜀: {line}")
    if not args.write and made:
        print("\n실제로 만들려면 --write 를 붙여라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
