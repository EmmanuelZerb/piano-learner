"""Vérifie les prérequis locaux. Usage : npm run doctor (depuis la racine)."""

import shutil
import subprocess
import sys

from app.system import device_info, ffmpeg_info, ffprobe_info


def _version(cmd: list[str]) -> str | None:
    if shutil.which(cmd[0]) is None:
        return None
    out = subprocess.run(cmd, capture_output=True, text=True, check=False, shell=False)
    return (out.stdout or out.stderr).strip().splitlines()[0]


def main() -> int:
    node = _version(["node", "--version"])
    node_ok = node is not None and int(node.lstrip("v").split(".")[0]) >= 20
    device = device_info()
    checks: list[tuple[str, bool, str]] = [
        ("Python 3.11", sys.version_info[:2] == (3, 11), sys.version.split()[0]),
        ("ffmpeg", ffmpeg_info().available, ffmpeg_info().version or "absent"),
        ("ffprobe", ffprobe_info().available, ffprobe_info().path or "absent"),
        ("Node >= 20", node_ok, node or "absent"),
        ("torch", device.torch_installed, device.torch_version or "uv sync"),
        ("GPU", device.device != "cpu", f"{device.device} {device.name or ''}".strip()),
    ]
    for name, ok, detail in checks:
        print(f"[{'OK' if ok else '!!'}] {name:<12} {detail}")
    # Le GPU est optionnel (repli CPU) : il ne fait pas échouer le diagnostic.
    return 0 if all(ok for name, ok, _ in checks if name != "GPU") else 1


if __name__ == "__main__":
    sys.exit(main())
