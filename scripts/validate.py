"""매니페스트가 스펙을 지키는지, 그리고 옆에 있어야 할 파일이 실제로 있는지 확인한다.

## 왜 스키마 검사만으로 안 되는가

스키마는 매니페스트 **안**만 본다. 그런데 이 저장소에서 조용히 틀릴 자리는 대부분
바깥이다 — 디렉터리 이름과 `name` 이 갈리거나, 샘플 파일이 없는데 매니페스트는
가리키고 있거나, 손으로 돌린 학습 기록이 빠지거나. 전부 병합된 뒤 받는 쪽에서만
드러나는 종류라 여기서 잡는다.
"""

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "schema" / "manifest.schema.json"
MODELS = ROOT / "models"

# 매니페스트 옆에 반드시 같이 있어야 하는 것들.
REQUIRED_SIBLINGS = ("sample.in.safetensors", "sample.out.safetensors")

# 그리고 **출신마다 하나 더.**
#
# 기록이 여기 있는 이유: 손으로 돌리기로 했으므로 자동 기록이 없다. 이 파일이 빠지면
# 그 가중치가 어디서 나왔는지 아는 사람이 세상에 한 명뿐이 되고, 그 한 명도 반년
# 뒤에는 잊는다.
#
# 이름이 갈리는 것은 **적을 내용이 다르기 때문이다.** 우리가 학습한 화물은 에폭과
# 정확도를 남기고, 가져온 화물은 누구의 것을 어떻게 옮겼는지를 남긴다. 가져온 화물에
# `training.md` 를 요구하면 학습하지 않은 사람이 학습 기록을 지어내게 된다.
RECORD_BY_ORIGIN = {
    "trained-by-borch": "training.md",
    "converted-from-torch": "provenance.md",
}


def _problems(manifest_path: Path, validator: Draft202012Validator) -> list[str]:
    """이 매니페스트 하나에서 발견한 문제를 사람이 읽을 문장으로 모은다."""
    rel = manifest_path.relative_to(ROOT)
    try:
        doc = json.loads(manifest_path.read_text())
    except json.JSONDecodeError as exc:
        return [f"{rel}: JSON 이 아닙니다 — {exc}"]

    found = [f"{rel}: {e.json_path} — {e.message}" for e in validator.iter_errors(doc)]

    # 스키마가 못 보는 자리: 디렉터리와 내용이 갈리는 것.
    version_dir = manifest_path.parent
    name_dir = version_dir.parent
    if doc.get("name") != name_dir.name:
        found.append(f"{rel}: name '{doc.get('name')}' 이 디렉터리 '{name_dir.name}' 과 다릅니다")
    if doc.get("version") != version_dir.name:
        found.append(
            f"{rel}: version '{doc.get('version')}' 이 디렉터리 '{version_dir.name}' 과 다릅니다")

    for sibling in REQUIRED_SIBLINGS:
        if not (version_dir / sibling).exists():
            found.append(f"{rel}: 옆에 있어야 할 {sibling} 이 없습니다")

    # 출신이 요구하는 기록. 스키마가 origin 을 enum 으로 좁혀 두었으므로 여기서
    # 모르는 값을 만나는 일은 스키마 검사가 먼저 잡는다.
    record = RECORD_BY_ORIGIN.get(doc.get("origin"))
    if record is not None and not (version_dir / record).exists():
        found.append(f"{rel}: 옆에 있어야 할 {record} 이 없습니다"
                     f" (origin 이 {doc.get('origin')} 입니다)")

    return found


def main() -> int:
    validator = Draft202012Validator(json.loads(SCHEMA.read_text()))
    manifests = sorted(MODELS.glob("*/*/manifest.json"))

    problems: list[str] = []
    for path in manifests:
        problems.extend(_problems(path, validator))

    for line in problems:
        print(line, file=sys.stderr)

    if problems:
        print(f"\n매니페스트 {len(manifests)}개 중 문제 {len(problems)}건", file=sys.stderr)
        return 1

    print(f"매니페스트 {len(manifests)}개 — 문제 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
