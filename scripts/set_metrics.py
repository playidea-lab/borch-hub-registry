"""잰 수를 **매니페스트에 싣는다** — borch-hub 의 측정 결과를 받아서.

    uv run python scripts/set_metrics.py --from ../borch-hub/out/accuracy/summary.json
    uv run python scripts/set_metrics.py --from ... --write

## 왜 수가 넷인가

`top1_imagenetv2` 하나만 적으면 읽는 사람은 흔히 인용되는 ImageNet 점수와 견주고
**"왜 이렇게 낮지" 라고 묻는다.** 실제로 그 질문이 먼저 나왔고, 옳은 질문이었다 —
낮은 수 하나로는 시험지가 어려운 것인지 변환이 틀린 것인지 구별할 수 없다.

| 이름 | 무엇 |
|---|---|
| `top1_imagenetv2` · `top5_imagenetv2` | 우리 파이프라인이 잰 것 |
| `top1_imagenetv2_timm` | **같은 사진에 timm 을 돌린 것** — 옆에 있어야 위 수가 읽힌다 |
| `top1_imagenet_reported` | timm 이 발표한 ImageNet 값. **우리가 잰 것이 아니다** |
| `n` | 표본. 1000 장이면 표준오차가 1.5%p 쯤이라 소수점 첫째 자리까지는 못 믿는다 |

`reported` 라는 이름이 값에 붙어 있는 이유가 마지막 줄이다. 측정한 것과 옮겨 적은
것을 같은 이름으로 두면, 나중에 그 구별을 아무도 못 한다.

## `imagenetv2` 를 이름에 박는 이유

ImageNet-V2 점수는 ImageNet val 보다 체계적으로 11~14 점 낮다 — 그것이 그 논문의
결론이다. 그냥 `top1` 이라 적으면 **다른 시험지 점수를 우리 점수인 척** 하는 것이 된다.
"""

import argparse
import datetime
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="source", type=pathlib.Path, required=True)
    ap.add_argument("--measured-by", required=True,
                    help="런타임·브라우저·장치. 손으로 돌리므로 이 문자열이 유일한 기록이다")
    ap.add_argument("--measured-at", default=None, help="기본은 오늘")
    ap.add_argument("--write", action="store_true", help="실제로 고친다 (기본은 미리보기)")
    args = ap.parse_args(argv)

    measured = json.loads(args.source.read_text())
    when = args.measured_at or datetime.date.today().isoformat()
    touched, missing = [], []

    for name, row in sorted(measured.items()):
        ours, ref = row["ours"], row.get("timm")
        values: dict[str, float] = {
            "top1_imagenetv2": round(ours["top1"], 4),
            "top5_imagenetv2": round(ours["top5"], 4),
            "n": ours["n"],
        }
        # **없으면 안 적는다.** 빈 자리를 0 으로 채우면 "0% 였다" 로 읽힌다.
        if ref is not None:
            values["top1_imagenetv2_timm"] = round(ref["top1"], 4)
        if row.get("reported") is not None:
            values["top1_imagenet_reported"] = row["reported"]

        found = sorted((MODELS / name).glob("*/manifest.json"))
        if not found:
            missing.append(name)
            continue
        for path in found:
            doc = json.loads(path.read_text())
            doc["metrics"] = {"values": values, "measuredBy": args.measured_by,
                              "measuredAt": when}
            where = path.parent.relative_to(MODELS).as_posix()
            if args.write:
                path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            touched.append(f"{where}  top1={values['top1_imagenetv2']}"
                           + (f" (timm {values['top1_imagenetv2_timm']})"
                              if "top1_imagenetv2_timm" in values else "  timm 없음"))

    print(f"{'고쳤다' if args.write else '미리보기 — 안 고친다'} · {len(touched)}개\n")
    for line in touched:
        print(f"  {line}")
    if missing:
        print(f"\n매니페스트를 못 찾았다: {', '.join(missing)}", file=sys.stderr)
        return 1
    if not args.write:
        print("\n실제로 고치려면 --write 를 붙여라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
