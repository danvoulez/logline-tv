"""Domain adapter — reads ALL extraction config from the database.

There are no per-site classes. Every site (adult or not) is a row in
domain_policies and DBAdapter just reads it.

Operators add / edit / delete sites entirely through the admin UI.
"""

import re

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.models import DomainPolicy

logger = structlog.get_logger()


class DBAdapter:
    """A single adapter implementation, configured by a DomainPolicy row."""

    DEFAULT_RESULT_SELECTOR = "a[href]"
    DEFAULT_TITLE_SELECTOR = "h1, h2, .title"
    DEFAULT_LOGIN_EMAIL_SEL = (
        "input[type='email'], input[name='email'], "
        "input[name='username'], input[name='login']"
    )
    DEFAULT_LOGIN_PASS_SEL = "input[type='password']"
    DEFAULT_LOGIN_SUBMIT_SEL = (
        "button[type='submit'], input[type='submit'], "
        "button.login-btn, button.submit"
    )

    def __init__(self, policy: DomainPolicy) -> None:
        self.policy = policy

    # ── Domain ────────────────────────────────────────────────────────────────

    @property
    def domain(self) -> str:
        return self.policy.domain

    @property
    def session_profile_name(self) -> str:
        return (
            self.policy.session_profile_name
            or f"{self.policy.domain.replace('.', '_')}_session"
        )

    # ── Selectors (with sensible fallbacks) ───────────────────────────────────

    @property
    def result_selector(self) -> str:
        return self.policy.result_selector or self.DEFAULT_RESULT_SELECTOR

    @property
    def title_selector(self) -> str:
        return self.policy.title_selector or self.DEFAULT_TITLE_SELECTOR

    @property
    def LOGIN_URL(self) -> str | None:
        return self.policy.login_url

    @property
    def LOGIN_EMAIL_SEL(self) -> str:
        return self.policy.login_email_selector or self.DEFAULT_LOGIN_EMAIL_SEL

    @property
    def LOGIN_PASS_SEL(self) -> str:
        return self.policy.login_password_selector or self.DEFAULT_LOGIN_PASS_SEL

    @property
    def LOGIN_SUBMIT_SEL(self) -> str:
        return self.policy.login_submit_selector or self.DEFAULT_LOGIN_SUBMIT_SEL

    @property
    def LOGIN_SUCCESS_SEL(self) -> str | None:
        return self.policy.login_success_selector

    # ── URL templates ─────────────────────────────────────────────────────────

    def build_search_url(self, query: str) -> str | None:
        if not self.policy.search_url_template:
            return None
        try:
            return self.policy.search_url_template.format(
                domain=self.policy.domain,
                query=query.replace(" ", "+"),
                query_dashed=query.replace(" ", "-"),
                query_raw=query,
            )
        except (KeyError, IndexError) as e:
            logger.warning(
                "search_url_template_invalid",
                domain=self.policy.domain,
                template=self.policy.search_url_template,
                error=str(e),
            )
            return None

    def build_user_url(self, username: str) -> str | None:
        if not self.policy.user_url_template:
            return None
        try:
            return self.policy.user_url_template.format(
                domain=self.policy.domain,
                username=username,
            )
        except (KeyError, IndexError) as e:
            logger.warning(
                "user_url_template_invalid",
                domain=self.policy.domain,
                template=self.policy.user_url_template,
                error=str(e),
            )
            return None

    # ── Retrieval classification ──────────────────────────────────────────────

    def _extensions(self) -> list[str]:
        raw = self.policy.accepted_extensions
        if isinstance(raw, list):
            return [str(e).lower().lstrip(".") for e in raw]
        return ["mp4", "webm", "m3u8", "mpd"]

    def classify_retrieval(
        self, url: str | None, page_info: dict | None = None
    ) -> tuple[bool, str | None]:
        """Decide if a URL/page yields an authorized retrieval path."""
        info = page_info or {}

        if self.policy.needs_media_interception and info.get("intercepted_media"):
            return True, "official_download"

        if self.policy.requires_login and info.get("has_download_button"):
            return True, "official_download"

        if not url:
            return False, None

        url_lower = url.lower().split("?")[0]
        for ext in self._extensions():
            if url_lower.endswith(f".{ext}"):
                return True, "direct_url"

        return False, None

    # ── Title cleanup ─────────────────────────────────────────────────────────

    def clean_title(self, raw_title: str) -> str:
        title = raw_title or ""
        strips = self.policy.title_suffix_strips
        if isinstance(strips, list):
            for suffix in strips:
                if not isinstance(suffix, str):
                    continue
                pattern = re.compile(re.escape(suffix) + r"\s*$", re.IGNORECASE)
                title = pattern.sub("", title)
        return title.strip()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def parse_duration(self, text: str) -> int | None:
        if not text:
            return None
        m = re.match(r"(\d+):(\d+):(\d+)", text)
        if m:
            return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
        m = re.match(r"(\d+):(\d+)", text)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2))
        m = re.match(r"(\d+)\s*s", text)
        if m:
            return int(m.group(1))
        try:
            return int(float(text))
        except (ValueError, TypeError):
            return None


async def get_adapter_for_domain(
    db: AsyncSession, domain: str
) -> DBAdapter | None:
    """Load the adapter for a domain. Returns None if not registered."""
    if not domain:
        return None
    result = await db.execute(
        select(DomainPolicy).where(DomainPolicy.domain == domain)
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        return None
    return DBAdapter(policy)
