import os
import time
from datetime import date
from typing import Optional

import requests

from norman.events import TournamentEvent
from norman.models import (
    AnalystOutput,
    AnalystLead,
    DeliveryStatus,
    SynthesisOutput,
    ThemeOutput,
)
from norman.config import DISCORD_WEBHOOK_URL, USE_PER_LEAD_ADS
from norman.token_tracker import token_tracker

DISCORD_CHAR_LIMIT = 2000
DISCORD_RATE_LIMIT_DELAY = 1.5  # seconds between webhook calls
DISCORD_DEFAULT_RETRY_AFTER = 5.0  # fallback when Retry-After header missing

SEGMENT_ICONS = {
    "fishing": "🎣",
    "golf": "⛳",
    "motorcycle": "🏍️",
    "commuter": "🚗",
    "general": "🌐",
}
SEGMENT_ORDER = ["fishing", "golf", "motorcycle", "commuter", "general"]


def _count_event_leads(output: AnalystOutput) -> int:
    """Count distinct event-flagged leads across all segment buckets."""
    seen: set[str] = set()
    count = 0
    for seg_leads in output.segments.values():
        for lead in seg_leads:
            if lead.url in seen:
                continue
            seen.add(lead.url)
            if lead.event_window:
                count += 1
    return count


def _event_window_block(
    active_event: Optional[TournamentEvent], n_event_leads: int
) -> str:
    """Render the event-window banner. Empty string when no event is active."""
    if not active_event:
        return ""
    return (
        f"🏌️ **Event Window: {active_event.name}** "
        f"({active_event.start_date.strftime('%m-%d')}–"
        f"{active_event.end_date.strftime('%m-%d')} ± buffer)\n"
        f"_{n_event_leads} event-flagged leads in today's run._\n"
    )


def run_delivery(
    analyst_output: AnalystOutput,
    run_log: str = "",
    klaviyo_configured: bool = False,
    dashboard_configured: bool = False,
    active_event: Optional[TournamentEvent] = None,
) -> DeliveryStatus:
    """Deliver analyst results to all configured channels.

    Branches on USE_PER_LEAD_ADS: when off (default), emits a condensed
    daily summary (run log + top 10 leads, no ad copy); when on, emits the
    full per-lead ad intelligence report.
    """
    status = DeliveryStatus()

    if USE_PER_LEAD_ADS:
        status.markdown = _write_markdown_report(analyst_output, active_event)
        status.discord = _post_discord(analyst_output, run_log, active_event)
    else:
        status.markdown = _write_markdown_condensed(analyst_output, active_event)
        status.discord = _post_discord_condensed(analyst_output, run_log, active_event)

    status.klaviyo = (
        "⚠️ Klaviyo integration not yet implemented"
        if klaviyo_configured
        else "⚠️ not configured"
    )
    status.dashboard = (
        "⚠️ Dashboard integration not yet implemented"
        if dashboard_configured
        else "⚠️ not configured"
    )

    return status


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

def _post_discord(
    output: AnalystOutput,
    run_log: str,
    active_event: Optional[TournamentEvent] = None,
) -> str:
    if not DISCORD_WEBHOOK_URL:
        return "⚠️ not configured (no DISCORD_WEBHOOK_URL)"

    errors = []
    stats = {"posted": 0, "retried": 0, "dropped": 0}

    if output.total_leads == 0:
        # Single combined message when there's nothing to report
        sources_ran = _sources_ran(output)
        event_block = _event_window_block(active_event, 0)
        msg = (
            f"📡 **Norman Daily Run — {output.date}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{event_block}"
            f"No new leads found today. All discovered URLs were previously visited "
            f"or scored below threshold.\n"
            f"Scouts ran: {sources_ran}\n"
        )
        if run_log:
            msg += f"\n```{run_log}```"
        err = _send_webhook(msg, stats)
        if err:
            errors.append(err)
    else:
        # Message 1 — Pipeline Run Log
        err = _post_run_log(output, run_log, stats, active_event)
        if err:
            errors.append(f"Run log: {err}")

        # Message 2+ — Lead Intelligence Report (chunked by segment)
        report_errors = _post_lead_report(output, stats)
        errors.extend(report_errors)

    total = stats["posted"] + stats["retried"] + stats["dropped"]
    summary = (
        f"posted {stats['posted']}/{total} messages, "
        f"{stats['retried']} retried, {stats['dropped']} dropped"
    )
    if errors:
        return f"⚠️ Discord partial ({summary}): {'; '.join(errors)}"
    return f"✅ Discord: {summary}"


