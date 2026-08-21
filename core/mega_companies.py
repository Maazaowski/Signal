"""A larger curated list of employers, used by Companies -> Add curated list.

Nothing here is tied to a country. These are companies that hire across many
markets, either because they are remote-first or because they run engineering
in several regions — but whether any of them is open to *you* depends on where
you are, which Signal cannot know. Every entry therefore seeds as
location_fit="maybe" and crawl_status="paused" until ATS detection finds a
board, which is what Companies -> Find job boards does.

Entries carry no ats_slug on purpose: these are names to probe, not verified
boards. company_seeder.py holds the smaller list that does have slugs.
"""


# -- Large multi-region employers -------------------------------

GLOBAL_ENTERPRISES = [
    {"name": "Google", "domain": "google.com", "tags": "big-tech", "employee_count": "10000+", "founded_year": 1998},
    {"name": "Microsoft", "domain": "microsoft.com", "tags": "big-tech", "employee_count": "20000+", "founded_year": 1975},
    {"name": "Amazon", "domain": "amazon.com", "tags": "big-tech,ecommerce", "employee_count": "100000+", "founded_year": 1994},
    {"name": "Meta", "domain": "meta.com", "tags": "big-tech,social", "employee_count": "5000+", "founded_year": 2004},
    {"name": "Apple", "domain": "apple.com", "tags": "big-tech", "employee_count": "5000+", "founded_year": 1976},
    {"name": "Netflix", "domain": "netflix.com", "tags": "streaming", "employee_count": "1000+", "founded_year": 1997},
    {"name": "Uber", "domain": "uber.com", "tags": "mobility", "employee_count": "5000+", "founded_year": 2009},
    {"name": "Salesforce", "domain": "salesforce.com", "tags": "saas,crm", "employee_count": "8000+", "founded_year": 1999},
    {"name": "Adobe", "domain": "adobe.com", "tags": "creative,saas", "employee_count": "6000+", "founded_year": 1982},
    {"name": "Oracle", "domain": "oracle.com", "tags": "enterprise,database", "employee_count": "40000+", "founded_year": 1977},
    {"name": "SAP", "domain": "sap.com", "tags": "enterprise,erp", "employee_count": "15000+", "founded_year": 1972},
    {"name": "IBM", "domain": "ibm.com", "tags": "enterprise,cloud", "employee_count": "100000+", "founded_year": 1911},
    {"name": "Cisco", "domain": "cisco.com", "tags": "networking", "employee_count": "12000+", "founded_year": 1984},
    {"name": "Intel", "domain": "intel.com", "tags": "semiconductor", "employee_count": "10000+", "founded_year": 1968},
    {"name": "Qualcomm", "domain": "qualcomm.com", "tags": "semiconductor", "employee_count": "8000+", "founded_year": 1985},
    {"name": "Samsung", "domain": "samsung.com", "tags": "electronics", "employee_count": "5000+", "founded_year": 1938},
    {"name": "Goldman Sachs", "domain": "goldmansachs.com", "tags": "finance", "employee_count": "10000+", "founded_year": 1869},
    {"name": "JP Morgan", "domain": "jpmorgan.com", "tags": "finance", "employee_count": "50000+", "founded_year": 1799},
    {"name": "Morgan Stanley", "domain": "morganstanley.com", "tags": "finance", "employee_count": "10000+", "founded_year": 1935},
    {"name": "Deutsche Bank", "domain": "db.com", "tags": "finance", "employee_count": "12000+", "founded_year": 1870},
    {"name": "Barclays", "domain": "barclays.com", "tags": "finance", "employee_count": "8000+", "founded_year": 1690},
    {"name": "Visa", "domain": "visa.com", "tags": "fintech,payments", "employee_count": "4000+", "founded_year": 1958},
    {"name": "Mastercard", "domain": "mastercard.com", "tags": "fintech,payments", "employee_count": "3000+", "founded_year": 1966},
    {"name": "PayPal", "domain": "paypal.com", "tags": "fintech,payments", "employee_count": "4000+", "founded_year": 1998},
    {"name": "VMware", "domain": "vmware.com", "tags": "cloud,virtualization", "employee_count": "5000+", "founded_year": 1998},
    {"name": "ServiceNow", "domain": "servicenow.com", "tags": "saas,itsm", "employee_count": "3000+", "founded_year": 2004},
    {"name": "Atlassian", "domain": "atlassian.com", "tags": "saas,devtools", "employee_count": "2000+", "founded_year": 2002},
    {"name": "Intuit", "domain": "intuit.com", "tags": "saas,fintech", "employee_count": "3000+", "founded_year": 1983},
    {"name": "LinkedIn", "domain": "linkedin.com", "tags": "social,professional", "employee_count": "3000+", "founded_year": 2002},
    {"name": "Twitter", "domain": "x.com", "tags": "social,media", "employee_count": "500+", "founded_year": 2006},
    {"name": "Spotify", "domain": "spotify.com", "tags": "music,streaming", "employee_count": "1000+", "founded_year": 2006},
    {"name": "Shopify", "domain": "shopify.com", "tags": "ecommerce,saas", "employee_count": "500+", "founded_year": 2006},
    {"name": "Twilio", "domain": "twilio.com", "tags": "communications,api", "employee_count": "1000+", "founded_year": 2008},
    {"name": "Confluent", "domain": "confluent.io", "tags": "kafka,streaming", "employee_count": "500+", "founded_year": 2014},
    {"name": "MongoDB", "domain": "mongodb.com", "tags": "database,nosql", "employee_count": "1000+", "founded_year": 2007},
    {"name": "CrowdStrike", "domain": "crowdstrike.com", "tags": "cybersecurity,cloud", "employee_count": "1000+", "founded_year": 2011},
    {"name": "Palo Alto Networks", "domain": "paloaltonetworks.com", "tags": "cybersecurity", "employee_count": "3000+", "founded_year": 2005},
    {"name": "Nutanix", "domain": "nutanix.com", "tags": "cloud,infrastructure", "employee_count": "3000+", "founded_year": 2009},
    {"name": "Cohesity", "domain": "cohesity.com", "tags": "data,backup", "employee_count": "500+", "founded_year": 2013},
    {"name": "ThoughtSpot", "domain": "thoughtspot.com", "tags": "analytics,bi", "employee_count": "500+", "founded_year": 2012},
    {"name": "Sprinklr", "domain": "sprinklr.com", "tags": "saas,social", "employee_count": "2000+", "founded_year": 2009},
    {"name": "Couchbase", "domain": "couchbase.com", "tags": "database,nosql", "employee_count": "500+", "founded_year": 2011},
    {"name": "Commvault", "domain": "commvault.com", "tags": "data,backup", "employee_count": "1000+", "founded_year": 1996},
    {"name": "NetApp", "domain": "netapp.com", "tags": "storage,cloud", "employee_count": "3000+", "founded_year": 1992},
    {"name": "Akamai", "domain": "akamai.com", "tags": "cdn,security", "employee_count": "1000+", "founded_year": 1998},
    {"name": "Freshworks", "domain": "freshworks.com", "tags": "saas,crm", "employee_count": "5000+", "founded_year": 2010},
    {"name": "ThoughtWorks", "domain": "thoughtworks.com", "tags": "consulting,engineering", "employee_count": "5000+", "founded_year": 1993},
    {"name": "Accenture", "domain": "accenture.com", "tags": "consulting,it-services", "employee_count": "300000+", "founded_year": 1989},
    {"name": "Deloitte", "domain": "deloitte.com", "tags": "consulting", "employee_count": "50000+", "founded_year": 1845},
    {"name": "EY", "domain": "ey.com", "tags": "consulting", "employee_count": "40000+", "founded_year": 1989},
    {"name": "KPMG", "domain": "kpmg.com", "tags": "consulting", "employee_count": "30000+", "founded_year": 1987},
    {"name": "Capgemini", "domain": "capgemini.com", "tags": "consulting,it-services", "employee_count": "150000+", "founded_year": 1967},
    {"name": "Cognizant", "domain": "cognizant.com", "tags": "it-services", "employee_count": "250000+", "founded_year": 1994},
    {"name": "DXC Technology", "domain": "dxc.com", "tags": "it-services", "employee_count": "20000+", "founded_year": 2017},
]


