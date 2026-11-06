"""Tool registry, security policy (default DENY), audit log and network isolation.

The router (rules or a local model such as FunctionGemma) only proposes a tool
call. This module decides whether the call may run:

  Gate 1  Authentication  – the local OS user of this single-workstation pilot
                            (no SSO/Entra ID in the pilot, see documentation)
  Gate 2  Authorization   – per-user profile: tools, chapters, operations
  Gate 3  Tool allowlist  – only enabled tools from tool_registry.json
  Gate 4  Network         – no internet in INTERNAL_RESTRICTED; outbound
                            connections of this process are blocked
  Gate 5  Audit           – every decision is logged without prompt content
"""
from __future__ import annotations

import fnmatch
import getpass
import hashlib
import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from pathlib import Path

from .storage import LOCK, now_iso

STATUS_MAP = {"Draft": "DRAFT", "Reviewed": "REVIEWED", "Released": "CONFIRMED", "Rejected": "REJECTED"}
FREE_TEXT = {"query"}


class PolicyError(ValueError):
    def __init__(self, message: str, status: int = 403):
        super().__init__(message)
        self.status = status


@dataclass
class Decision:
    allowed: bool
    tool: str
    operation: str = ""
    classification: str = ""
    reason: str = ""
    arguments: dict = field(default_factory=dict)
    confirmation_required: bool = False

    def as_dict(self):
        return {"result": "ALLOWED" if self.allowed else "DENIED", "tool": self.tool, "operation": self.operation,
                "classification": self.classification, "reason": self.reason,
                "confirmationRequired": self.confirmation_required}


# ------------------------------------------------------------------------------ Gate 4: network
_ORIGINAL_CONNECT = socket.socket.connect
_ORIGINAL_CONNECT_EX = socket.socket.connect_ex
_ALLOWED_NETWORKS: list = []
_GUARD_ACTIVE = False


def _address_allowed(address) -> bool:
    if not isinstance(address, tuple) or not address:
        return True  # AF_UNIX and other local transports
    host = address[0]
    try:
        ip = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return host in ("localhost",)
    return ip.is_loopback or any(ip in net for net in _ALLOWED_NETWORKS)


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _address_allowed(address):
        raise PermissionError(f"Netzwerkzugriff blockiert (INTERNAL_RESTRICTED): {address[0]}")
    return _ORIGINAL_CONNECT(self, address)


def _guarded_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _address_allowed(address):
        raise PermissionError(f"Netzwerkzugriff blockiert (INTERNAL_RESTRICTED): {address[0]}")
    return _ORIGINAL_CONNECT_EX(self, address)


def install_network_guard(internal_networks=()):
    """Block outbound connections of this Python process except loopback and listed internal networks.

    This complements, but does not replace, an OS/firewall rule: other programs on the machine are not affected.
    """
    global _GUARD_ACTIVE
    _ALLOWED_NETWORKS[:] = [ipaddress.ip_network(n, strict=False) for n in internal_networks]
    socket.socket.connect = _guarded_connect
    socket.socket.connect_ex = _guarded_connect_ex
    _GUARD_ACTIVE = True


def network_guard_active() -> bool:
    return _GUARD_ACTIVE


