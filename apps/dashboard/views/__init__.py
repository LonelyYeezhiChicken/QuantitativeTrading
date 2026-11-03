"""Dashboard views module for decoupled tab rendering."""

from apps.dashboard.views.overview_tab import render_overview_tab
from apps.dashboard.views.journal_tab import render_journal_tab
from apps.dashboard.views.trading_tab import render_trading_tab
from apps.dashboard.views.research_tab import render_research_tab

__all__ = [
    "render_overview_tab",
    "render_journal_tab",
    "render_trading_tab",
    "render_research_tab",
]
