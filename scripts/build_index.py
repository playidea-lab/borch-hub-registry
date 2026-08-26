"""메뉴판의 **목차**를 만든다 — `models/` 를 훑어 `index.json` 하나로.

    uv run python scripts/build_index.py          # 만든다 (저장소에는 안 남는다)
    uv run python scripts/build_index.py --dry-run  # 만들어 보기만 한다

## 왜 목차가 필요한가

허브의 입구는 `load(매니페스트 주소)` 하나다. 즉 **쓰는 사람이 그 주소를 이미 알고
있어야 한다.** 모델이 하나일 때는 안 보이던 구멍이고, 둘이 되는 순간 "무엇이 있는지"
를 물을 곳이 없다는 것이 드러난다.

## 목차에 무엇을 넣고 무엇을 빼는가

**받기 전에 고르는 데 필요한 것까지만** 넣는다 — 이름, 판, 무슨 일을 하는지, 어느
데이터셋인지, 얼마나 큰지, 우리가 학습한 것인지 남에게서 온 것인지.

전처리 표나 클래스 1000 개는 안 넣는다. 그것은 **고른 다음** 필요한 것이고, 목차에
넣으면 목차가 매니페스트만큼 커진다. 고르는 사람은 1000 개 이름을 읽고 고르지 않는다.

## 저장소에 안 남는 이유

`.gitignore` 가 그 결정을 이미 적어 뒀다 — **커밋하면 매니페스트와 갈릴 자리가 하나
늘고, 갈린 것은 아무도 안 본다.** 목차는 `models/` 에서 언제든 다시 나오므로 정본이
둘일 이유가 없다.

그래서 CI 가 대조하는 것은 저장된 파일이 아니라 **만들 수 있는가**다. 매니페스트
하나가 목차 한 줄이 되지 못하면 그 자리에서 멈춘다.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
INDEX = ROOT / "index.json"

SCHEMA_VERSION = 1


def entry(manifest_path: Path, doc: dict[str, object]) -> dict[str, object]:
    """매니페스트 하나에서 **고르는 데 필요한 것만** 뽑는다."""
    weights = doc["weights"]
    assert isinstance(weights, dict)
    # 매니페스트 주소는 가중치 주소에서 얻는다. 둘은 **같은 디렉터리에 있어야 하고**,
    # 그 사실이 여기 박히는 것이 맞다 — 샘플이 상대 주소로 적혀 있어서 매니페스트가
    # 다른 곳에 있으면 샘플을 못 찾는다.
    url = str(weights["url"])
    base = url.rsplit("/", 1)[0]
    return {
        "name": doc["name"],
        "version": doc["version"],
        "task": doc["task"],
        "dataset": doc["dataset"],
        "tags": doc.get("tags", []),
        "origin": doc["origin"],
        "bytes": weights["bytes"],
        "manifestUrl": f"{base}/manifest.json",
        "path": str(manifest_path.parent.relative_to(ROOT).as_posix()),
    }


def build() -> dict[str, object]:
    entries = []
    for manifest_path in sorted(MODELS.rglob("manifest.json")):
        doc = json.loads(manifest_path.read_text())
        entries.append(entry(manifest_path, doc))
    # **정해진 순서로 낸다.** 파일시스템 순서에 맡기면 아무것도 안 바뀐 날에도 diff 가
    # 생기고, 그러면 diff 가 신호이기를 그만둔다.
    entries.sort(key=lambda e: (str(e["name"]), str(e["version"])))
    return {"schemaVersion": SCHEMA_VERSION, "models": entries}


def main(argv: list[str]) -> int:
    made = build()
    text = json.dumps(made, indent=2, ensure_ascii=False) + "\n"

    models = made["models"]
    assert isinstance(models, list)
    found = len(list(MODELS.rglob("manifest.json")))
    if len(models) != found:
        print(f"매니페스트 {found}개인데 목차는 {len(models)}줄이다 — 하나가 떨어졌다",
              file=sys.stderr)
        return 1

    if "--dry-run" in argv:
        print(f"목차를 만들 수 있다 — 모델 {len(models)}개 (쓰지 않았다)")
        return 0

    INDEX.write_text(text)
    print(f"목차를 만들었다: index.json — 모델 {len(models)}개")
    for e in models:
        print(f"  {e['name']} {e['version']}  {e['bytes']:,} 바이트  {e['origin']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
