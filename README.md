# borch-hub-registry

`borch` 런타임이 바로 불러 돌릴 수 있는 모델의 **매니페스트와 검증 자료**가 사는 곳이다.

## 여기에 없는 것 — 가중치

가중치 바이트는 이 저장소에 **없다.** 매니페스트가 URL 과 `sha256` 만 들고 있고,
바이트는 CDN(R2)에서 온다.

ResNet-18 하나가 45MB 다. 모델이 스무 개면 저장소가 1GB 가 되고, 클론하는 사람은
자기가 쓸 하나를 위해 스물을 받는다. 그리고 git 은 바이너리의 이력을 압축하지 못해서
같은 모델을 두 번 고치면 90MB 가 영구히 남는다.

대신 **해시를 남긴다.** 코어 저장소가 `tests/browser/assets.lock` 에서 이미 쓰는
방식이다 — 바깥에서 받아온 것은 저장소에 해시만 둔다. 바이트가 갈리면 로더가
받는 자리에서 멈춘다.

## 목차

`index.json` 은 `models/` 를 훑어 만든 **생성물이고 저장소에 안 남는다.** `.gitignore`
가 그 이유를 적어 뒀다 — 커밋하면 매니페스트와 갈릴 자리가 하나 늘고, 갈린 것은
아무도 안 본다. 올릴 때마다 다시 만든다:

```bash
uv run python scripts/build_index.py            # 만든다
uv run python scripts/build_index.py --dry-run  # 만들 수 있는지만 본다 (CI 가 이것을 돌린다)
```

받는 데 필요한 것까지만 담는다 — 이름·판·과제·데이터셋·크기·출신·매니페스트 주소.
전처리 표나 클래스 1000 개는 **고른 다음** 필요한 것이라 매니페스트에 남는다.

## 배치

```
models/<이름>/<버전>/
├── manifest.json          ← 스펙은 schema/manifest.schema.json
├── sample.in.safetensors  ← 배지의 근거. 작다(수십 KB)
├── sample.out.safetensors
└── training.md            ← 이 가중치가 어떻게 나왔는지. 손으로 돌리므로 이것이 유일한 증거다
```

버전은 디렉터리로 가른다. 같은 이름의 모델을 고쳐 올려도 **옛 버전을 가리키던
매니페스트 URL 이 계속 살아 있어야** 하기 때문이다 — 남의 페이지가 그 URL 을 박아
두고 돌고 있다.

## 왜 샘플 입출력이 저장소에 있나

"이 모델이 이 브라우저에서 제대로 도는가"를 **받는 쪽이 스스로 확인할 수 있어야**
배지가 주장이 아니라 사실이 된다. 클라이언트가 `sample.in` 을 넣어 나온 값을
`sample.out` 과 `allclose` 로 대조한다.

가중치와 달리 이건 작고(수십 KB), 매니페스트와 **같이 움직여야** 한다 — 따로 두면
어느 순간 모델은 새것이고 샘플은 옛것인 상태가 되는데, 그때도 검사는 통과한다.

## 모델을 추가하려면

학습이 뱉은 화물(`model.safetensors` · `sample.in` · `sample.out` · `summary.json`)에서
시작한다. 여섯 단계이고, **순서가 정해져 있다.**

```bash
# 1. 화물 → 레지스트리 항목 (매니페스트 · 샘플 · 기록 초안)
uv run --with jsonschema python scripts/pack.py     --cargo ~/git/borch-hub/out --name cifar10-resnet18 --version 1.0.0     --base https://models.pilab.kr/cifar10-resnet18/1.0.0 --date 2026-08-19

# 2. 가중치를 CDN 으로. 올린 뒤 공개 주소로 다시 받아 해시를 대조한다
uv run --with boto3 python scripts/upload.py     --file ~/git/borch-hub/out/model.safetensors --bucket borch-hub     --key cifar10-resnet18/1.0.0/model.safetensors --public-base https://models.pilab.kr

# 3. 받는 사람이 될 것 — 이 매니페스트로 실제로 왕복이 도는지 (borch-hub 에서)
npm run roundtrip -- --manifest models/cifar10-resnet18/1.0.0/manifest.json

# 4. 무엇이 나갈지 먼저 본다 — 매니페스트·샘플·목차 전부
uv run --with boto3 python scripts/publish.py

# 5. 올린다 (자격증명이 있어야 한다)
export R2_ENDPOINT=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
uv run --with boto3 python scripts/publish.py --write

# 6. 스펙 확인 후 PR
uv run --with jsonschema python scripts/validate.py
uv run python scripts/build_index.py --dry-run
```

**2 번이 1 번보다 먼저 병합되면 안 된다.** 매니페스트가 가리키는 바이트가 없으면
받는 쪽은 404 를 만나고, 그것은 우리가 아니라 그 사람이 겪는다.

**4 번이 없으면 아무도 이 모델을 못 쓴다.** 허브의 입구는 `load(매니페스트 주소)`
하나인데, 이 저장소는 비공개다 — 매니페스트가 CDN 에 없으면 **남에게 건넬 수 있는
주소가 세상에 없다.** 가중치 주소는 절대 주소라 잘 열리고 샘플은 상대 주소라 매니페스트를
따라가므로, 로컬에서 서빙하며 검사하면 이 구멍이 통째로 안 보인다(실제로 그랬다).

**`publish.py` 가 한 번에 부르는 것도 그래서다.** 파일마다 `upload.py` 를 셸 반복문으로
부르면, 자격증명 한 줄이 빠졌을 때 **같은 실패가 열다섯 번** 나온다. 화면이 파이썬
역추적으로 가득 차면 사람이 처음 하는 생각은 "스크립트가 깨졌나" 이지 "export 를 안
했구나" 가 아니다 — 실제로 두 번 그랬다. 한 번만 부르면 시작하기 전에 다 보고 한 번만
말한다. 파일별 되받기 확인과 덮어쓰기 금지는 그대로 `upload.py` 가 한다.

**기본이 미리보기다.** 공개 CDN 에 쓰는 명령이므로 `--write` 를 손으로 적게 한다.

**목차만 `--mutable` 로 나간다.** 버전이 박힌 자산에 그것을 쓰면 이미 나간 매니페스트를
덮어쓸 수 있게 되고, 그 손해는 되돌릴 수 없다. 목차는 반대로 바뀌어야 하는 물건이라
`immutable` 이 붙으면 받은 사람이 1 년 동안 옛 목차를 쥔다.

**3 번을 건너뛰지 말 것.** 1·2 가 성공해도 로더가 그 매니페스트를 소화하는지는
별개다 — 상대 주소와 절대 주소가 한 문서에 섞여 있고, 그 이음매는 실제로 받아 봐야
걸린다. 그리고 `training.md` 초안은 **사람이 읽고 보태라.** 손으로 돌린 실행이라
그 파일 말고는 그 가중치가 어떻게 나왔는지 아는 것이 없다.

## 관련

- `borch` — 런타임 (코어)
- `borch-hub` — 클라이언트 SDK. 이 저장소의 매니페스트를 읽는 쪽
