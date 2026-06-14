"""URL Safety Checker — additional URL-level safety validation beyond ComplianceFilter."""
import re
from urllib.parse import urlparse


class UrlSafetyChecker:
    """Extra safety checks on URLs before they enter the candidate pipeline.

    Complements ComplianceFilter with URL-structure-specific checks.
    """

    # Dangerous URL patterns (never collect)
    DANGEROUS_PATTERNS = [
        (r"\.exe$", "executable file"),
        (r"\.dmg$", "macOS disk image"),
        (r"\.pkg$", "installer package"),
        (r"\.msi$", "Windows installer"),
        (r"\.apk$", "Android APK"),
        (r"\.ipa$", "iOS IPA"),
        (r"\.scr$", "Windows screensaver"),
        (r"\.bat$", "batch script"),
        (r"\.sh$", "shell script"),
        (r"\.ps1$", "PowerShell script"),
        (r"\.vbs$", "VBScript"),
        (r"\.jar$", "Java archive"),
    ]

    # Suspicious patterns (warn, block unless user explicitly allows)
    SUSPICIOUS_PATTERNS = [
        (r"\.php\?", "PHP script with query"),
        (r"/cgi-bin/", "CGI script"),
        (r"eval\(", "eval pattern in URL"),
        (r"<script", "script tag in URL"),
        (r"javascript:", "javascript protocol"),
        (r"data:", "data URI"),
    ]

    # Non-public URL patterns
    NON_PUBLIC_PATTERNS = [
        (r"^https?://localhost", "localhost"),
        (r"^https?://127\.0\.0\.\d+", "loopback IP"),
        (r"^https?://10\.\d+\.\d+\.\d+", "private network (10.x)"),
        (r"^https?://172\.(1[6-9]|2\d|3[01])\.\d+\.\d+", "private network (172.16-31)"),
        (r"^https?://192\.168\.\d+\.\d+", "private network (192.168.x)"),
    ]

    def check(self, url: str) -> tuple:
        """Check URL safety. Returns (safe: bool, reason: str)."""
        if not url or not url.startswith(("http://", "https://")):
            return (False, "invalid URL protocol")

        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        # Non-public networks
        for pattern, reason in self.NON_PUBLIC_PATTERNS:
            if re.match(pattern, url, re.IGNORECASE):
                return (False, f"non-public address: {reason}")

        # Dangerous file types
        for pattern, reason in self.DANGEROUS_PATTERNS:
            if re.search(pattern, hostname + parsed.path, re.IGNORECASE):
                return (False, f"dangerous file type: {reason}")

        # Suspicious patterns
        for pattern, reason in self.SUSPICIOUS_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                return (False, f"suspicious pattern: {reason}")

        return (True, "")

    def filter_safe(self, urls: list) -> list:
        """Filter list, return only safe URLs with (url, reason) tuples for unsafe ones."""
        safe = []
        unsafe_reasons = []
        for url in urls:
            ok, reason = self.check(url)
            if ok:
                safe.append(url)
            else:
                unsafe_reasons.append((url, reason))
        return safe, unsafe_reasons
