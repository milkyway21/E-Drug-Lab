# DrugCLIP 恢复 — 问题总结

## 当前状态

- **drugclip-api:latest** 镜像已构建成功（2.65GB），image ID: `0bb7e07b77a8`
- **模型文件** `deliverables/drugclip-package/models/checkpoint_best.pt` 存在
- **Dockerfile** 修复完成（加了 `--no-build-isolation` 解决 unicore 安装问题）

## 核心问题：WSL ext4 文件系统 I/O 损坏

Docker 的 containerd 存储层（`/var/lib/containerd`）有大量 I/O 错误，`rm` 无法删除损坏的 blob 文件。具体症状：

### 症状

1. **容器启动失败**: `exec /usr/local/bin/python: input/output error`
2. **rm 失败**: `rm: cannot remove '/var/lib/containerd/.../blobs/sha256/...': Input/output error`
3. **containerd 启动失败**: bbolt 数据库损坏 — `go.etcd.io/bbolt` panic
4. **Docker daemon 启动失败**: containerd socket 连接超时
5. **系统命令也 I/O 错误**: `mkdir`, `systemctl` 有时也报 I/O error

### 根因

WSL2 ext4.vhdx 文件（75GB，在 `E:\WSL\eDrugUbuntu\ext4.vhdx`）的文件系统元数据损坏。Docker 频繁的写入 + WSL 突然关闭导致 ext4 元数据不一致。

## 需要手工解决的步骤

### 方法一：修复现有 VHDX（推荐先试）

```powershell
# 1. 彻底关闭 WSL
wsl --shutdown

# 2. 用 fsck 修复 ext4 文件系统
# 在 WSL 内执行（需要在 Linux 下，或者启动时指定 root）
wsl -d eDrugUbuntu -u root
e2fsck -f /dev/sdb  # 或对应设备

# 3. 如果 fsck 不行，用 diskpart 压缩/修复 VHDX
diskpart
select vdisk file="E:\WSL\eDrugUbuntu\ext4.vhdx"
attach vdisk readonly
compact vdisk
detach vdisk
exit

# 4. 重新启动 Docker
wsl -d eDrugUbuntu -u root
systemctl start docker
```

### 方法二：重建 Docker 存储（如果方法一不行）

```bash
# 在 WSL root 下执行
systemctl stop docker docker.socket containerd

# 用 rm -rf 删不掉损坏文件时，用 find -delete
find /var/lib/containerd -type f -delete 2>/dev/null
find /var/lib/containerd -type d -delete 2>/dev/null
find /var/lib/docker -type f -delete 2>/dev/null
find /var/lib/docker -type d -delete 2>/dev/null

# 重建目录
mkdir -p /var/lib/docker /var/lib/containerd

# 启动
systemctl start containerd
systemctl start docker
```

### 方法三：重建 WSL 分发版（终极方案）

如果 VHDX 损坏无法修复：

```powershell
# 1. 导出当前配置（记住已安装的包）
wsl --export eDrugUbuntu E:\WSL\eDrugUbuntu_backup.tar

# 2. 注销并重新安装
wsl --unregister eDrugUbuntu
wsl --import eDrugUbuntu E:\WSL\eDrugUbuntu E:\path\to\ubuntu.tar --version 2

# 3. 重新安装 Docker
# 运行 deliverables/drugclip-package/scripts/install_docker_ubuntu.sh

# 4. 重新构建镜像
cd E:\e-drug-lab\deliverables\drugclip-package
wsl -d eDrugUbuntu docker build -t drugclip-api:latest .
```

## 恢复后启动命令

Docker 修复后：

```bash
# 启动 drugclip 容器（端口 8500）
wsl -d eDrugUbuntu docker run -d --name drugclip-api -p 8500:8500 \
  -v /mnt/e/e-drug-lab/deliverables/drugclip-package/models:/app/models:ro \
  -v /mnt/e/e-drug-lab/deliverables/drugclip-package/data:/app/data \
  -v /mnt/e/e-drug-lab/deliverables/drugclip-package/work:/app/work \
  -e DRUGCLIP_MODEL_DIR=/app/models \
  -e DRUGCLIP_DATA_DIR=/app/data \
  -e DRUGCLIP_WORK_DIR=/app/work \
  drugclip-api:latest \
  python -m uvicorn app.api_server:app --host 0.0.0.0 --port 8500

# 验证
curl http://localhost:8500/health
```

## 已知的 Docker daemon.json

当前配置（`/etc/docker/daemon.json`）：
```json
{
    "dns": ["8.8.8.8", "8.8.4.4"],
    "registry-mirrors": ["https://docker.1ms.run"],
    "runtimes": {
        "nvidia": {
            "args": [],
            "path": "nvidia-container-runtime"
        }
    }
}
```

- `docker.1ms.run` 是可用的中国镜像（docker.xuanyuan.me 已 429 限流，已移除）
- NVIDIA runtime 已配置（RTX 5080 GPU 支持）