def _post_run_log(
    output: AnalystOutput,
    run_log: str,
    stats: dict,
    active_event: Optional[TournamentEvent] = None,
) -> str | None:
    """Post Message 1: the pipeline run log block."""
    sources = sorted(_collect_sources(output))
    seg_counts = {seg: len(leads) for seg, leads in output.segments.items() if leads}
    seg_summary = " | ".join(
        f"{SEGMENT_ICONS.get(seg, '')} {seg.title()} ({n})"
        for seg, n in seg_counts.items()
    )

    top_lines = []
    for i, lead in enumerate(output.top_3, 1):
        badge = "🏆 " if lead.event_window else ""
        top_lines.append(
            f"{i}. {badge}**[{lead.title[:80]}]({lead.url})**\n"
            f"   Score: {lead.score}/100 | {lead.segment} | {lead.source}\n"
            f"   > {lead.problem_detected}\n"
            f"   > 📣 _{lead.ad_headline}_"
        )

    event_block = _event_window_block(active_event, _count_event_leads(output))
    msg = (
        f"📡 **Norman Daily Run — {output.date}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{event_block}"
        f"Total leads: **{output.total_leads}** across {', '.join(sources)}\n\n"
        f"🏆 **Top Leads Today:**\n\n"
        + "\n\n".join(top_lines)
        + f"\n\n📊 By Segment: {seg_summary}\n"
    )

    usage_block = _format_token_usage(output.date)
    if usage_block:
        msg += f"\n{usage_block}"

    if run_log:
        log_block = f"\n```{run_log}```"
        # Only append if it fits within the limit
        if len(msg) + len(log_block) <= DISCORD_CHAR_LIMIT:
            msg += log_block

    return _send_webhook(msg[:DISCORD_CHAR_LIMIT], stats)


def _post_lead_report(output: AnalystOutput, stats: dict) -> list[str]:
    """Post Message 2+: full ad copy report, chunked at segment boundaries."""
    errors = []
    header = f"📊 **Norman Lead Intelligence — {output.date}**\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Build per-segment blocks, then chunk them into ≤2000-char messages
    chunks: list[str] = []
    current = header

    for seg_name in SEGMENT_ORDER:
        seg_leads = output.segments.get(seg_name, [])
        if not seg_leads:
            continue

        icon = SEGMENT_ICONS.get(seg_name, "📋")
        seg_block = f"{icon} **{seg_name.upper()} — {len(seg_leads)} lead{'s' if len(seg_leads) != 1 else ''}**\n\n"

        for lead in seg_leads:
            seg_block += _format_lead_block(lead)

        # If adding this segment would overflow, flush current chunk first
        if len(current) + len(seg_block) > DISCORD_CHAR_LIMIT:
            if current.strip():
                chunks.append(current)
            # If one segment is itself too long, split it lead-by-lead
            if len(seg_block) > DISCORD_CHAR_LIMIT:
                current = f"{icon} **{seg_name.upper()} (continued)**\n\n"
                for lead in seg_leads:
                    lead_block = _format_lead_block(lead)
                    if len(current) + len(lead_block) > DISCORD_CHAR_LIMIT:
                        chunks.append(current)
                        current = f"{icon} **{seg_name.upper()} (continued)**\n\n"
                    current += lead_block
            else:
                current = seg_block
        else:
            current += seg_block

    if current.strip():
        chunks.append(current)

    for chunk in chunks:
        err = _send_webhook(chunk[:DISCORD_CHAR_LIMIT], stats)
        if err:
            errors.append(err)

    return errors


