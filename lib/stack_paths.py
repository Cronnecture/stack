"""Resolve the Cronnecture stack root and nested Ansible fleet."""

from __future__ import annotations

import os
from pathlib import Path


def _stack_usable(path: Path) -> bool:
    return path.is_dir() and (path / "deploy.sh").is_file() and (path / "kubernetes").is_dir()


def _ansible_usable(path: Path) -> bool:
    return path.is_dir() and (path / "ansible.cfg").is_file() and (path / "config" / "inventory").is_dir()


def stack_root() -> Path:
    env = os.environ.get("STACK_ROOT", "").strip()
    if env and _stack_usable(Path(env)):
        return Path(env).resolve()
    here = Path(__file__).resolve().parent
    for cand in (here.parent, Path("/home/dev/stack")):
        if _stack_usable(cand):
            return cand.resolve()
    return here.parent


def ansible_dir() -> Path:
    for key in ("FLEET_ROOT", "ANSIBLE_DIR"):
        env = os.environ.get(key, "").strip()
        if env and _ansible_usable(Path(env)):
            return Path(env).resolve()
    nested = stack_root() / "ansible"
    if _ansible_usable(nested):
        return nested.resolve()
    return nested


def apps_dir() -> Path:
    return stack_root() / "apps"


def docs_dir() -> Path:
    return stack_root() / "docs"


def vault_file() -> Path:
    return ansible_dir() / "config" / "inventory" / "group_vars" / "all" / "vault.yml"


def vault_pass_file() -> Path:
    env = os.environ.get("ANSIBLE_VAULT_PASSWORD_FILE", "").strip()
    if env and Path(env).is_file():
        return Path(env)
    home = Path.home() / ".ansible" / "vault_pass"
    if home.is_file():
        return home
    return Path("/home/dev/.ansible/vault_pass")
