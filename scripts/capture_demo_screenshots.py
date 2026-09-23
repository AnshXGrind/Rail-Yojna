#!/usr/bin/env python3
"""
Capture presentation screenshots from a locally running Rail-Yojna stack.

Requirements:
  python -m pip install playwright
  python -m playwright install chromium

Run with:
  python scripts/capture_demo_screenshots.py

The script expects:
  backend:  http://127.0.0.1:8000
  frontend: http://127.0.0.1:5173

Screenshots are written to docs/assets/demo/.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "assets" / "demo"
BASE = "http://127.0.0.1:5173"


async def open_page(page, path: str, ready_selector: str) -> None:
    await page.goto(
        f"{BASE}/#{path}",
        wait_until="domcontentloaded",
    )
    await page.wait_for_selector(
        ready_selector,
        state="visible",
        timeout=30_000,
    )


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(
            viewport={"width": 1600, "height": 1000},
            device_scale_factor=1,
        )

        await open_page(page, "/control", ".dashboard")
        await page.screenshot(
            path=str(OUT / "control-room.png"),
            full_page=True,
        )

        await page.get_by_role(
            "button",
            name="Block Planning",
        ).click()

        await page.get_by_text(
            "Block Planning Center",
            exact=True,
        ).wait_for(state="visible", timeout=10_000)

        await page.screenshot(
            path=str(OUT / "block-planning.png"),
            full_page=True,
        )

        await open_page(page, "/reports", ".module-page")
        await page.screenshot(
            path=str(OUT / "reports.png"),
            full_page=True,
        )

        await open_page(page, "/service", ".module-page")
        await page.screenshot(
            path=str(OUT / "service.png"),
            full_page=True,
        )

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
