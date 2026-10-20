import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Dict, List, Optional


class LLMGateway:
    """Lightweight Multi-LLM router with automatic provider failover and zero-config graceful fallback."""

    def __init__(self, env_path: Optional[Path] = None, llm_config: Optional[Dict[str, Any]] = None):
        self._load_env(env_path)
        cfg = llm_config or {}
        self.enabled: bool = bool(cfg.get("enabled", True))
        self.failover_chain: List[str] = list(cfg.get("failover_chain", ["gemini", "openai", "anthropic"]))
        roles = cfg.get("roles", {}) if isinstance(cfg.get("roles"), dict) else {}
        self.gemini_model: str = str(cfg.get("gemini_model") or roles.get("explorer") or "gemini-2.5-flash")
        self.openai_model: str = str(cfg.get("openai_model") or "gpt-4o-mini")
        self.anthropic_model: str = str(cfg.get("anthropic_model") or roles.get("fixer") or "claude-3-7-sonnet-20250219")

        self.gemini_key = os.getenv("GEMINI_API_KEY")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = os.getenv("OPENAI_API_KEY")
        self.openai_base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def _load_env(self, env_path: Optional[Path]) -> None:
        target = env_path or (Path(__file__).resolve().parent.parent / ".env")
        if target.exists():
            for line in target.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

    @property
    def has_any_provider(self) -> bool:
        return self.enabled and bool(self.gemini_key or self.anthropic_key or self.openai_key)

    def generate(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """Tries configured providers in priority chain; returns None if offline or all fail."""
        if not self.enabled:
            return None

        for provider in self.failover_chain:
            p = provider.lower()
            if p == "gemini" and self.gemini_key:
                res = self._call_gemini(prompt, system_prompt)
                if res:
                    return res
            elif p == "openai" and self.openai_key:
                res = self._call_openai(prompt, system_prompt)
                if res:
                    return res
            elif p == "anthropic" and self.anthropic_key:
                res = self._call_anthropic(prompt, system_prompt)
                if res:
                    return res

        return None

    def _call_gemini(self, prompt: str, system_prompt: str) -> Optional[str]:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            if system_prompt:
                payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception:
            return None

    def _call_openai(self, prompt: str, system_prompt: str) -> Optional[str]:
        try:
            url = f"{self.openai_base_url}/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.openai_model,
                "messages": messages,
                "temperature": 0.2
            }
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.openai_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except Exception:
            return None

    def _call_anthropic(self, prompt: str, system_prompt: str) -> Optional[str]:
        try:
            url = "https://api.anthropic.com/v1/messages"
            payload = {
                "model": self.anthropic_model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]
            }
            if system_prompt:
                payload["system"] = system_prompt

            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["content"][0]["text"]
        except Exception:
            return None
