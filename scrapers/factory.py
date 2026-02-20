"""
Scraper Factory.
Routes each company to the correct ATS scraper based on its platform.
Manages scraper lifecycle and provides a single interface for the orchestrator.
"""

import logging
from typing import Optional

from config.settings import ScraperConfig
from config.company_registry import Company, ATSPlatform
from scrapers.base import BaseScraper, NormalizedJob
from scrapers.ats.greenhouse import GreenhouseScraper
from scrapers.ats.lever import LeverScraper
from scrapers.ats.ashby import AshbyScraper
from scrapers.ats.smartrecruiters import SmartRecruitersScraper
from scrapers.ats.workday import WorkdayScraper
from scrapers.ats.custom import CustomScraper

logger = logging.getLogger(__name__)


class ScraperFactory:
    """
    Creates and caches scraper instances by ATS platform.
    Single entry point: `scrape(company) -> list[NormalizedJob]`
    """

    def __init__(self, config: ScraperConfig):
        self.config = config
        self._scrapers: dict[ATSPlatform, BaseScraper] = {}

    def _get_scraper(self, ats: ATSPlatform) -> Optional[BaseScraper]:
        """Lazy-instantiate and cache scrapers."""
        if ats not in self._scrapers:
            cls_map = {
                ATSPlatform.GREENHOUSE: GreenhouseScraper,
                ATSPlatform.LEVER: LeverScraper,
                ATSPlatform.ASHBY: AshbyScraper,
                ATSPlatform.SMARTRECRUITERS: SmartRecruitersScraper,
                ATSPlatform.WORKDAY: WorkdayScraper,
                ATSPlatform.CUSTOM: CustomScraper,
            }
            cls = cls_map.get(ats)
            if cls:
                self._scrapers[ats] = cls(self.config)
            else:
                logger.warning("No scraper implementation for ATS: %s", ats)
                return None

        return self._scrapers[ats]

    async def scrape(self, company: Company) -> list[NormalizedJob]:
        """Scrape a single company using the appropriate ATS scraper."""
        scraper = self._get_scraper(company.ats)
        if not scraper:
            return []

        return await scraper.scrape_company(company)

    async def close_all(self) -> None:
        """Close all scraper HTTP clients."""
        for scraper in self._scrapers.values():
            await scraper.close()
        self._scrapers.clear()