def _format_lead_block(lead: AnalystLead) -> str:
    """Format one lead's ad intelligence as a Discord-friendly block."""
    lines = [
        f"**[{lead.title[:80]}]({lead.url})**",
        f"_{lead.source.upper()} | Score {lead.score}/100_",
        f"> **Problem:** {lead.problem_detected}",
        f"> **Why We Win:** {lead.why_we_win}",
        f"> **Ad:** {lead.ad_headline}",
        f"> {lead.ad_body}",
        f"> 📍 _{lead.placement_tip}_",
        "─────────────────────\n",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Condensed daily summary (USE_PER_LEAD_ADS=0)
# ---------------------------------------------------------------------------

def _post_discord_condensed(
    output: AnalystOutput,
    run_log: str,
    active_event: Optional[TournamentEvent] = None,
) -> str:
    """Discord delivery when per-lead ad generation is off. Posts the run
    log plus the top 10 leads by score, no ad copy, no per-segment blocks.
    """
    if not DISCORD_WEBHOOK_URL:
        return "⚠️ not configured (no DISCORD_WEBHOOK_URL)"

    stats = {"posted": 0, "retried": 0, "dropped": 0}
    errors: list[str] = []

    sources = sorted(_collect_sources(output))
    top_10 = _top_n_by_score(output, 10)

    event_block = _event_window_block(active_event, _count_event_leads(output))
    header = (
        f"📡 **Norman Daily Run — {output.date}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{event_block}"
        f"Customer-voice leads: **{output.total_leads}** across "
        f"{', '.join(sources) if sources else 'no sources'}\n"
        f"_Daily signal only; creative themes posted every Monday._\n"
    )
    if run_log:
        header += f"\n```{run_log}```\n"

    top_header = "\n🏆 **Top 10 Leads by Score**\n\n" if top_10 else ""
    top_lines: list[str] = []
    for i, lead in enumerate(top_10, 1):
        badge = "🏆 " if lead.event_window else ""
        top_lines.append(
            f"{i}. {badge}**[{lead.title[:80]}]({lead.url})**\n"
            f"   Score {lead.score} | {lead.source_type} | {lead.segment}"
        )

    # Assemble into chunks that respect the 2000-char Discord limit.
    chunks: list[str] = []
    current = header + top_header
    for line in top_lines:
        candidate = current + line + "\n"
        if len(candidate) > DISCORD_CHAR_LIMIT:
            if current.strip():
                chunks.append(current)
            current = top_header + line + "\n"
        else:
            current = candidate
    if current.strip():
        chunks.append(current)

    # Append token-usage footer as its own trailing message if present.
    usage_block = _format_token_usage(output.date)
    if usage_block:
        chunks.append(usage_block)

    for chunk in chunks:
        err = _send_webhook(chunk[:DISCORD_CHAR_LIMIT], stats)
        if err:
            errors.append(err)

    total = stats["posted"] + stats["retried"] + stats["dropped"]
    summary = (
        f"posted {stats['posted']}/{total} messages, "
        f"{stats['retried']} retried, {stats['dropped']} dropped"
    )
    if errors:
        return f"⚠️ Discord partial ({summary}): {'; '.join(errors)}"
    return f"✅ Discord: {summary}"


def _write_markdown_condensed(
    output: AnalystOutput,
    active_event: Optional[TournamentEvent] = None,
) -> str:
    """Markdown report when per-lead ad generation is off. Mirrors the
    condensed Discord post: header, top 10 leads, token usage."""
    os.makedirs("reports", exist_ok=True)
    filename = f"reports/{output.date}.md"
    sources = _collect_sources(output)

    try:
        with open(filename, "w") as f:
            f.write(f"# Norman Ad Scout Report — {output.date}\n\n")
            event_block = _event_window_block(
                active_event, _count_event_leads(output)
            )
            if event_block:
                f.write(event_block + "\n")
            f.write(
                "**Mode:** USE_PER_LEAD_ADS=0 "
                "(per-lead ad generation disabled; weekly synthesis runs Monday)\n\n"
            )
            f.write(f"**Customer-voice leads:** {output.total_leads}\n")
            f.write(
                f"**Sources:** {', '.join(sorted(sources)) if sources else 'none'}\n\n---\n\n"
            )

            f.write("## Top 10 Leads by Score\n\n")
            top_10 = _top_n_by_score(output, 10)
            if not top_10:
                f.write("No qualifying leads this run.\n\n")
            for i, lead in enumerate(top_10, 1):
                badge = "🏆 " if lead.event_window else ""
                f.write(f"{i}. {badge}**[{lead.title}]({lead.url})**\n")
                f.write(f"   - Score: {lead.score}/100\n")
                f.write(f"   - Source type: {lead.source_type}\n")
                f.write(f"   - Segment: {lead.segment}\n\n")

            usage_block = _format_token_usage(output.date)
            if usage_block:
                f.write(usage_block)

        return f"✅ written to {filename}"
    except Exception as e:
        return f"❌ markdown write failed: {e}"


def _top_n_by_score(output: AnalystOutput, n: int) -> list[AnalystLead]:
    """Flatten segments, dedupe by URL, return the top-N AnalystLeads by score."""
    all_leads = sorted(
        (l for seg_leads in output.segments.values() for l in seg_leads),
        key=lambda l: l.score,
        reverse=True,
    )
    seen: set[str] = set()
    picked: list[AnalystLead] = []
    for l in all_leads:
        if l.url in seen:
            continue
        seen.add(l.url)
        picked.append(l)
        if len(picked) == n:
            break
    return picked


# ---------------------------------------------------------------------------
# Weekly synthesis delivery
# ---------------------------------------------------------------------------

def deliver_synthesis(synthesis_output: Optional[SynthesisOutput]) -> DeliveryStatus:
    """Deliver a weekly SynthesisOutput to markdown + Discord.

    Accepts None — when the synthesizer returns None (insufficient data or
    parse failure), we post a single short skip notice to Discord and mark
    the markdown field accordingly.
    """
    status = DeliveryStatus()

    if synthesis_output is None:
        status.synthesis_markdown = "⏸️  skipped (synthesizer returned None)"
        status.synthesis_discord = _post_synthesis_skip_notice()
        return status

    status.synthesis_markdown = _write_synthesis_markdown(synthesis_output)
    status.synthesis_discord = _post_synthesis_discord(synthesis_output)
    return status


def _post_synthesis_skip_notice() -> str:
    if not DISCORD_WEBHOOK_URL:
        return "⚠️ not configured (no DISCORD_WEBHOOK_URL)"
    stats = {"posted": 0, "retried": 0, "dropped": 0}
    msg = (
        "📊 Norman Synthesis skipped — insufficient customer-voice data "
        "in past 7 days. Next check: next Monday."
    )
    err = _send_webhook(msg, stats)
    if err:
        return f"⚠️ Discord drop: {err}"
    return "✅ Discord: posted skip notice"


def _write_synthesis_markdown(output: SynthesisOutput) -> str:
    os.makedirs("reports/synthesis", exist_ok=True)
    filename = f"reports/synthesis/{output.week_of}.md"
    today = date.today().isoformat()

    try:
        with open(filename, "w") as f:
            f.write(f"# Norman Weekly Synthesis — Week ending {today}\n\n")
            if output.events_in_window:
                f.write(
                    f"_Tournament context: "
                    f"{', '.join(output.events_in_window)}_\n\n"
                )

            f.write("## Summary\n\n")
            f.write(f"{output.summary}\n\n")
            f.write(f"Total customer_voice leads analyzed: {output.leads_analyzed}\n\n")
            if output.sampled_note:
                f.write(f"_{output.sampled_note}_\n\n")

            f.write("## Themes\n\n")
            for i, theme in enumerate(output.themes, 1):
                f.write(
                    f"### Theme {i} — {theme.name} "
                    f"(urgency: {theme.urgency_score}/10)\n\n"
                )
                f.write(f"**Pain point:** {theme.pain_point}\n\n")
                f.write(
                    f"**Segment breakdown:** {_format_breakdown(theme.segment_breakdown)}\n\n"
                )

                if theme.representative_quotes:
                    f.write("**Representative quotes:**\n\n")
                    last = len(theme.representative_quotes) - 1
                    for idx, q in enumerate(theme.representative_quotes):
                        if q.quote:
                            f.write(
                                f'> "{q.quote}" — [{q.segment}]({q.source_url})\n'
                            )
                        else:
                            f.write(f"> [{q.segment}]({q.source_url})\n")
                        f.write(f"> *Summary: {q.summary}*\n")
                        if idx != last:
                            f.write(">\n")
                    f.write("\n")

                if theme.creative_angles:
                    f.write("**Creative angles:**\n\n")
                    for j, angle in enumerate(theme.creative_angles, 1):
                        f.write(f"{j}. **{angle.angle}**\n")
                        f.write(f"   Hook: {angle.hook}\n")
                        f.write(f"   Proof: {angle.proof_point}\n\n")

            usage_block = _format_token_usage(today)
            if usage_block:
                f.write(usage_block)

        return f"✅ written to {filename}"
    except Exception as e:
        return f"❌ synthesis markdown write failed: {e}"


def _post_synthesis_discord(output: SynthesisOutput) -> str:
    """Post synthesis to Discord. One intro message + one message per theme,
    each chunked to the 2000-char limit."""
    if not DISCORD_WEBHOOK_URL:
        return "⚠️ not configured (no DISCORD_WEBHOOK_URL)"

    stats = {"posted": 0, "retried": 0, "dropped": 0}
    errors: list[str] = []
    today = date.today().isoformat()

    intro = (
        f"📊 **Norman Synthesis — Week ending {today}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{output.summary}\n"
        f"Leads analyzed: **{output.leads_analyzed}**"
    )
    if output.sampled_note:
        intro += f"\n_{output.sampled_note}_"

    err = _send_webhook(intro[:DISCORD_CHAR_LIMIT], stats)
    if err:
        errors.append(f"intro: {err}")

    for theme in output.themes:
        msg = _format_theme_for_discord(theme, today)
        err = _send_webhook(msg[:DISCORD_CHAR_LIMIT], stats)
        if err:
            errors.append(f"{theme.name}: {err}")

    total = stats["posted"] + stats["retried"] + stats["dropped"]
    summary = (
        f"posted {stats['posted']}/{total} messages, "
        f"{stats['retried']} retried, {stats['dropped']} dropped"
    )
    if errors:
        return f"⚠️ Discord partial ({summary}): {'; '.join(errors)}"
    return f"✅ Discord: {summary}"


def _format_theme_for_discord(theme: ThemeOutput, today: str) -> str:
    """Render one theme as a self-contained Discord message."""
    lines = [
        f"📊 **Norman Synthesis — Week ending {today}**",
        f"**Theme:** {theme.name} (urgency {theme.urgency_score}/10)",
        f"**Pain:** {theme.pain_point}",
        f"**Segments:** {_format_breakdown(theme.segment_breakdown)}",
    ]

    # Spec: show top 2 quotes in Discord (full list lives in the markdown).
    if theme.representative_quotes:
        lines.append("**Top quotes:**")
        top = theme.representative_quotes[:2]
        last = len(top) - 1
        for idx, q in enumerate(top):
            link = f"[{q.segment}](<{q.source_url}>)"
            if q.quote:
                lines.append(f'> "{q.quote}" — {link}')
            else:
                lines.append(f"> {link}")
            lines.append(f"> _Summary: {q.summary}_")
            if idx != last:
                lines.append("")

    if theme.creative_angles:
        lines.append("**Creative angles:**")
        for angle in theme.creative_angles:
            lines.append(f"• {angle.angle}: {angle.hook}")

    return "\n".join(lines)


def _format_breakdown(breakdown: dict[str, int]) -> str:
    """Render {'golf': 5, 'sensitivity': 12} as 'golf (5), sensitivity (12)'.
    Orders by count descending so the dominant segment leads."""
    if not breakdown:
        return "—"
    items = sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True)
    return ", ".join(f"{seg} ({n})" for seg, n in items)


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------

