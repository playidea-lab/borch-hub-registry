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
시작한다. 네 단계이고, **순서가 정해져 있다.**

```bash
# 1. 화물 → 레지스트리 항목 (매니페스트 · 샘플 · 기록 초안)
uv run --with jsonschema python scripts/pack.py     --cargo ~/git/borch-hub/out --name cifar10-resnet18 --version 1.0.0     --base https://models.pilab.kr/cifar10-resnet18/1.0.0 --date 2026-08-19

# 2. 가중치를 CDN 으로. 올린 뒤 공개 주소로 다시 받아 해시를 대조한다
uv run --with boto3 python scripts/upload.py     --file ~/git/borch-hub/out/model.safetensors --bucket borch-hub     --key cifar10-resnet18/1.0.0/model.safetensors --public-base https://models.pilab.kr

# 3. 받는 사람이 될 것 — 이 매니페스트로 실제로 왕복이 도는지 (borch-hub 에서)
npm run roundtrip -- --manifest models/cifar10-resnet18/1.0.0/manifest.json

# 4. 스펙 확인 후 PR
uv run --with jsonschema python scripts/validate.py
```

**2 번이 1 번보다 먼저 병합되면 안 된다.** 매니페스트가 가리키는 바이트가 없으면
받는 쪽은 404 를 만나고, 그것은 우리가 아니라 그 사람이 겪는다.

**3 번을 건너뛰지 말 것.** 1·2 가 성공해도 로더가 그 매니페스트를 소화하는지는
별개다 — 상대 주소와 절대 주소가 한 문서에 섞여 있고, 그 이음매는 실제로 받아 봐야
걸린다. 그리고 `training.md` 초안은 **사람이 읽고 보태라.** 손으로 돌린 실행이라
그 파일 말고는 그 가중치가 어떻게 나왔는지 아는 것이 없다.

## 관련

- `borch` — 런타임 (코어)
- `borch-hub` — 클라이언트 SDK. 이 저장소의 매니페스트를 읽는 쪽
