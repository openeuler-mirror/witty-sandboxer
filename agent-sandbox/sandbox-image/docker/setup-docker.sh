#!/bin/bash
###############################################################################
# setup-docker.sh
# 沙箱运行依赖的 Docker 准备工作脚本
#
# 用途：安装 docker，并从公网镜像仓库拉取沙箱运行所需镜像。
#       镜像名与 OpenSandbox 默认值一致，拉取后可直接使用。
#
# 使用：sudo bash setup-docker.sh
###############################################################################

set -euo pipefail

# Docker Hub 上的公网镜像，与 OpenSandbox 默认镜像名一致
SANDBOX_IMAGES=(
  "opensandbox/code-interpreter:v1.1.0"
  "opensandbox/execd:v1.1.0"
)

# 必须 root 执行
if [ "$(id -u)" -ne 0 ]; then
  echo "错误：请使用 root 或 sudo 执行本脚本" >&2
  exit 1
fi

echo "==> [1/2] 安装 moby（docker 社区版实现）"
dnf install -y moby

systemctl enable --now docker

echo "==> [2/2] 从公网拉取沙箱镜像"
for image in "${SANDBOX_IMAGES[@]}"; do
  echo "    docker pull ${image}"
  docker pull "${image}"
done

echo "==> 完成。可执行 'docker images' 确认镜像已就绪。"