def _write_markdown_report(
    output: AnalystOutput,
    active_event: Optional[TournamentEvent] = None,
) -> str:
    os.makedirs("reports", exist_ok=True)
    filename = f"reports/{output.date}.md"

    sources = _collect_sources(output)

    try:
        with open(filename, "w") as f:
            f.write(f"# Norman Ad Scout Report — {output.date}\n\n")
            event_block = _event_window_block(
                active_event, _count_event_leads(output)
            )
            if event_block:
                f.write(event_block + "\n")

            if output.total_leads == 0:
                f.write("**Status:** Scout ran successfully — no new leads found today.\n\n")
                f.write("All discovered URLs were either previously visited or scored below threshold.\n")
            else:
                f.write(f"**Total leads:** {output.total_leads}\n")
                f.write(f"**Sources:** {', '.join(sorted(sources))}\n\n---\n\n")

                for seg_name in SEGMENT_ORDER:
                    seg_leads = output.segments.get(seg_name, [])
                    icon = SEGMENT_ICONS.get(seg_name, "📋")
                    f.write(f"## {icon} {seg_name.title()} ({len(seg_leads)} leads)\n\n")

                    if not seg_leads:
                        f.write("No leads in this segment.\n\n")
                        continue

                    for lead in seg_leads:
                        badge = "🏆 " if lead.event_window else ""
                        f.write(f"### {badge}[{lead.title}]({lead.url})\n")
                        f.write(f"**Source:** {lead.source.upper()} | **Score:** {lead.score}/100\n\n")
                        f.write(f"**Problem:** {lead.problem_detected}\n")
                        f.write(f"**Why We Win:** {lead.why_we_win}\n")
                        f.write(f"**Ad Headline:** {lead.ad_headline}\n")
                        f.write(f"**Ad Body:** {lead.ad_body}\n")
                        f.write(f"**Placement:** {lead.placement_tip}\n\n---\n\n")

            # Token usage footer
            usage_block = _format_token_usage(output.date)
            if usage_block:
                f.write(usage_block)

        return f"✅ written to {filename}"
    except Exception as e:
        return f"❌ markdown write failed: {e}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _send_webhook(message: str, stats: dict | None = None) -> str | None:
    """POST one message to Discord with rate-limit backoff.

    Sleeps DISCORD_RATE_LIMIT_DELAY before the call. On HTTP 429, honors the
    Retry-After header (fallback DISCORD_DEFAULT_RETRY_AFTER) and retries once.
    Increments stats counters ("posted", "retried", "dropped") when provided.
    Returns an error string on drop, None on success.
    """
    time.sleep(DISCORD_RATE_LIMIT_DELAY)
    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message},
            timeout=10,
        )
    except Exception as e:
        if stats is not None:
            stats["dropped"] += 1
        return str(e)

    if resp.status_code in (200, 204):
        if stats is not None:
            stats["posted"] += 1
        return None

    if resp.status_code == 429:
        retry_after = DISCORD_DEFAULT_RETRY_AFTER
        header = resp.headers.get("Retry-After")
        if header:
            try:
                retry_after = float(header)
            except ValueError:
                pass
        time.sleep(retry_after)
        try:
            resp = requests.post(
                DISCORD_WEBHOOK_URL,
                json={"content": message},
                timeout=10,
            )
        except Exception as e:
            if stats is not None:
                stats["dropped"] += 1
            return f"retry failed: {e}"
        if resp.status_code in (200, 204):
            if stats is not None:
                stats["retried"] += 1
            return None
        if stats is not None:
            stats["dropped"] += 1
        return f"HTTP {resp.status_code} after retry"

    if stats is not None:
        stats["dropped"] += 1
    return f"HTTP {resp.status_code}"


