# MemOS v2.0.25 source-lock 换锁记录

日期：2026-07-26

## 1. 裁决

MemOS Phase 1 接入锁定官方最新稳定 release：

```text
upstream  https://github.com/MemTensor/MemOS.git
tag       v2.0.25
commit    e820406269537b97d270687e3e40eea2f015f81a
released  2026-07-24T16:47:37+08:00
```

不锁浮动 `main`。核验时远端 `main@3fd109e7` 只比 release 多一个
`feat: add Yunxiao sync preflight (#2159)`；该状态没有 release 身份，且未来会继续漂移。
对 benchmark 框架而言，可复现的最新稳定 release 优先于“今天最新的 branch tip”。

## 2. 一手核验

远端：

```text
$ git ls-remote --symref https://github.com/MemTensor/MemOS.git HEAD
ref: refs/heads/main HEAD
3fd109e7cbaba291af2253f107e0a595dbf62b00 HEAD

$ git ls-remote --tags --refs https://github.com/MemTensor/MemOS.git
...
e820406269537b97d270687e3e40eea2f015f81a refs/tags/v2.0.25
```

本地换锁后：

```text
$ git -C third_party/methods/MemOS status --short --branch
## HEAD (no branch)

$ git -C third_party/methods/MemOS rev-parse HEAD
e820406269537b97d270687e3e40eea2f015f81a

$ git -C third_party/methods/MemOS describe --tags --exact-match
v2.0.25
```

`pyproject.toml` 在该 tag 声明 `version = "2.0.25"`、Python `>=3.10`。父仓库的
`.gitignore` 明确忽略 `third_party/methods/MemOS/`，因此 source identity 必须同时写入
tracked `third_party/methods/MANIFEST.md` 和恢复脚本，不能只依赖本机 nested Git HEAD。

## 3. 为什么不删除后重克隆

原目录是 clean 的官方 nested Git 仓库，remote 已指向同一 upstream。执行
`fetch --tags --prune` 后 checkout 精确 tag，工作树内容与重新 clone 后 checkout
该 commit 等价，同时保留：

- 完整 remote/tag/commit provenance；
- 从 `v2.0.22` 做差量审计的能力；
- 一步 checkout 回滚能力；
- 不存在“先删后拉失败”留下半成品目录的窗口。

因此“受控换锁”优于物理删除。

## 4. 旧审计的失效边界

旧锁点是 `v2.0.22@b051e638`。到 `v2.0.25@e820406`：

```text
repository-wide: 221 files changed, 13802 insertions(+), 1588 deletions(-)
src/memos + evaluation + pyproject.toml:
50 files changed, 1640 insertions(+), 471 deletions(-)
```

承重变化覆盖：

- `src/memos/api/{client,config,product_models,server_api*}.py`；
- product search handler、API lifecycle 与 config builders；
- embedder base/cache/factory/universal API；
- mem-reader config、parser 与 prompts；
- tree-text recall/searcher、single-cube 与 scheduler config；
- LoCoMo/LongMemEval evaluation scripts。

所以 2026-07-05 的 `memos.md` / `mechanism-memos.md` 可继续提供术语、旧路径和风险问题，
但以下内容必须在 M1 对 current source 重新取证：

- 产品入口与 payload/response；
- `general_text`/`tree_text` 配置与默认值；
- search readout、source/score/ranking；
- scheduler/reorganizer 完成语义；
- official harness 与产品路径的对应关系；
- embedding/LLM/服务依赖。

五个 benchmark 自身没有换锁，不重开 raw census。

## 5. 可复现恢复

新机器从父仓库根目录执行：

```bash
bash scripts/fetch_third_party_methods.sh
```

脚本会 clone upstream 并 checkout `e820406269537b97d270687e3e40eea2f015f81a`。
若目录已经存在，脚本按既有安全语义跳过，不擅自覆盖本地工作。

## 6. 下一门

先完成一份 `v2.0.25` source-delta/product-identity M1 ruling，再决定 adapter 形态。
在此之前：

- 不运行真实 API；
- 不启动 Qdrant/Neo4j/MemOS server；
- 不改 vendored 算法；
- 不按五个 benchmark 重复派调查卡；
- 不把 `v2.0.22` 行号写成 current evidence。
