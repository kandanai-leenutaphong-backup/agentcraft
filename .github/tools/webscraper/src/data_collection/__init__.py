"""HTTP-first, browser-assisted public HTML acquisition."""

from .models import BrowserAction, ScrapeOptions, ScrapeResult
from .scraper import Scraper

__all__ = ["BrowserAction", "ScrapeOptions", "ScrapeResult", "Scraper"]