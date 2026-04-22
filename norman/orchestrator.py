"""Norman Orchestrator — dispatches scouts in parallel, aggregates, routes to analyst → delivery."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from norman.models import Lead, AnalystLead, ScoutResult
from norman.scouts import ALL_SCOUTS
from norman.scouts.base import BaseScout
from norman.analyst import run_analyst, primary_segment
from norman.classifier import classify_source_type
from norman.delivery import run_delivery
from norman.db import init_db, get_seen_urls, save_lead
from norman.config import SCORE_THRESHOLD, SEGMENTS, USE_PER_LEAD_ADS
from norman.models import AnalystOutput


def run_pipeline():
    """Execute the full Norman pipeline: scouts → analyst → delivery."""
    today = str(date.today())
    print(f"\n🚀 Norman pipeline starting — {today}")

    # --- Init DB and get seen URLs ---
    conn = init_db()
    seen_urls = get_seen_urls(conn)
    print(f"📦 {len(seen_urls)} previously seen URLs loaded")

    # --- Step 1: Dispatch all scouts in parallel ---
    scouts: list[BaseScout] = [ScoutClass() for ScoutClass in ALL_SCOUTS]
    scout_results: dict[str, ScoutResult] = {}

    print(f"🔍 Dispatching {len(scouts)} scouts in parallel...")
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {
            executor.submit(scout.run, seen_urls): scout.name
            for scout in scouts
        }
        for future in as_completed(futures):
            scout_name = futures[future]
            try:
                result = future.result()
                scout_results[scout_name] = result
                lead_count = len(result.leads)
                err_count = len(result.errors)
                status = "✅" if not result.errors else "⚠️"
                print(f"  {status} {scout_name}: {lead_count} leads, {err_count} errors")
                for note in result.notes:
                    print(f"    · {note}")
            except Exception as e:
                print(f"  ❌ {scout_name}: crashed — {e}")
                scout_results[scout_name] = ScoutResult(
                    source=scout_name.lower(),
                    leads=[],
                    errors=[f"{scout_name} crashed: {e}"],
                )

    # --- Step 2: Collect and deduplicate leads ---
    all_leads: list[Lead] = []
    seen_in_run: set[str] = set()

    for name, result in scout_results.items():
        for lead in result.leads:
            if lead.url not in seen_in_run and lead.score >= SCORE_THRESHOLD:
                seen_in_run.add(lead.url)
                all_leads.append(lead)

    print(f"\n📊 {len(all_leads)} qualifying leads after dedup (threshold: {SCORE_THRESHOLD})")

    # --- Step 2.5: Classify source type, split customer voice vs competitor intel ---
    print(f"🏷️  Classifying source type for {len(all_leads)} leads...")
    customer_voice_leads: list[Lead] = []
    competitor_intel_leads: list[Lead] = []
    for lead in all_leads:
        lead.source_type = classify_source_type(lead.title, lead.snippet, lead.url)
        if lead.source_type == "customer_voice":
            customer_voice_leads.append(lead)
        elif lead.source_type in ("retailer", "editorial_roundup"):
            competitor_intel_leads.append(lead)
        else:
            # Treat unknown as customer_voice to stay conservative — the
            # analyst can still flag them. Switch to competitor_intel if
            # we decide unknowns are more likely to be marketing noise.
            customer_voice_leads.append(lead)
    print(
        f"  customer_voice (→ analyst): {len(customer_voice_leads)} | "
        f"competitor_intel (stored only): {len(competitor_intel_leads)}"
    )

    # --- Step 3: Dispatch Analyst (or skip if USE_PER_LEAD_ADS=0) ---
    save_counts = {"new": 0, "updated": 0, "revisited": 0}

    if USE_PER_LEAD_ADS:
        print("🧠 Running Analyst...")
        try:
            analyst_output = run_analyst(customer_voice_leads)
            print(f"  ✅ Analyst enriched {analyst_output.total_leads} leads")
        except Exception as e:
            print(f"  ❌ Analyst failed: {e}")
            print("  ⚠️ Falling back to raw leads for delivery")
            analyst_output = _bypass_analyst_output(today, customer_voice_leads)

        # Build URL → {segment: AnalystLead} lookup so each customer_voice URL
        # can be paired with the AnalystLead that matches its primary segment.
        url_to_analyst: dict[str, dict[str, AnalystLead]] = {}
        for seg_leads in analyst_output.segments.values():
            for al in seg_leads:
                url_to_analyst.setdefault(al.url, {})[al.segment] = al

        for lead in customer_voice_leads:
            seg_map = url_to_analyst.get(lead.url, {})
            strategy_json = ""
            if seg_map:
                primary = primary_segment(lead)
                analyst_lead = seg_map.get(primary) or next(iter(seg_map.values()))
                try:
                    strategy_json = json.dumps({
                        "segment": analyst_lead.segment,
                        "problem_detected": analyst_lead.problem_detected,
                        "why_we_win": analyst_lead.why_we_win,
                        "ad_headline": analyst_lead.ad_headline,
                        "ad_body": analyst_lead.ad_body,
                        "placement_tip": analyst_lead.placement_tip,
                    }, ensure_ascii=False)
                except (TypeError, ValueError) as e:
                    print(f"  ⚠️ strategy serialize failed for {lead.url}: {e}")
                    strategy_json = ""
            status = save_lead(conn, lead, strategy=strategy_json)
            save_counts[status] = save_counts.get(status, 0) + 1
    else:
        print("🧠 Analyst: ⏸️  skipped (USE_PER_LEAD_ADS=0; synthesis runs weekly)")
        analyst_output = _bypass_analyst_output(today, customer_voice_leads)

        for lead in customer_voice_leads:
            status = save_lead(conn, lead, strategy="")
            save_counts[status] = save_counts.get(status, 0) + 1

    for lead in competitor_intel_leads:
        status = save_lead(conn, lead)
        save_counts[status] = save_counts.get(status, 0) + 1

    # --- Step 4: Build run log (printed to terminal + passed to Delivery) ---
    run_log = _build_run_log(
        today, scout_results, analyst_output, competitor_intel_leads,
        save_counts=save_counts,
        per_lead_ads=USE_PER_LEAD_ADS,
    )
    print(run_log)

    # --- Step 5: Dispatch Delivery ---
    print("📬 Running Delivery...")
    delivery_status = run_delivery(analyst_output, run_log=run_log)
    print(f"  Markdown:  {delivery_status.markdown}")
    print(f"  Discord:   {delivery_status.discord}")
    print(f"  Klaviyo:   {delivery_status.klaviyo}")
    print(f"  Dashboard: {delivery_status.dashboard}")

    conn.close()


def _bypass_analyst_output(today: str, customer_voice_leads: list[Lead]) -> AnalystOutput:
    """Build an AnalystOutput that carries raw leads through to delivery
    without generating ad copy. Used when USE_PER_LEAD_ADS=0 (default) and
    as the fallback when an enabled analyst call crashes.
    """
    segments: dict[str, list[AnalystLead]] = {s: [] for s in SEGMENTS + ["general"]}
    for lead in customer_voice_leads:
        seg = primary_segment(lead)
        segments.setdefault(seg, []).append(AnalystLead(
            url=lead.url, title=lead.title, score=lead.score,
            keywords=lead.keywords, source=lead.source, platform=lead.platform,
            geo=lead.geo, snippet=lead.snippet, source_type=lead.source_type,
            segment=seg,
        ))
    for seg in segments:
        segments[seg].sort(key=lambda x: x.score, reverse=True)

    all_leads = sorted(
        (l for seg_leads in segments.values() for l in seg_leads),
        key=lambda x: x.score, reverse=True,
    )
    seen: set[str] = set()
    top_3: list[AnalystLead] = []
    for l in all_leads:
        if l.url in seen:
            continue
        seen.add(l.url)
        top_3.append(l)
        if len(top_3) == 3:
            break

    return AnalystOutput(
        date=today,
        total_leads=len(customer_voice_leads),
        segments=segments,
        top_3=top_3,
    )


def _build_run_log(
    today,
    scout_results,
    analyst_output,
    competitor_intel_leads: list[Lead] | None = None,
    save_counts: dict[str, int] | None = None,
    per_lead_ads: bool = True,
) -> str:
    """Build the terminal-style run summary string. Printed locally and sent to Discord."""
    scout_statuses = []
    for name, result in scout_results.items():
        icon = "✅" if not result.errors else "⚠️"
        scout_statuses.append(f"{name} {icon}")

    top_lead = analyst_output.top_3[0] if analyst_output.top_3 else None
    top_str = (
        f"{top_lead.title[:60]} ({top_lead.source}) — Score {top_lead.score}/100 [{top_lead.source_type}]"
        if top_lead else "none"
    )

    sources_with_leads = sum(1 for r in scout_results.values() if r.leads)

    competitor_intel_leads = competitor_intel_leads or []
    retailer_count = sum(1 for l in competitor_intel_leads if l.source_type == "retailer")
    editorial_count = sum(
        1 for l in competitor_intel_leads if l.source_type == "editorial_roundup"
    )

    rotation_lines = [
        note for r in scout_results.values() for note in r.notes
    ]
    rotation_block = (
        "Query rotation:\n  " + "\n  ".join(rotation_lines) + "\n"
        if rotation_lines
        else ""
    )

    save_counts = save_counts or {}
    save_block = (
        f"Saved: {save_counts.get('new', 0)} new, "
        f"{save_counts.get('updated', 0)} updated, "
        f"{save_counts.get('revisited', 0)} revisited\n"
    )

    if per_lead_ads:
        analyst_line = f"Analyst: ✅ {analyst_output.total_leads} leads enriched\n"
    else:
        analyst_line = "Analyst: ⏸️  skipped (USE_PER_LEAD_ADS=0; synthesis runs weekly)\n"

    return (
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Norman Run Complete — {today}\n"
        f"Scouts: {' | '.join(scout_statuses)}\n"
        f"{rotation_block}"
        f"Customer-voice leads: {analyst_output.total_leads} across {sources_with_leads} sources\n"
        f"Competitor intel (not analyzed): {len(competitor_intel_leads)} "
        f"(retailer: {retailer_count}, editorial: {editorial_count})\n"
        f"Top lead: {top_str}\n"
        f"{analyst_line}"
        f"{save_block}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
