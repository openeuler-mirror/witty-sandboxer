# sandbox-image / docker

本目录存放沙箱运行所需 Docker 镜像的说明与准备脚本。镜像从公网 Docker Hub 拉取，镜像名与 OpenSandbox 默认值一致，拉取后可直接使用。

## 一键准备

需要 root 权限，且当前环境可以访问公网：

```bash
sudo bash setup-docker.sh
```

脚本会安装 moby（docker 的上游社区版实现）、启动 docker，并拉取下列镜像：

- `opensandbox/code-interpreter:v1.1.0`
- `opensandbox/execd:v1.1.0`

## 手动步骤

### 1. 安装并启动 docker

在使用 `dnf` 的系统上安装 moby：

```bash
sudo dnf install -y moby
sudo systemctl enable --now docker
```

### 2. 拉取镜像

```bash
docker pull opensandbox/code-interpreter:v1.1.0
docker pull opensandbox/execd:v1.1.0
```

可用 `docker images` 确认镜像已就绪。
