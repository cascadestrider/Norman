"""Norman Orchestrator — dispatches scouts in parallel, aggregates, routes to analyst → delivery."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from norman.models import Lead, ScoutResult
from norman.scouts import ALL_SCOUTS
from norman.scouts.base import BaseScout
from norman.analyst import run_analyst
from norman.classifier import classify_source_type
from norman.delivery import run_delivery
from norman.db import init_db, get_seen_urls, save_lead
from norman.config import SCORE_THRESHOLD


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
    with ThreadPoolExecutor() as executor:
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

    # --- Step 3: Dispatch Analyst on customer-voice leads only ---
    print("🧠 Running Analyst...")
    try:
        analyst_output = run_analyst(customer_voice_leads)
        print(f"  ✅ Analyst enriched {analyst_output.total_leads} leads")
    except Exception as e:
        print(f"  ❌ Analyst failed: {e}")
        print("  ⚠️ Falling back to raw leads for delivery")
        # Fallback: create minimal analyst output from raw leads
        from norman.models import AnalystOutput, AnalystLead
        fallback_leads = [
            AnalystLead(
                url=l.url, title=l.title, score=l.score, keywords=l.keywords,
                source=l.source, platform=l.platform, geo=l.geo, snippet=l.snippet,
                source_type=l.source_type,
            )
            for l in customer_voice_leads
        ]
        analyst_output = AnalystOutput(
            date=today,
            total_leads=len(customer_voice_leads),
            segments={"general": fallback_leads},
            top_3=fallback_leads[:3],
        )

    # --- Step 4: Build run log (printed to terminal + passed to Delivery) ---
    run_log = _build_run_log(
        today, scout_results, analyst_output, competitor_intel_leads
    )
    print(run_log)

    # --- Step 5: Dispatch Delivery ---
    print("📬 Running Delivery...")
    delivery_status = run_delivery(analyst_output, run_log=run_log)
    print(f"  Markdown:  {delivery_status.markdown}")
    print(f"  Discord:   {delivery_status.discord}")
    print(f"  Klaviyo:   {delivery_status.klaviyo}")
    print(f"  Dashboard: {delivery_status.dashboard}")

    # --- Save all leads (both kinds) to DB ---
    for lead in customer_voice_leads + competitor_intel_leads:
        save_lead(conn, lead)
    conn.close()


def _build_run_log(
    today,
    scout_results,
    analyst_output,
    competitor_intel_leads: list[Lead] | None = None,
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

    return (
        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Norman Run Complete — {today}\n"
        f"Scouts: {' | '.join(scout_statuses)}\n"
        f"Customer-voice leads: {analyst_output.total_leads} across {sources_with_leads} sources\n"
        f"Competitor intel (not analyzed): {len(competitor_intel_leads)} "
        f"(retailer: {retailer_count}, editorial: {editorial_count})\n"
        f"Top lead: {top_str}\n"
        f"Analyst: ✅ {analyst_output.total_leads} leads enriched\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
