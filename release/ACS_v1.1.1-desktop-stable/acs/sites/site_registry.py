"""Multi-site registry with data isolation."""
import os, json, threading
from typing import Dict, List, Optional
from acs.sites.site_config import SiteConfig, DEFAULT_SITES

class SiteRegistry:
    def __init__(self, config_path: str = "acs_data/sites.json"):
        self.config_path = config_path
        self._lock = threading.Lock()
        self._sites: Dict[str, SiteConfig] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    data = json.load(f)
                for item in data:
                    cfg = SiteConfig.from_dict(item)
                    if cfg.site_id:
                        self._sites[cfg.site_id] = cfg
            except: pass
        if not self._sites:
            for cfg in DEFAULT_SITES:
                self._sites[cfg.site_id] = cfg

    def _save(self):
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self._sites.values()], f, ensure_ascii=False, indent=2)

    def list_enabled(self) -> List[SiteConfig]:
        return [s for s in self._sites.values() if s.enabled]

    def list_all(self) -> List[SiteConfig]:
        return list(self._sites.values())

    def get(self, site_id: str) -> Optional[SiteConfig]:
        return self._sites.get(site_id)

    def add(self, cfg: SiteConfig) -> bool:
        errs = cfg.validate()
        if errs: return False
        with self._lock:
            self._sites[cfg.site_id] = cfg
            self._save()
        return True

    def remove(self, site_id: str) -> bool:
        with self._lock:
            if site_id in self._sites:
                del self._sites[site_id]
                self._save()
                return True
        return False

    def set_enabled(self, site_id: str, enabled: bool) -> bool:
        s = self._sites.get(site_id)
        if s:
            s.enabled = enabled
            self._save()
            return True
        return False

    def stats(self) -> dict:
        total = len(self._sites)
        enabled = len(self.list_enabled())
        return {"total_sites": total, "enabled_sites": enabled}
