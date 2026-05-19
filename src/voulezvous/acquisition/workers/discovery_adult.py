"""User-profile (creator) discovery worker.

Scrapes a creator's profile on any cadastered domain and registers new candidates.
Works for any site cadastered in domain_policies — adult or not.

No hardcoded site names: the function takes a `domain` and pulls everything
(URLs, selectors, credentials) from the DB row.
"""

import asyncio
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from voulezvous.acquisition.browser.adapters import get_adapter_for_domain
from voulezvous.acquisition.browser.runtime import BrowserRuntime
from voulezvous.acquisition.enums import (
    CandidateRightsStatus,
    DiscoveryStatus,
    RetrievalStatus,
)
from voulezvous.acquisition.models import CandidateAsset, DiscoveryRun, DomainPolicy

logger = structlog.get_logger()


async def run_user_discovery(
    db: AsyncSession,
    domain: str,
    username: str,
    max_videos: int = 20,
    run_date: date | None = None,
) -> DiscoveryRun:
    """Scrape a creator's profile on the given domain and register candidates."""
    run_date = run_date or date.today()

    adapter = await get_adapter_for_domain(db, domain)
    if adapter is None:
        raise ValueError(f"Domain {domain} is not registered in domain_policies")

    policy: DomainPolicy = adapter.policy

    if not policy.is_enabled:
        raise ValueError(f"Domain {domain} is disabled")

    profile_url = adapter.build_user_url(username)
    if not profile_url:
        raise ValueError(f"Domain {domain} has no user_url_template configured")

    candidates_found = 0
    candidates_added = 0
    errors: list[str] = []

    runtime = BrowserRuntime()
    try:
        await runtime.launch(profile_name=adapter.session_profile_name)

        # Login if the domain requires it and credentials are configured
        if policy.requires_login and policy.credential_email and policy.credential_password:
            if not adapter.LOGIN_URL:
                logger.warning("login_skipped_no_url", domain=domain)
            else:
                login_result = await runtime.login(
                    login_url=adapter.LOGIN_URL,
                    email=policy.credential_email,
                    password=policy.credential_password,
                    email_selector=adapter.LOGIN_EMAIL_SEL,
                    pass_selector=adapter.LOGIN_PASS_SEL,
                    submit_selector=adapter.LOGIN_SUBMIT_SEL,
                    success_check=adapter.LOGIN_SUCCESS_SEL,
                )
                if not login_result.get("success") and not login_result.get(
                    "already_logged_in"
                ):
                    logger.warning(
                        "user_login_failed",
                        domain=domain,
                        error=login_result.get("error"),
                    )

        logger.info("user_discovery_start", domain=domain, user=username, url=profile_url)
        await runtime.navigate(profile_url)
        await asyncio.sleep(3)

        links = await runtime.extract_links(
            selector=adapter.result_selector, max_results=max_videos
        )

        if not links:
            links = await runtime.extract_links(
                selector="a[href*='/video'], a[href*='/watch'], a[href*='/v/']",
                max_results=max_videos,
            )

        logger.info("user_discovery_links", domain=domain, count=len(links))

        for link in links[:max_videos]:
            href = link.get("href", "")
            link_text = link.get("text", "") or link.get("title", "") or domain

            if not href or len(href) < 10:
                continue

            skip_patterns = [
                "/search", "/tag", "/category", "/channel", "/profile",
                "/login", "/register", "/premium", "/upload",
            ]
            if any(p in href.lower() for p in skip_patterns):
                continue

            candidates_found += 1

            await runtime.navigate(href)
            await asyncio.sleep(2)

            media_info = await runtime.extract_media_info()
            duration_sec = None
            if media_info.get("og_duration"):
                try:
                    duration_sec = int(media_info["og_duration"])
                except ValueError:
                    pass
            if not duration_sec and media_info.get("videos"):
                for v in media_info["videos"]:
                    if v.get("duration"):
                        try:
                            duration_sec = int(float(v["duration"]))
                            break
                        except (ValueError, TypeError):
                            pass

            page_title = media_info.get("title") or link_text
            page_title = adapter.clean_title(page_title)

            intercepted: list = []
            download_url: str | None = None
            if policy.needs_media_interception:
                intercepted = await runtime.intercept_media_requests()
                if intercepted:
                    mp4s = [u for u in intercepted if u.endswith(".mp4")]
                    download_url = mp4s[0] if mp4s else intercepted[0]

            if not download_url:
                download_url = await runtime.click_download_button()

            page_info = {
                "has_download_button": bool(download_url),
                "intercepted_media": bool(intercepted),
            }
            authorized, retrieval_type = adapter.classify_retrieval(download_url, page_info)

            tags = [domain, username]
            if policy.is_adult:
                tags.append("adult")

            candidate = CandidateAsset(
                domain_policy_id=policy.id,
                title=page_title[:500] if page_title else f"{domain} — {username}",
                source_url=download_url or href,
                page_url=href,
                duration_sec=duration_sec,
                retrieval_status=(
                    RetrievalStatus.authorized_direct
                    if authorized
                    else RetrievalStatus.metadata_only
                ),
                rights_status=CandidateRightsStatus.pending_review,
                discovery_status=DiscoveryStatus.found,
                tags=tags,
                extra_metadata={
                    "domain": domain,
                    "creator": username,
                    "download_url": download_url,
                    "retrieval_type": retrieval_type,
                    "intercepted_urls": intercepted[:5] if intercepted else [],
                    "og_description": media_info.get("meta_description", "")[:500],
                },
            )
            db.add(candidate)
            candidates_added += 1
            logger.info(
                "user_candidate_added",
                domain=domain,
                title=page_title[:60],
                duration=duration_sec,
                authorized=authorized,
            )

        await db.commit()

    except Exception as e:
        logger.error("user_discovery_error", domain=domain, error=str(e))
        errors.append(str(e))
    finally:
        await runtime.close()

    discovery_run = DiscoveryRun(
        run_date=run_date,
        status="completed" if not errors else "partial",
        output_summary={
            "domain": domain,
            "creator": username,
            "total_found": candidates_found,
            "total_added": candidates_added,
            "errors": errors,
        },
    )
    db.add(discovery_run)
    await db.commit()

    logger.info(
        "user_discovery_complete",
        domain=domain,
        user=username,
        found=candidates_found,
        added=candidates_added,
    )
    return discovery_run