# --------------------------------------------------------------------------------- registry + policy
class PolicyService:
    def __init__(self, registry_path: Path, policy_path: Path, audit_path: Path, user: str | None = None):
        self.registry_path = Path(registry_path)
        self.policy_path = Path(policy_path)
        self.audit_path = Path(audit_path)
        self.user = user or getpass.getuser() or "unbekannt"
        self.registry = self._load_registry()
        self.policy = self._load_policy()

    def _load_registry(self) -> dict:
        data = json.loads(self.registry_path.read_text(encoding="utf-8"))
        names = set()
        for tool in data.get("tools", []):
            name = tool.get("name", "")
            if not re.fullmatch(r"[a-z][a-z0-9_]{2,60}", name) or name in names:
                raise PolicyError(f"Tool Registry: ungültiger oder doppelter Name „{name}“.", 500)
            names.add(name)
            sec = tool.get("security") or {}
            for key in ("classification", "network", "internet_access", "audit", "allowed_operations", "source"):
                if key not in sec:
                    raise PolicyError(f"Tool Registry: {name} ohne Sicherheitsangabe „{key}“.", 500)
            if sec["internet_access"] is not False:
                raise PolicyError(f"Tool Registry: {name} verlangt Internetzugriff – im Pilot nicht zulässig.", 500)
            if tool.get("parameters", {}).get("type") != "object":
                raise PolicyError(f"Tool Registry: {name} braucht ein JSON-Schema mit type=object.", 500)
        return data

    def _load_policy(self) -> dict:
        policy = json.loads(self.policy_path.read_text(encoding="utf-8"))
        if policy.get("default_policy") != "DENY":
            raise PolicyError("Security Policy: default_policy muss DENY sein.", 500)
        if policy.get("security_mode") == "INTERNAL_RESTRICTED":
            for flag in ("external_network", "external_llm", "external_search", "telemetry_external"):
                if policy.get(flag) is not False:
                    raise PolicyError(f"Security Policy: {flag} muss im Modus INTERNAL_RESTRICTED false sein.", 500)
        return policy

    # -- registry views -------------------------------------------------------------
    def tools(self) -> list[dict]:
        return [t for t in self.registry["tools"] if t.get("enabled", True)]

    def tool(self, name: str) -> dict | None:
        return next((t for t in self.tools() if t["name"] == name), None)

    def declarations(self) -> list[dict]:
        """Function declarations for the model: name, description, JSON schema – no security metadata."""
        return [{"name": t["name"], "description": t["description"], "parameters": t["parameters"]} for t in self.tools()]

    def profile(self, user: str | None = None) -> dict:
        profiles = self.policy.get("profiles", {})
        user = user or self.user
        return profiles.get(user) or profiles.get("*") or {"tools": [], "chapters": [], "operations": []}

    def allowed_chapters(self, user: str | None = None) -> list[str] | None:
        chapters = self.profile(user).get("chapters", [])
        return None if "*" in chapters else list(chapters)

    def summary(self) -> dict:
        p = self.policy
        return {"name": p.get("name"), "securityMode": p.get("security_mode"), "defaultPolicy": p.get("default_policy"),
                "externalNetwork": p.get("external_network"), "externalLlm": p.get("external_llm"),
                "externalSearch": p.get("external_search"), "telemetryExternal": p.get("telemetry_external"),
                "allowedSources": p.get("allowed_sources", []), "auditLogging": p.get("audit_logging"),
                "networkGuard": network_guard_active(), "user": self.user,
                "authentication": "Lokaler Windows-Benutzer (Pilot ohne SSO/Entra ID)",
                "profile": self.profile(), "localFirstOrder": p.get("local_first_order", []),
                "registry": self.registry.get("name"), "registryVersion": self.registry.get("version")}

    # -- argument validation (schema) -------------------------------------------------------
    @staticmethod
    def validate_arguments(tool: dict, arguments) -> dict:
        spec = tool["parameters"]
        if not isinstance(arguments, dict):
            arguments = {}
        clean = {}
        for key, schema in spec.get("properties", {}).items():
            value = arguments.get(key)
            if value in (None, "", []):
                continue
            if schema.get("type") == "array":
                values = value if isinstance(value, list) else [value]
                enum = schema.get("items", {}).get("enum")
                picked = []
                for item in values:
                    match = next((e for e in enum if e.casefold() == str(item).casefold()), None) if enum else str(item)
                    if match and match not in picked:
                        picked.append(match)
                if picked:
                    clean[key] = picked
                continue
            value = str(value).strip()[:300]
            if "enum" in schema:
                value = next((e for e in schema["enum"] if e.casefold() == value.casefold()), "")
            if value:
                clean[key] = value
        missing = [k for k in spec.get("required", []) if k not in clean]
        if missing:
            raise PolicyError(f"Pflichtparameter fehlt: {', '.join(missing)}.", 400)
        return clean

    # -- the decision ---------------------------------------------------------------------
    def decide(self, tool_name: str, arguments, user: str | None = None) -> Decision:
        user = user or self.user
        tool = self.tool(tool_name)
        if tool is None:  # Gate 3: allowlist, default DENY
            return Decision(False, tool_name, reason=f"„{tool_name}“ steht nicht in der Tool Registry (default DENY).")
        sec = tool["security"]
        operation = sec["allowed_operations"][0]
        decision = Decision(False, tool_name, operation, sec["classification"])
        if sec.get("internet_access") or (sec["network"] not in ("LOCAL_ONLY", "INTERNAL_ONLY")):  # Gate 4
            decision.reason = "Tool verlangt Netzwerkzugriff außerhalb des internen Netzes."
            return decision
        if sec["source"] not in self.policy.get("allowed_sources", []):
            decision.reason = f"Quelle „{sec['source']}“ ist in der Policy nicht freigegeben."
            return decision
        if sec.get("authentication_required", True) and not user:  # Gate 1
            decision.reason = "Kein angemeldeter Benutzer."
            return decision
        profile = self.profile(user)  # Gate 2
        if not any(fnmatch.fnmatch(tool_name, pattern) for pattern in profile.get("tools", [])):
            decision.reason = f"Benutzer {user} ist für {tool_name} nicht berechtigt."
            return decision
        if operation not in profile.get("operations", []):
            decision.reason = f"Operation {operation} ist für {user} nicht freigegeben."
            return decision
        try:
            args = self.validate_arguments(tool, arguments)
        except PolicyError as exc:
            decision.reason = str(exc)
            return decision
        chapters = self.allowed_chapters(user)
        if chapters is not None and args.get("chapter") and args["chapter"] not in chapters:
            decision.reason = f"Kapitel {args['chapter']} ist für {user} nicht freigegeben."
            return decision
        decision.allowed = True
        decision.arguments = args
        decision.reason = "Allowlist, Berechtigung und Parameter geprüft."
        decision.confirmation_required = bool(sec.get("confirmation_required"))
        return decision

    # -- Gate 5: audit -----------------------------------------------------------------------
    def audit(self, decision: Decision, *, session: str = "", router: str = "", message: str = "", executed: bool = False,
              user: str | None = None):
        if not self.policy.get("audit_logging", True):
            return
        args = {k: (f"<{len(str(v))} Zeichen>" if k in FREE_TEXT else v) for k, v in (decision.arguments or {}).items()}
        entry = {"timestamp": now_iso(), "user": user or self.user, "session": (session or "")[:64], "tool": decision.tool,
                 "operation": decision.operation, "classification": decision.classification,
                 "result": "ALLOWED" if decision.allowed else "DENIED", "executed": executed, "reason": decision.reason,
                 "router": router, "arguments": args}
        if message:
            entry["messageSha256"] = hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]
            entry["messageLength"] = len(message)
            if self.policy.get("audit_include_prompt"):
                entry["message"] = message
        with LOCK:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def audit_entries(self, limit: int = 100) -> list[dict]:
        if not self.audit_path.exists():
            return []
        lines = self.audit_path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in reversed(lines):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
