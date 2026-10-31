"""Clasificación por nombre, extensión y carpeta. No abre el archivo."""

from __future__ import annotations

from dataclasses import dataclass

ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
SOURCE = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".md", ".txt"}
CRITICAL_NAMES = {".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", "credentials.json", "secrets.json"}
CRITICAL_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}
CRITICAL_DIRS = {".ssh", ".aws", ".gnupg", "secrets", "credentials", "private"}
HIGH_SUFFIXES = {".sql", ".dump", ".bak", ".sqlite", ".sqlite3", ".db", ".tfvars"}
HIGH_DIRS = {".github", "infra", "deploy", "k8s", "kubernetes", "helm"}
SECRET_WORDS = ("secret", "credential", "password", "token", "apikey", "api_key", "private_key")


@dataclass(frozen=True)
class Classification:
    risk: str
    category: str
    reasons: tuple[str, ...]


def _bump(level: str, category: str, reason: str, best: list[str], reasons: list[str]) -> None:
    reasons.append(reason)
    if ORDER[level] > ORDER[best[0]]:
        best[0] = level
        best[1] = category


def classify(relative_path: str, kind: str) -> Classification:
    name = relative_path.rsplit("/", 1)[-1].lower()
    parts = [part.lower() for part in relative_path.split("/") if part]
    reasons: list[str] = []
    best = ["LOW", "general"]
    if kind == "symlink":
        _bump("MEDIUM", "access_config", "Es un enlace. No se sigue ni se lee el destino.", best, reasons)
        return Classification(best[0], best[1], tuple(reasons))
    if kind == "directory":
        if name in CRITICAL_DIRS:
            _bump("CRITICAL", "credentials", f"La carpeta «{name}» suele guardar claves. No se leyó su contenido.", best, reasons)
        elif name in HIGH_DIRS:
            _bump("HIGH", "infrastructure", f"La carpeta «{name}» suele alojar infraestructura.", best, reasons)
        else:
            reasons.append("El nombre de la carpeta no coincide con un patrón sensible.")
        return Classification(best[0], best[1], tuple(reasons))
    suffix = "" if name.startswith(".") and name.count(".") == 1 else (name[name.rfind("."):] if "." in name[1:] else "")
    if name in CRITICAL_NAMES or name.startswith(".env"):
        _bump("CRITICAL", "credentials", "El nombre coincide con un archivo habitual de secretos. No se leyó el contenido.", best, reasons)
    if suffix in CRITICAL_SUFFIXES:
        _bump("CRITICAL", "credentials", "La extensión es habitual en material criptográfico. No se leyó el contenido.", best, reasons)
    if any(word in name for word in SECRET_WORDS):
        if suffix in SOURCE:
            _bump("MEDIUM", "credentials", "El nombre sugiere un secreto, pero la extensión es de código o texto. No es una prueba.", best, reasons)
        else:
            _bump("HIGH", "credentials", "El nombre contiene un término de secreto. No se leyó el contenido.", best, reasons)
    if suffix in HIGH_SUFFIXES or name in {"terraform.tfvars", "kubeconfig"}:
        category = "database" if suffix in {".sql", ".dump", ".bak", ".sqlite", ".sqlite3", ".db"} else "infrastructure"
        _bump("HIGH", category, "El nombre o la extensión coinciden con respaldos o infraestructura. No se leyó el contenido.", best, reasons)
    if not reasons:
        reasons.append("Sin indicadores de nombre, extensión o ubicación asociados a material sensible.")
    return Classification(best[0], best[1], tuple(reasons))
