/**
 * Company logo with graceful fallback chain:
 *   1. Google favicon API (free, always-on)
 *   2. Clearbit logo API (better quality when it has the domain)
 *   3. Initial-letter color tile (deterministic hue from name hash)
 *
 * Extracted from App.jsx along with its companion ``CO_DOMAINS`` table
 * and ``guessDomain`` helper — all three are tightly coupled (the table
 * is only used by guessDomain, and guessDomain is only used by LogoImg).
 */
import { useState } from "react";

/**
 * Hand-curated map of company name → domain. Falls back to a heuristic
 * (lowercased name + ".com") when a company isn't in the table.
 *
 * Keep this list as your scraper's company roster grows — new
 * companies that don't follow the "{name}.com" pattern (e.g. "Block
 * (Square)" → "block.xyz") need an explicit entry.
 */
export const CO_DOMAINS = {
  "Anthropic":"anthropic.com","OpenAI":"openai.com","Stripe":"stripe.com","Datadog":"datadoghq.com",
  "Databricks":"databricks.com","Snowflake":"snowflake.com","Coinbase":"coinbase.com","Palantir":"palantir.com",
  "Scale AI":"scale.com","Discord":"discord.com","Ramp":"ramp.com","Plaid":"plaid.com","Reddit":"reddit.com",
  "Anduril":"anduril.com","Wiz":"wiz.io","Rippling":"rippling.com","dbt Labs":"getdbt.com",
  "Fivetran":"fivetran.com","Confluent":"confluent.io","Netflix":"netflix.com","Spotify":"spotify.com",
  "Vercel":"vercel.com","Linear":"linear.app","Supabase":"supabase.com","Figma":"figma.com",
  "Notion":"notion.so","Brex":"brex.com","Airtable":"airtable.com","MongoDB":"mongodb.com",
  "Elastic":"elastic.co","Cloudflare":"cloudflare.com","GitLab":"gitlab.com","HashiCorp":"hashicorp.com",
  "CrowdStrike":"crowdstrike.com","Block (Square)":"block.xyz","Twilio":"twilio.com","Affirm":"affirm.com",
  "Gusto":"gusto.com","Toast":"toasttab.com","Samsara":"samsara.com","Miro":"miro.com",
  "Navan":"navan.com","Grammarly":"grammarly.com","Canva":"canva.com","Zapier":"zapier.com",
  "Webflow":"webflow.com","Grafana Labs":"grafana.com","Temporal":"temporal.io",
  "Cockroach Labs":"cockroachlabs.com","PlanetScale":"planetscale.com","Vanta":"vanta.com",
  "Weights & Biases":"wandb.ai","Cohere":"cohere.com","Mistral AI":"mistral.ai",
  "Hugging Face":"huggingface.co","Perplexity":"perplexity.ai","Instacart":"instacart.com",
  "DoorDash":"doordash.com","Lyft":"lyft.com","Airbnb":"airbnb.com","Pinterest":"pinterest.com",
  "Snap":"snap.com","Robinhood":"robinhood.com","Chime":"chime.com","Faire":"faire.com",
  "Flexport":"flexport.com","Pagerduty":"pagerduty.com","Okta":"okta.com","SentinelOne":"sentinelone.com",
  "Retool":"retool.com","Neon":"neon.tech","PostHog":"posthog.com","Railway":"railway.app",
  "Tinybird":"tinybird.co","MotherDuck":"motherduck.com","Hex":"hex.tech","Visa":"visa.com",
  "KPMG":"kpmg.com","Bosch":"bosch.com","Prefect":"prefect.io","Dagster":"dagster.io",
  "Goldman Sachs":"goldmansachs.com","Capital One":"capitalone.com","Walmart":"walmart.com",
  "Disney":"disney.com","Target":"target.com","Amex":"americanexpress.com","Deloitte":"deloitte.com",
  "Uber":"uber.com","Atlassian":"atlassian.com","Dropbox":"dropbox.com","Asana":"asana.com",
  "HubSpot":"hubspot.com","Zoom":"zoom.us","Amplitude":"amplitude.com","ClickHouse":"clickhouse.com",
};

export function guessDomain(name) {
  if (!name) return null;
  const k = CO_DOMAINS[name];
  if (k) return k;
  return name.toLowerCase().replace(/[^a-z0-9]/g, "") + ".com";
}

export function LogoImg({ name, size = 32, t }) {
  const [stage, setStage] = useState(0);
  const domain = guessDomain(name);
  if (!domain || stage >= 2) {
    const letter = (name || "?")[0].toUpperCase();
    const hue = [...(name||"")].reduce((h,c)=>h+c.charCodeAt(0),0) % 360;
    return (
      <div style={{width:size,height:size,borderRadius:8,background:`hsl(${hue},25%,92%)`,display:"flex",alignItems:"center",justifyContent:"center",fontSize:size*0.44,fontWeight:800,color:`hsl(${hue},35%,40%)`,flexShrink:0,fontFamily:"system-ui,sans-serif"}}>
        {letter}
      </div>
    );
  }
  const srcs = [
    `https://www.google.com/s2/favicons?domain=${domain}&sz=${size*2}`,
    `https://logo.clearbit.com/${domain}?size=${size*2}`,
  ];
  return (
    <img src={srcs[stage]} alt="" width={size} height={size}
      style={{borderRadius:8,flexShrink:0,objectFit:"contain",background:"#fff",border:`1px solid ${t.bd}`}}
      onError={() => setStage(s => s + 1)}
    />
  );
}
