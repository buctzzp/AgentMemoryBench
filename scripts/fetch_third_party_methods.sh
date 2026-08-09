#!/usr/bin/env bash
# 用途：按 MANIFEST.md 固定的 upstream 与 commit 恢复 local-only 第三方 method 仓库。

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
METHODS_DIR="${ROOT_DIR}/third_party/methods"

fetch_method() {
  local dir_name="$1"
  local repo_url="$2"
  local commit_hash="$3"
  local target_dir="${METHODS_DIR}/${dir_name}"

  if [[ -d "${target_dir}" ]]; then
    printf 'skip %s: directory already exists\n' "${dir_name}"
    return 0
  fi

  git clone "${repo_url}" "${target_dir}"
  git -C "${target_dir}" checkout "${commit_hash}"
}

apply_method_patch() {
  local dir_name="$1"
  local patch_path="$2"
  local target_dir="${METHODS_DIR}/${dir_name}"

  if git -C "${target_dir}" apply --unidiff-zero --reverse --check "${patch_path}" >/dev/null 2>&1; then
    printf 'skip %s patch: already applied\n' "${dir_name}"
    return 0
  fi
  git -C "${target_dir}" apply --unidiff-zero --check "${patch_path}"
  git -C "${target_dir}" apply --unidiff-zero "${patch_path}"
  printf 'applied %s patch: %s\n' "${dir_name}" "${patch_path}"
}

fetch_method "MemOS" "https://github.com/MemTensor/MemOS.git" "e820406269537b97d270687e3e40eea2f015f81a"
apply_method_patch "MemOS" "${ROOT_DIR}/scripts/patches/memos-product-runtime-observability.patch"
fetch_method "SimpleMem" "https://github.com/aiming-lab/SimpleMem.git" "60a48e83a7fef10d386e1f438589047d3a4257bc"
apply_method_patch "SimpleMem" "${ROOT_DIR}/scripts/patches/simplemem-product-compat.patch"
fetch_method "cognee" "https://github.com/topoteretes/cognee.git" "f7e2267cf02f5df15c4b60bf196b30ac2c06b32d"
fetch_method "langmem" "https://github.com/langchain-ai/langmem.git" "56d85939d80bb731bd5e237567148d817d7bfd16"
fetch_method "letta" "https://github.com/letta-ai/letta.git" "b76da9092518cbaa2d09042e52fdcbde69243e18"
fetch_method "supermemory" "https://github.com/supermemoryai/supermemory.git" "566be208981aa23ef20a85fd50a737861b1b10b2"
fetch_method "EverOS" "https://github.com/EverMind-AI/EverOS.git" "48fc9084888bc17100053227284f939a5aca5e91"
apply_method_patch "EverOS" "${ROOT_DIR}/scripts/patches/everos-product-runtime-observability.patch"
