"""가중치를 CDN 에 올린다 — **운영자의 단계다.**

    export R2_ENDPOINT=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
    uv run --with boto3 python scripts/upload.py \
        --file ~/git/borch-hub/out/model.safetensors \
        --bucket borch-hub --key cifar10-resnet18/1.0.0/model.safetensors \
        --public-base https://models.pilab.kr

주소도 자격도 전부 환경에서 온다. 여기 박아 두면 버킷을 옮기는 날 이 저장소를
고쳐야 하고, 자격은 애초에 저장소에 있을 것이 아니다.

## 왜 매니페스트보다 먼저인가

매니페스트가 먼저 병합되면 받는 쪽이 404 를 만난다. 바이트가 먼저 서 있고
매니페스트가 그것을 가리키는 순서여야 한다.

## 헤더 둘

- `Content-Type: application/octet-stream` — safetensors 는 알려진 타입이 없다
- `Cache-Control: public, max-age=31536000, immutable` — 경로에 버전이 박혀 있고
  받는 쪽이 해시로 검증한다. 바뀔 수 없는 물건이므로 immutable 이 정확한 표시이고,
  그것이 붙으면 두 번째 방문자는 재검증 왕복조차 안 한다
"""

import argparse
import hashlib
import os
import pathlib
import sys
import urllib.request

CACHE_FOREVER = "public, max-age=31536000, immutable"
OCTET = "application/octet-stream"


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--file", required=True)
    p.add_argument("--bucket", required=True)
    p.add_argument("--key", required=True)
    p.add_argument("--public-base", required=True, help="공개 주소의 뿌리")
    p.add_argument("--content-type", default=OCTET)
    args = p.parse_args()

    path = pathlib.Path(args.file).expanduser().resolve()
    if not path.exists():
        print(f"파일이 없다: {path}", file=sys.stderr)
        return 2
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()

    import boto3
    from botocore.config import Config

    s3 = boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"], region_name="auto",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )

    # 같은 열쇠에 다른 바이트를 덮어쓰는 것은 **이미 배포된 매니페스트를 거짓말로
    # 만드는 일**이다. 받는 쪽은 해시가 안 맞는다고 멈추고, 왜인지는 모른다.
    exists = True
    try:
        head = s3.head_object(Bucket=args.bucket, Key=args.key)
    except s3.exceptions.ClientError:
        exists = False

    if exists:
        if head["ContentLength"] == len(raw):
            print(f"이미 있다(같은 길이): {args.key} — 올리지 않는다")
        else:
            print(f"이미 있고 길이가 다르다: {args.key}\n"
                  "  버전 경로를 새로 잡아라. 덮어쓰면 그 주소를 적은 매니페스트가 거짓이 된다.",
                  file=sys.stderr)
            return 1
    else:
        print(f"올린다: {args.key} ({len(raw):,} 바이트)")
        s3.put_object(
            Bucket=args.bucket, Key=args.key, Body=raw,
            ContentType=args.content_type, CacheControl=CACHE_FOREVER,
            Metadata={"sha256": digest},
        )

    # **공개 주소로 다시 받아 대조한다.** S3 로 넣었다고 CDN 에서 나오는 것은 아니다 —
    # 도메인 연결이 안 됐거나 캐시가 옛것을 쥐고 있으면 여기서 갈린다.
    url = f"{args.public_base.rstrip('/')}/{args.key}"
    with urllib.request.urlopen(url) as res:
        got = res.read()
        headers = {k.lower(): v for k, v in res.headers.items()}
    back = hashlib.sha256(got).hexdigest()
    print(f"\n공개 주소: {url}")
    print(f"  받은 길이 {len(got):,} · sha256 {'맞다' if back == digest else '다르다'}")
    print(f"  content-type: {headers.get('content-type')}")
    print(f"  cache-control: {headers.get('cache-control')}")
    print(f"  accept-ranges: {headers.get('accept-ranges')}")
    if back != digest:
        print("\n공개 주소가 다른 바이트를 준다.", file=sys.stderr)
        return 1
    print(f"\nsha256: {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