def _collect_sources(output: AnalystOutput) -> set[str]:
    return {
        lead.source
        for seg_leads in output.segments.values()
        for lead in seg_leads
    }


def _sources_ran(output: AnalystOutput) -> str:
    sources = _collect_sources(output)
    return ", ".join(sorted(sources)) if sources else "none"


def _format_token_usage(date_str: str) -> str:
    """Build the token-usage footer block from the global tracker."""
    summary = token_tracker.summary()
    total = summary["total"]

    if total["input_tokens"] == 0 and total["output_tokens"] == 0:
        return ""

    lines = [
        f"\n💰 **Token Usage — {date_str}**",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "By Agent:",
    ]
    for agent, data in summary["by_agent"].items():
        lines.append(
            f"  {agent}:  {data['input_tokens']:,} in / "
            f"{data['output_tokens']:,} out  →  ${data['cost']:.4f}"
        )
    lines.append("By Model:")
    for model, data in summary["by_model"].items():
        lines.append(
            f"  {model}:  {data['input_tokens']:,} in / "
            f"{data['output_tokens']:,} out  →  ${data['cost']:.4f}"
        )
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(
        f"TOTAL:  {total['input_tokens']:,} in / "
        f"{total['output_tokens']:,} out  →  ${total['cost']:.4f}"
    )
    return "\n".join(lines) + "\n"
