"""레지스트리를 **통째로 배포한다** — 매니페스트·샘플, 그리고 목차.

    export R2_ENDPOINT=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
    uv run --with boto3 python scripts/publish.py            # 무엇이 나갈지 보여주기만
    uv run --with boto3 python scripts/publish.py --write    # 실제로 올린다

## 왜 스크립트인가 — 셸 반복문이 아니라

`upload.py` 는 파일 하나를 다룬다. 그것을 셸 반복문으로 열다섯 번 부르면, **틀린 것이
있을 때 같은 실패가 열다섯 번 나온다.** 자격증명 한 줄이 빠졌을 뿐인데 화면이 파이썬
역추적으로 가득 차고, 사람이 처음 하는 생각은 "스크립트가 깨졌나" 가 된다(실제로 두 번
그랬다).

한 번만 부르면 **먼저 다 보고 나서 시작할 수 있다** — 자격증명이 있는지, 올릴 것이
무엇인지, 가중치가 이미 서 있는지. 틀린 것은 한 번 말하고 멈춘다.

## 기본이 미리보기인 이유

이것은 공개 CDN 에 쓰는 명령이다. `--write` 를 손으로 적게 하면 "무엇이 나가는지 보고
나서 결정" 이 기본이 된다. 반대로 두면 실수가 이미 나간 뒤에 발견된다.

## 순서

가중치가 먼저 서 있어야 한다 — 매니페스트가 가리키는 바이트가 없으면 받는 쪽이 404 를
만나고, 그것은 우리가 아니라 그 사람이 겪는다. 그래서 가중치를 **확인만 하고 올리지는
않는다.** 그것은 화물을 만든 사람이 이미 한 일이다.

목차는 맨 마지막이다. 목차에 있는데 못 받는 것보다, 있는데 목차에 아직 없는 편이 낫다.
"""

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"
INDEX = ROOT / "index.json"

NEEDED = ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY")
BESIDE = ("manifest.json", "sample.in.safetensors", "sample.out.safetensors")
JSON = "application/json"
OCTET = "application/octet-stream"

# 공개 주소로 확인할 때 쓴다. Cloudflare 는 `Python-urllib/3.x` 를 봇으로 보고 403 을 준다.
AGENT = {"User-Agent": "borch-hub-publish/1"}


def credentials() -> list[str]:
    """없는 것의 이름. **셋을 한꺼번에 말한다** — 하나씩 알리면 세 번 돌게 된다."""
    return [name for name in NEEDED if not os.environ.get(name)]


def head(url: str) -> int | None:
    """공개 주소의 길이. 없으면 `None`."""
    try:
        request = urllib.request.Request(url, method="HEAD", headers=AGENT)
        with urllib.request.urlopen(request, timeout=30) as res:
            return int(res.headers.get("content-length", 0))
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None


def entries() -> list[dict[str, object]]:
    found = []
    for manifest_path in sorted(MODELS.rglob("manifest.json")):
        doc = json.loads(manifest_path.read_text())
        weights = doc["weights"]
        found.append({
            "dir": manifest_path.parent,
            "key": manifest_path.parent.relative_to(MODELS).as_posix(),
            "weightsUrl": weights["url"],
            "weightsBytes": weights["bytes"],
        })
    return found


def upload(path: pathlib.Path, key: str, content_type: str, public: str,
           bucket: str, mutable: bool) -> bool:
    """`upload.py` 를 그대로 쓴다 — 되받기 확인과 덮어쓰기 금지가 거기 들어 있다."""
    cmd = [
        "uv", "run", "--with", "boto3", "python", str(ROOT / "scripts" / "upload.py"),
        "--file", str(path), "--bucket", bucket, "--key", key,
        "--public-base", public, "--content-type", content_type,
    ]
    if mutable:
        cmd.append("--mutable")
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode == 0


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="실제로 올린다 (기본은 미리보기)")
    ap.add_argument("--bucket", default="borch-hub")
    ap.add_argument("--public-base", dest="public", default="https://models.pilab.kr")
    args = ap.parse_args(argv)

    missing = credentials()
    if missing and args.write:
        print(f"자격증명이 없다: {', '.join(missing)}\n"
              "  Cloudflare 대시보드 → R2 → API 토큰. **값을 실제로 채워서** 넘겨라 —\n"
              "  아래를 그대로 붙여넣으면 안 된다:\n"
              "    export R2_ENDPOINT=https://<계정ID>.r2.cloudflarestorage.com\n"
              "  아무것도 올라가지 않았다.", file=sys.stderr)
        return 2

    found = entries()
    if not found:
        print("models/ 가 비어 있다", file=sys.stderr)
        return 1

    print(f"{'올린다' if args.write else '미리보기 — 올리지 않는다'} · 모델 {len(found)}개\n")

    # **가중치는 확인만 한다.** 먼저 서 있어야 하고, 올리는 것은 화물을 만든 사람의 일이다.
    blocked = []
    for e in found:
        got = head(str(e["weightsUrl"]))
        ok = got == e["weightsBytes"]
        mark = "✅" if ok else "⚠️ "
        seen = f"{got:,}" if got else "없음"
        note = "" if ok else f"  (매니페스트는 {e['weightsBytes']:,})"
        print(f"  {mark} {e['key']}  가중치 {seen}{note}")
        if not ok:
            blocked.append(str(e["key"]))
    if blocked:
        print(f"\n가중치가 먼저 서 있어야 한다: {', '.join(blocked)}\n"
              "  매니페스트가 가리키는 바이트가 없으면 받는 쪽이 404 를 만난다.", file=sys.stderr)
        return 1

    print()
    failed = []
    for e in found:
        for name in BESIDE:
            path = pathlib.Path(str(e["dir"])) / name
            if not path.exists():
                print(f"  없다: {e['key']}/{name}", file=sys.stderr)
                failed.append(f"{e['key']}/{name}")
                continue
            key = f"{e['key']}/{name}"
            if not args.write:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
                print(f"  {key}  {path.stat().st_size:,} 바이트  sha256:{digest}…")
                continue
            if not upload(path, key, JSON if name == "manifest.json" else OCTET,
                          args.public, args.bucket, mutable=False):
                failed.append(key)

    # 목차는 맨 마지막. 있는데 못 받는 것보다, 있는데 목차에 아직 없는 편이 낫다.
    build = subprocess.run(
        ["uv", "run", "python", str(ROOT / "scripts" / "build_index.py")],
        cwd=ROOT, check=False, capture_output=True, text=True)
    if build.returncode != 0:
        print(build.stderr, file=sys.stderr)
        return 1
    print(f"\n  목차: index.json  {INDEX.stat().st_size:,} 바이트")
    if args.write and not upload(INDEX, "index.json", JSON, args.public,
                                 args.bucket, mutable=True):
        failed.append("index.json")

    if failed:
        print(f"\n실패: {', '.join(failed)}", file=sys.stderr)
        return 1
    if not args.write:
        print("\n실제로 올리려면 --write 를 붙여라.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
