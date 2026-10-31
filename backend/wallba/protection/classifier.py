"""Clasificación explicable por nombre, extensión y ubicación.

No abre archivos. Una coincidencia es un indicador, no una prueba de que el
contenido sea secreto. El nivel es el más alto entre las reglas que aplican;
no hay una puntuación numérica.
"""

from __future__ import annotations

from dataclasses import dataclass

RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
SOURCE_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".java",
    ".kt", ".rb", ".php", ".cs", ".cpp", ".c", ".h", ".md", ".txt", ".rst",
}
CRITICAL_FILENAMES = {
    ".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "credentials.json", "secrets.json", "secrets.yaml", "secrets.yml",
    "service-account.json", "gcloud.json",
}
CRITICAL_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx", ".keystore", ".jks", ".ppk"}
CRITICAL_DIRECTORIES = {".ssh", ".aws", ".gnupg", "secrets", "credentials", "private"}
HIGH_FILENAMES = {"terraform.tfvars", "terraform.tfvars.json", "kubeconfig", ".htpasswd", "id_rsa.pub"}
HIGH_SUFFIXES = {".sql", ".dump", ".bak", ".sqlite", ".sqlite3", ".db", ".tfvars"}
HIGH_DIRECTORIES = {".github", "infra", "deploy", "deployment", "k8s", "kubernetes", "helm", ".azure", ".gcp"}
SECRET_TOKENS = ("secret", "credential", "password", "passwd", "token", "private-key", "private_key", "apikey", "api_key")
ACCESS_NAMES = {"auth.json", "auth.yaml", "auth.yml", "permissions.json", "permissions.yaml", "policy.json", "policy.yaml"}
PRIVATE_TOKENS = ("confidencial", "confidential", "nomina", "nómina", "payroll", "financiero", "financial")
INFRA_PARTS = {"infra", "deploy", "deployment", "k8s", "kubernetes", "helm", ".github"}


@dataclass(frozen=True)
class Classification:
    risk: str
    category: str
    reasons: tuple[str, ...]


def _raise(level: str, category: str, reason: str, best: list[str], reasons: list[str]) -> None:
    reasons.append(reason)
    if RISK_ORDER[level] > RISK_ORDER[best[0]]:
        best[0] = level
        best[1] = category


def classify_path(relative_path: str, kind: str, *, symlink_escapes: bool = False) -> Classification:
    name = relative_path.rsplit("/", 1)[-1]
    lowered = name.lower()
    parts = [part.lower() for part in relative_path.split("/") if part]
    reasons: list[str] = []
    best = ["LOW", "general"]

    if kind == "symlink":
        if symlink_escapes:
            _raise(
                "HIGH",
                "access_config",
                "El enlace apunta fuera del proyecto. No se sigue ni se lee el destino.",
                best,
                reasons,
            )
        else:
            _raise(
                "MEDIUM",
                "access_config",
                "Es un enlace simbólico. No se sigue ni se lee el destino.",
                best,
                reasons,
            )
        return Classification(best[0], best[1], tuple(reasons))

    if kind == "directory":
        if lowered in CRITICAL_DIRECTORIES:
            _raise(
                "CRITICAL",
                "credentials",
                f"La carpeta «{name}» coincide con una ubicación habitual de claves o secretos. No se leyó su contenido.",
                best,
                reasons,
            )
        elif lowered in HIGH_DIRECTORIES:
            _raise(
                "HIGH",
                "infrastructure",
                f"La carpeta «{name}» coincide con una ubicación habitual de infraestructura o despliegue.",
                best,
                reasons,
            )
        else:
            reasons.append("El nombre de la carpeta no coincide con un patrón sensible.")
        return Classification(best[0], best[1], tuple(reasons))

    suffix = "" if lowered.startswith(".env") else _suffix(lowered)
    source = suffix in SOURCE_SUFFIXES

    if lowered in CRITICAL_FILENAMES or lowered.startswith(".env"):
        _raise(
            "CRITICAL",
            "credentials",
            "El nombre coincide con un archivo habitual de secretos o variables de entorno. No se leyó el contenido.",
            best,
            reasons,
        )
    if suffix in CRITICAL_SUFFIXES:
        _raise(
            "CRITICAL",
            "credentials",
            "La extensión es habitual en claves o almacenes criptográficos. No se leyó el contenido.",
            best,
            reasons,
        )
    if any(token in lowered for token in SECRET_TOKENS):
        if source:
            _raise(
                "MEDIUM",
                "credentials",
                "El nombre contiene un término de secreto, pero la extensión es de código o texto. No demuestra que haya una credencial.",
                best,
                reasons,
            )
        else:
            _raise(
                "HIGH",
                "credentials",
                "El nombre contiene un término asociado a secretos. No demuestra que el archivo guarde una credencial y no se leyó.",
                best,
                reasons,
            )
    if lowered in HIGH_FILENAMES or suffix in HIGH_SUFFIXES:
        category = "database" if suffix in {".sql", ".dump", ".bak", ".sqlite", ".sqlite3", ".db"} else "infrastructure"
        _raise(
            "HIGH",
            category,
            "El nombre o la extensión coinciden con respaldos, bases locales o configuración de infraestructura. No se leyó el contenido.",
            best,
            reasons,
        )
    if any(part in INFRA_PARTS for part in parts[:-1]) and suffix in {".yml", ".yaml", ".json", ".tf", ".env"}:
        _raise(
            "HIGH",
            "infrastructure",
            "Está en una ruta de infraestructura y usa un formato de configuración. No se leyó el contenido.",
            best,
            reasons,
        )
    if lowered in ACCESS_NAMES or "auth" in parts[:-1] and suffix in {".json", ".yml", ".yaml", ".conf"}:
        _raise(
            "MEDIUM",
            "access_config",
            "El nombre o la carpeta sugieren configuración de acceso. No se comprobó si contiene secretos.",
            best,
            reasons,
        )
    if any(token in lowered for token in PRIVATE_TOKENS):
        _raise(
            "MEDIUM",
            "private_data",
            "El nombre sugiere material interno o financiero. No se leyó el contenido ni se asume que haya datos personales.",
            best,
            reasons,
        )
    if not reasons:
        reasons.append("Sin indicadores de nombre, extensión o ubicación asociados a material sensible.")
    return Classification(best[0], best[1], tuple(reasons))


def _suffix(lowered_name: str) -> str:
    if lowered_name.startswith(".") and lowered_name.count(".") == 1:
        return ""
    dot = lowered_name.rfind(".")
    if dot <= 0:
        return ""
    return lowered_name[dot:]


def extension_label(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith(".env"):
        return "env"
    suffix = _suffix(lowered)
    return suffix[1:] if suffix.startswith(".") else suffix
