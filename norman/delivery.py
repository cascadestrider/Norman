import os
import requests
from norman.models import AnalystOutput, AnalystLead, DeliveryStatus
from norman.config import DISCORD_WEBHOOK_URL
from norman.token_tracker import token_tracker

DISCORD_CHAR_LIMIT = 2000

SEGMENT_ICONS = {
    "fishing": "🎣",
    "golf": "⛳",
    "motorcycle": "🏍️",
    "commuter": "🚗",
    "general": "🌐",
}
SEGMENT_ORDER = ["fishing", "golf", "motorcycle", "commuter", "general"]


def run_delivery(
    analyst_output: AnalystOutput,
    run_log: str = "",
    klaviyo_configured: bool = False,
    dashboard_configured: bool = False,
) -> DeliveryStatus:
    """Deliver analyst results to all configured channels."""
    status = DeliveryStatus()

    # 1. Markdown report (always first — establishes the record)
    status.markdown = _write_markdown_report(analyst_output)

    # 2. Discord — two messages (run log + lead report), or one if no leads
    status.discord = _post_discord(analyst_output, run_log)

    # 3. Klaviyo (stub)
    status.klaviyo = (
        "⚠️ Klaviyo integration not yet implemented"
        if klaviyo_configured
        else "⚠️ not configured"
    )

    # 4. Dashboard (stub)
    status.dashboard = (
        "⚠️ Dashboard integration not yet implemented"
        if dashboard_configured
        else "⚠️ not configured"
    )

    return status


# ---------------------------------------------------------------------------
# Discord
# ---------------------------------------------------------------------------

def _post_discord(output: AnalystOutput, run_log: str) -> str:
    if not DISCORD_WEBHOOK_URL:
        return "⚠️ not configured (no DISCORD_WEBHOOK_URL)"

    errors = []

    if output.total_leads == 0:
        # Single combined message when there's nothing to report
        sources_ran = _sources_ran(output)
        msg = (
            f"📡 **Norman Daily Run — {output.date}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"No new leads found today. All discovered URLs were previously visited "
            f"or scored below threshold.\n"
            f"Scouts ran: {sources_ran}\n"
        )
        if run_log:
            msg += f"\n```{run_log}```"
        err = _send_webhook(msg)
        if err:
            errors.append(err)
    else:
        # Message 1 — Pipeline Run Log
        err = _post_run_log(output, run_log)
        if err:
            errors.append(f"Run log: {err}")

        # Message 2+ — Lead Intelligence Report (chunked by segment)
        report_errors = _post_lead_report(output)
        errors.extend(report_errors)

    if errors:
        return f"⚠️ Discord partial: {'; '.join(errors)}"
    return "✅ posted to Discord (run log + lead report)"


def _post_run_log(output: AnalystOutput, run_log: str) -> str | None:
    """Post Message 1: the pipeline run log block."""
    sources = sorted(_collect_sources(output))
    seg_counts = {seg: len(leads) for seg, leads in output.segments.items() if leads}
    seg_summary = " | ".join(
        f"{SEGMENT_ICONS.get(seg, '')} {seg.title()} ({n})"
        for seg, n in seg_counts.items()
    )

    top_lines = []
    for i, lead in enumerate(output.top_3, 1):
        top_lines.append(
            f"{i}. **[{lead.title[:80]}]({lead.url})**\n"
            f"   Score: {lead.score}/100 | {lead.segment} | {lead.source}\n"
            f"   > {lead.problem_detected}\n"
            f"   > 📣 _{lead.ad_headline}_"
        )

    msg = (
        f"📡 **Norman Daily Run — {output.date}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
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

    return _send_webhook(msg[:DISCORD_CHAR_LIMIT])


def _post_lead_report(output: AnalystOutput) -> list[str]:
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
        err = _send_webhook(chunk[:DISCORD_CHAR_LIMIT])
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
# Markdown report
# ---------------------------------------------------------------------------

def _write_markdown_report(output: AnalystOutput) -> str:
    os.makedirs("reports", exist_ok=True)
    filename = f"reports/{output.date}.md"

    sources = _collect_sources(output)

    try:
        with open(filename, "w") as f:
            f.write(f"# Norman Ad Scout Report — {output.date}\n\n")

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
                        f.write(f"### [{lead.title}]({lead.url})\n")
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

def _send_webhook(message: str) -> str | None:
    """POST one message to Discord. Returns an error string on failure, None on success."""
    try:
        resp = requests.post(
            DISCORD_WEBHOOK_URL,
            json={"content": message},
            timeout=10,
        )
        if resp.status_code not in (200, 204):
            return f"HTTP {resp.status_code}"
        return None
    except Exception as e:
        return str(e)


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
