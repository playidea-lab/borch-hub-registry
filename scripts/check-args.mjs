/**
 * 매니페스트의 `arch.args` 가 팩토리 규격에 맞는지 **카탈로그에게 직접 물어본다.**
 *
 *     npm i --no-save --no-package-lock bimm-ts borch-ts
 *     node scripts/check-args.mjs
 *
 * ## 왜 스키마로는 안 되는가
 *
 * 스키마는 `args` 가 객체인지까지만 본다. 팩토리마다 무엇을 받는지는 카탈로그가 알고,
 * 그 표를 여기 옮겨 적으면 **두 벌이 되고 두 벌은 갈린다.** 그래서 복제하지 않고
 * 부른다 — 규격은 `factorySpec` 이 말해 주고 검사는 `checkArgs` 가 한다.
 *
 * 이것이 없던 동안 `numClases: 10` 같은 오타는 병합을 통과했다. 스키마가 통과시키고,
 * 받는 쪽에서 처음 드러나는 종류다.
 *
 * ## GPU 가 없는 러너에서 도는 이유
 *
 * bimm 은 인자 검사를 모델 만들기 **앞에** 두고, 그 코드에 코어 임포트를 두지 않았다.
 * 층이 곧 텐서라 모델은 WebGPU 어댑터 없이 못 서지만, 값이 틀렸다는 것은 어댑터 없이
 * 안다. 그 분리가 있어야 레지스트리 CI 가 매니페스트를 볼 수 있고, 이 파일이 그
 * 주장을 실제로 쓴다.
 *
 * ## 판 1 매니페스트는 건너뛴다
 *
 * `library` 가 없던 판 1 의 이름을 지금 이름으로 잇는 표는 borch-hub 에 있고, 그
 * 패키지는 아직 npm 에 없다. 표를 여기 옮겨 적으면 세 번째 사본이 된다. 건너뛴 것은
 * **말한다** — 말없이 건너뛰면 초록색이 "다 봤다"로 읽히는데, 안 본 것이 있으면
 * 그건 거짓말이다. borch-hub 이 나가는 날 이 갈래는 사라진다.
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

import { BimmError, checkArgs, factorySpec } from "bimm-ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const MODELS = join(ROOT, "models");

/** `models/<이름>/<판>/manifest.json` 전부. validate.py 가 보는 것과 같은 자리다. */
function manifests() {
  const found = [];
  for (const name of readdirSync(MODELS)) {
    const model = join(MODELS, name);
    if (!statSync(model).isDirectory()) continue;
    for (const version of readdirSync(model)) {
      const path = join(model, version, "manifest.json");
      try {
        if (statSync(path).isFile()) found.push(path);
      } catch {
        // 매니페스트가 없는 디렉터리는 validate.py 가 자기 말로 말한다.
      }
    }
  }
  return found.sort();
}

const problems = [];
const skipped = [];

for (const path of manifests()) {
  const rel = relative(ROOT, path);
  const arch = JSON.parse(readFileSync(path, "utf8")).arch;

  if (arch?.library === undefined) {
    skipped.push(rel);
    continue;
  }

  const name = `${arch.library}/${arch.factory}`;
  try {
    checkArgs(name, factorySpec(arch.library, arch.factory), arch.args ?? {});
  } catch (err) {
    // 카탈로그가 거절한 것만 문제로 센다. 그 밖의 예외는 이 스크립트의 버그이므로
    // 삼키지 않고 그대로 올린다.
    if (!(err instanceof BimmError)) throw err;
    problems.push(`${rel}: ${err.message}`);
  }
}

for (const line of problems) console.error(line);
for (const rel of skipped) {
  console.error(`${rel}: 판 1 매니페스트라 인자를 못 봤습니다 — 이름 표가 borch-hub 에 있습니다.`);
}

if (problems.length > 0) {
  console.error(`\n매니페스트 ${problems.length + skipped.length}건 중 문제 ${problems.length}건`);
  process.exit(1);
}

const seen = manifests().length - skipped.length;
console.log(`인자를 본 매니페스트 ${seen}개 — 문제 없음 (판 1 ${skipped.length}개는 건너뜀)`);