# -- Remote-first companies -------------------------------------

GLOBAL_REMOTE = [
    {"name": "GitLab", "domain": "gitlab.com", "tags": "devops,open-source,remote-first", "employee_count": "2000+", "founded_year": 2014},
    {"name": "Automattic", "domain": "automattic.com", "tags": "wordpress,open-source,remote-first", "employee_count": "2000+", "founded_year": 2005},
    {"name": "Canonical", "domain": "canonical.com", "tags": "ubuntu,open-source,remote-first", "employee_count": "1000+", "founded_year": 2004},
    {"name": "Zapier", "domain": "zapier.com", "tags": "automation,saas,remote-first", "employee_count": "800+", "founded_year": 2011},
    {"name": "Buffer", "domain": "buffer.com", "tags": "social,saas,remote-first", "employee_count": "100+", "founded_year": 2010},
    {"name": "Toggl", "domain": "toggl.com", "tags": "productivity,saas,remote-first", "employee_count": "200+", "founded_year": 2006},
    {"name": "Doist", "domain": "doist.com", "tags": "productivity,saas,remote-first", "employee_count": "100+", "founded_year": 2007},
    {"name": "Hotjar", "domain": "hotjar.com", "tags": "analytics,saas,remote-first", "employee_count": "500+", "founded_year": 2014},
    {"name": "Deel", "domain": "deel.com", "tags": "hr,payroll,remote-first", "employee_count": "3000+", "founded_year": 2019},
    {"name": "Remote.com", "domain": "remote.com", "tags": "hr,remote-first", "employee_count": "1000+", "founded_year": 2019},
    {"name": "Toptal", "domain": "toptal.com", "tags": "marketplace,talent,remote-first", "employee_count": "1000+", "founded_year": 2010},
    {"name": "Turing", "domain": "turing.com", "tags": "marketplace,talent,remote-first", "employee_count": "1000+", "founded_year": 2018},
    {"name": "Andela", "domain": "andela.com", "tags": "marketplace,talent,remote-first", "employee_count": "500+", "founded_year": 2014},
    {"name": "Mattermost", "domain": "mattermost.com", "tags": "chat,open-source,remote-first", "employee_count": "300+", "founded_year": 2016},
    {"name": "Supabase", "domain": "supabase.com", "tags": "database,open-source,remote-first", "employee_count": "200+", "founded_year": 2020},
    {"name": "Linear", "domain": "linear.app", "tags": "project-management,saas,remote-first", "employee_count": "100+", "founded_year": 2019},
    {"name": "Cal.com", "domain": "cal.com", "tags": "scheduling,open-source,remote-first", "employee_count": "100+", "founded_year": 2021},
    {"name": "Airbyte", "domain": "airbyte.com", "tags": "data,etl,open-source,remote-first", "employee_count": "200+", "founded_year": 2020},
    {"name": "Grafana Labs", "domain": "grafana.com", "tags": "monitoring,open-source,remote-first", "employee_count": "1000+", "founded_year": 2014},
    {"name": "Elastic", "domain": "elastic.co", "tags": "search,open-source,remote-first", "employee_count": "3000+", "founded_year": 2012},
    {"name": "Wikimedia Foundation", "domain": "wikimedia.org", "tags": "non-profit,open-source,remote-first", "employee_count": "500+", "founded_year": 2003},
    {"name": "Mozilla", "domain": "mozilla.org", "tags": "browser,open-source,remote-first", "employee_count": "1000+", "founded_year": 2003},
    {"name": "Red Hat", "domain": "redhat.com", "tags": "linux,open-source,remote-first", "employee_count": "20000+", "founded_year": 1993},
    {"name": "SUSE", "domain": "suse.com", "tags": "linux,open-source,remote-first", "employee_count": "2000+", "founded_year": 1992},
    {"name": "DigitalOcean", "domain": "digitalocean.com", "tags": "cloud,remote-first", "employee_count": "1000+", "founded_year": 2011},
    {"name": "Cloudflare", "domain": "cloudflare.com", "tags": "infrastructure,security,cdn", "employee_count": "3000+", "founded_year": 2009},
    {"name": "Hashicorp", "domain": "hashicorp.com", "tags": "devops,infrastructure,open-source", "employee_count": "2000+", "founded_year": 2012},
    {"name": "Kong", "domain": "konghq.com", "tags": "api-gateway,open-source", "employee_count": "500+", "founded_year": 2009},
    {"name": "Snyk", "domain": "snyk.io", "tags": "security,devtools", "employee_count": "1000+", "founded_year": 2015},
    {"name": "Docker", "domain": "docker.com", "tags": "containers,devtools", "employee_count": "500+", "founded_year": 2008},
    {"name": "CircleCI", "domain": "circleci.com", "tags": "ci-cd,devops", "employee_count": "500+", "founded_year": 2011},
    {"name": "PagerDuty", "domain": "pagerduty.com", "tags": "incident-mgmt,saas", "employee_count": "1000+", "founded_year": 2009},
    {"name": "Datadog", "domain": "datadoghq.com", "tags": "monitoring,observability", "employee_count": "5000+", "founded_year": 2010},
    {"name": "New Relic", "domain": "newrelic.com", "tags": "monitoring,observability", "employee_count": "2000+", "founded_year": 2008},
    {"name": "Sentry", "domain": "sentry.io", "tags": "error-tracking,monitoring", "employee_count": "500+", "founded_year": 2012},
    {"name": "LaunchDarkly", "domain": "launchdarkly.com", "tags": "feature-flags,devtools", "employee_count": "500+", "founded_year": 2014},
    {"name": "Vercel", "domain": "vercel.com", "tags": "cloud,frontend,devtools", "employee_count": "500+", "founded_year": 2015},
    {"name": "Netlify", "domain": "netlify.com", "tags": "cloud,jamstack", "employee_count": "300+", "founded_year": 2014},
    {"name": "Render", "domain": "render.com", "tags": "cloud,paas", "employee_count": "200+", "founded_year": 2018},
    {"name": "Fly.io", "domain": "fly.io", "tags": "cloud,edge", "employee_count": "100+", "founded_year": 2017},
    {"name": "Temporal", "domain": "temporal.io", "tags": "workflow,orchestration", "employee_count": "200+", "founded_year": 2019},
    {"name": "Cockroach Labs", "domain": "cockroachlabs.com", "tags": "database,distributed", "employee_count": "500+", "founded_year": 2015},
    {"name": "PlanetScale", "domain": "planetscale.com", "tags": "database,mysql", "employee_count": "200+", "founded_year": 2018},
    {"name": "Neon", "domain": "neon.tech", "tags": "database,postgres,serverless", "employee_count": "200+", "founded_year": 2021},
    {"name": "Retool", "domain": "retool.com", "tags": "internal-tools,low-code", "employee_count": "500+", "founded_year": 2017},
    {"name": "Webflow", "domain": "webflow.com", "tags": "no-code,web-design", "employee_count": "1000+", "founded_year": 2013},
    {"name": "Figma", "domain": "figma.com", "tags": "design,saas", "employee_count": "1000+", "founded_year": 2012},
    {"name": "Notion", "domain": "notion.so", "tags": "productivity,saas", "employee_count": "500+", "founded_year": 2016},
    {"name": "Stripe", "domain": "stripe.com", "tags": "fintech,payments,api", "employee_count": "5000+", "founded_year": 2010},
    {"name": "Plaid", "domain": "plaid.com", "tags": "fintech,api,banking", "employee_count": "1000+", "founded_year": 2013},
    {"name": "Brex", "domain": "brex.com", "tags": "fintech,corporate-cards", "employee_count": "1000+", "founded_year": 2017},
    {"name": "Ramp", "domain": "ramp.com", "tags": "fintech,expense", "employee_count": "500+", "founded_year": 2019},
    {"name": "Coinbase", "domain": "coinbase.com", "tags": "crypto,exchange", "employee_count": "3000+", "founded_year": 2012},
    {"name": "Ripple", "domain": "ripple.com", "tags": "crypto,payments", "employee_count": "500+", "founded_year": 2012},
]


def get_all_mega_companies() -> list[dict]:
    """Return every curated company with an id and a neutral location_fit."""
    from core.models import Company
    result = []
    seen = set()

    for category, companies in [
        ("global-enterprise", GLOBAL_ENTERPRISES),
        ("global-remote", GLOBAL_REMOTE),
    ]:
        for c in companies:
            company_id = Company.make_id(c["name"])
            if company_id in seen:
                continue
            seen.add(company_id)

            result.append({
                "id": company_id,
                "name": c["name"],
                "domain": c.get("domain", ""),
                "careers_url": "",
                "ats_platform": "unknown",
                "ats_slug": "",
                "founded_year": c.get("founded_year", 0),
                "employee_count": c.get("employee_count", ""),
                "tags": c.get("tags", ""),
                # "maybe", never "yes": openness depends on the user's location,
                # which is configured per profile, not baked into a list.
                "location_fit": "maybe",
                "last_crawled": "",
                "crawl_status": "paused",  # paused until ATS detected
                "notes": category,
            })

    return result
