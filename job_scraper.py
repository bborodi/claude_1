#!/usr/bin/env python3
import argparse, csv, json, os, re, time, urllib.parse, urllib.request
from datetime import datetime
from xml.etree import ElementTree
try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
DEFAULT_CONFIG = {"adzuna_app_id":"","adzuna_app_key":"","location":"","country":"us","remote_only":False,"internship_only":False,"output_dir":"results"}

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f: cfg.update(json.load(f))
    cfg["adzuna_app_id"] = os.getenv("ADZUNA_APP_ID", cfg["adzuna_app_id"])
    cfg["adzuna_app_key"] = os.getenv("ADZUNA_APP_KEY", cfg["adzuna_app_key"])
    return cfg

DESIGN_KEYWORDS = {"graphic design","graphic designer","brand designer","branding","packaging designer","packaging design","visual designer","ui designer","ux designer","ui/ux","product designer","art director","creative director","illustration","illustrator","typography","motion designer","motion graphics","design intern","design internship","junior designer","marketing designer","digital designer","print designer","identity designer","logo designer","layout designer"}
EXCLUDE_FRAGMENTS = {"interior design","landscape design","fashion design","industrial design","mechanical engineer","software engineer","data scientist","accountant","nurse","teacher"}

def is_relevant(title, body=""):
    text = (title+" "+body).lower()
    if any(ex in text for ex in EXCLUDE_FRAGMENTS): return False
    return any(kw in text for kw in DESIGN_KEYWORDS)

def detect_job_type(title, body):
    text = (title+" "+body).lower()
    if any(w in text for w in ["part-time","part time","parttime"]): return "Part-time"
    if any(w in text for w in ["intern","internship","placement"]): return "Internship"
    if any(w in text for w in ["contract","freelance"]): return "Contract"
    return "Full-time"

def detect_remote(location, body):
    loc = location.lower(); text = body.lower()
    if any(w in loc or w in text for w in ["remote","anywhere","worldwide"]): return "Remote"
    if any(w in text for w in ["hybrid","flexible"]): return f"Hybrid – {location}" if location else "Hybrid"
    return location if location else "Not specified"

def make_summary(description):
    text = re.sub(r"\s+"," ",description).strip()
    sentences = re.split(r"(?<=[.!?])\s+", text)
    good = [s for s in sentences if len(s)>30][:2]
    summary = " ".join(good)
    return summary[:280]+("…" if len(summary)>280 else "")

HEADERS={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.9"}

def fetch_text(url, timeout=20):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.read().decode("utf-8",errors="replace")
    except Exception as e:
        print(f"  [warn] {url[:70]}... → {e}"); return None

def fetch_json(url, timeout=20):
    raw = fetch_text(url, timeout)
    if not raw: return None
    try: return json.loads(raw)
    except: return None

def strip_html(html):
    if _BS4: return BeautifulSoup(html,"lxml").get_text(" ",strip=True)
    return re.sub(r"<[^>]+>"," ",html).strip()

def _job(title, company, location, url, source, date="", description=""):
    d = description.strip()
    return {"title":title.strip(),"company":company.strip(),"location":location.strip(),"url":url.strip(),"source":source,"date":date.strip(),"description":d[:600],"job_type":detect_job_type(title,d),"where":detect_remote(location.strip(),d),"summary":make_summary(d)}

def scrape_the_muse(internship_only=False):
    print("  [The Muse] ..."); jobs=[]
    for page in range(0,5):
        data=fetch_json(f"https://www.themuse.com/api/public/jobs?category=Design%20%26%20UX&page={page}")
        if not data or not data.get("results"): break
        for item in data["results"]:
            title=item.get("name",""); company=item.get("company",{}).get("name","Unknown")
            locs=item.get("locations",[]); location=locs[0].get("name","") if locs else "Remote"
            link=item.get("refs",{}).get("landing_page",""); pub=item.get("publication_date","")
            body=strip_html(item.get("contents",""))
            if internship_only and "intern" not in title.lower(): continue
            if is_relevant(title,body): jobs.append(_job(title,company,location,link,"The Muse",pub,body))
        time.sleep(0.5)
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_remotive(internship_only=False):
    print("  [Remotive] ..."); jobs=[]
    data=fetch_json("https://remotive.com/api/remote-jobs?category=design-creative")
    if not data: return jobs
    for item in data.get("jobs",[]):
        title=item.get("title",""); company=item.get("company_name","Unknown")
        location=item.get("candidate_required_location","Remote"); link=item.get("url","")
        pub=item.get("publication_date",""); body=strip_html(item.get("description",""))
        if internship_only and "intern" not in title.lower(): continue
        if is_relevant(title,body): jobs.append(_job(title,company,location,link,"Remotive",pub,body))
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_arbeitnow():
    print("  [Arbeitnow] ..."); jobs=[]
    data=fetch_json("https://arbeitnow.com/api/job-board-api")
    if not data: return jobs
    for item in data.get("data",[]):
        title=item.get("title",""); company=item.get("company_name","Unknown")
        location=item.get("location",""); link=item.get("url",""); pub=item.get("created_at","")
        tags=" ".join(item.get("tags",[])); body=strip_html(item.get("description",""))
        if is_relevant(title,tags+" "+body): jobs.append(_job(title,company,location,link,"Arbeitnow",pub,body))
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_jobicy_rss():
    print("  [Jobicy RSS] ..."); jobs=[]
    xml=fetch_text("https://jobicy.com/?feed=job_feed&job_categories=design&listing_type=full_time")
    if not xml: return jobs
    try: root=ElementTree.fromstring(xml)
    except: return jobs
    for item in root.findall(".//item"):
        def t(tag):
            el=item.find(tag); return (el.text or "").strip() if el is not None else ""
        title=t("title"); link=t("link"); desc=strip_html(t("description")); pub=t("pubDate")
        creator=item.find("{http://purl.org/dc/elements/1.1/}creator")
        company=creator.text.strip() if creator is not None and creator.text else "Unknown"
        if is_relevant(title,desc): jobs.append(_job(title,company,"Remote",link,"Jobicy",pub,desc))
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_indeed_rss(query, location=""):
    jobs=[]; q=urllib.parse.quote_plus(query); loc=urllib.parse.quote_plus(location)
    xml=fetch_text(f"https://www.indeed.com/rss?q={q}&l={loc}&sort=date&fromage=14")
    if not xml: return jobs
    try: root=ElementTree.fromstring(xml)
    except: return jobs
    for item in root.findall(".//item"):
        def t(tag):
            el=item.find(tag); return (el.text or "").strip() if el is not None else ""
        title=t("title"); link=t("link"); desc=strip_html(t("description")); pub=t("pubDate")
        if is_relevant(title,desc): jobs.append(_job(title,"Unknown",location,link,"Indeed",pub,desc))
    return jobs

def scrape_indeed_all(location="", internship_only=False):
    print(f"  [Indeed RSS] location={location or 'any'} ...")
    queries=["graphic design internship","design intern"] if internship_only else ["graphic designer","graphic design internship","brand designer","packaging designer","visual designer","ui designer"]
    jobs=[]
    for q in queries: jobs+=scrape_indeed_rss(q,location); time.sleep(1)
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_linkedin_public(query):
    if not _BS4: return []
    jobs=[]; q=urllib.parse.quote_plus(query)
    html=fetch_text(f"https://www.linkedin.com/jobs/search/?keywords={q}&f_TPR=r604800&sortBy=DD")
    if not html: return jobs
    soup=BeautifulSoup(html,"lxml")
    for card in soup.select("div.base-card"):
        te=card.select_one("h3.base-search-card__title"); ce=card.select_one("h4.base-search-card__subtitle")
        le=card.select_one("span.job-search-card__location"); lke=card.select_one("a.base-card__full-link"); de=card.select_one("time")
        title=te.get_text(strip=True) if te else ""; company=ce.get_text(strip=True) if ce else "Unknown"
        loc=le.get_text(strip=True) if le else ""; link=lke["href"] if lke else ""; date=de.get("datetime","") if de else ""
        if title and is_relevant(title): jobs.append(_job(title,company,loc,link,"LinkedIn",date))
    return jobs

def scrape_linkedin_all(internship_only=False):
    print("  [LinkedIn public] ...")
    queries=["graphic design internship","design intern"] if internship_only else ["graphic designer","brand designer","visual designer"]
    jobs=[]
    for q in queries: jobs+=scrape_linkedin_public(q); time.sleep(2)
    print(f"     → {len(jobs)} jobs"); return jobs

def dedup(jobs):
    seen=set(); out=[]
    for j in jobs:
        key=(j["title"].lower(),j["company"].lower())
        if key not in seen: seen.add(key); out.append(j)
    return out

def build_html_email(jobs, date_str):
    count=len(jobs); rows=""
    for j in jobs:
        badge={"The Muse":"#6c63ff","Remotive":"#00b894","Arbeitnow":"#0984e3","Jobicy":"#e17055","Indeed":"#2089e3","LinkedIn":"#0077b5","Adzuna":"#fdcb6e"}.get(j["source"],"#888")
        ri="🌍 " if "remote" in j["where"].lower() else "📍 "
        ti={"Internship":"🎓 ","Part-time":"⏰ ","Contract":"📋 ","Full-time":"💼 "}.get(j["job_type"],"")
        rows+=f'<tr><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;"><a href="{j["url"]}" style="color:#1a1a2e;font-weight:600;font-size:14px;text-decoration:none;">{j["title"]}</a><br><span style="color:#666;font-size:12px;">{j["company"]}</span><br><span style="display:inline-block;margin-top:4px;padding:2px 7px;border-radius:10px;font-size:11px;color:#fff;background:{badge};">{j["source"]}</span></td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;font-size:13px;color:#444;">{ri}{j["where"]}</td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;font-size:13px;color:#444;">{ti}{j["job_type"]}</td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;font-size:13px;color:#555;max-width:340px;">{j["summary"] or "No description available."}</td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;text-align:center;"><a href="{j["url"]}" style="display:inline-block;padding:6px 14px;background:#1a1a2e;color:#fff;border-radius:6px;font-size:12px;text-decoration:none;white-space:nowrap;">View →</a></td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="margin:0;padding:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"><table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f7;padding:30px 0;"><tr><td align="center"><table width="700" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);"><tr><td style="background:#1a1a2e;padding:28px 32px;"><h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">🎨 Design Jobs Daily</h1><p style="margin:6px 0 0;color:#a0a8c0;font-size:14px;">{date_str} · {count} new listing{"s" if count!=1 else ""} found</p></td></tr><tr><td style="padding:0 0 24px;"><table width="100%" cellpadding="0" cellspacing="0"><thead><tr style="background:#f8f8fb;"><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">Role & Company</th><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">Location</th><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">Type</th><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">What they need</th><th></th></tr></thead><tbody>{rows}</tbody></table></td></tr><tr><td style="padding:20px 32px;background:#f8f8fb;border-top:1px solid #eee;"><p style="margin:0;color:#aaa;font-size:12px;text-align:center;">Sent automatically every morning · Sources: The Muse, Remotive, Arbeitnow, Jobicy</p></td></tr></table></td></tr></table></body></html>'''

def main():
    p=argparse.ArgumentParser(); p.add_argument("--location",default=""); p.add_argument("--remote-only",action="store_true"); p.add_argument("--internship",action="store_true"); p.add_argument("--no-indeed",action="store_true"); p.add_argument("--no-linkedin",action="store_true"); p.add_argument("--output-dir",default="")
    args=p.parse_args(); cfg=load_config()
    location=args.location or cfg.get("location",""); remote_only=args.remote_only or cfg.get("remote_only",False)
    internship=args.internship or cfg.get("internship_only",False); output_dir=args.output_dir or cfg.get("output_dir","results")
    os.makedirs(output_dir,exist_ok=True)
    print(f"Graphic Design Job Scraper\n  Location: {location or 'anywhere'}\n")
    jobs=[]
    jobs+=scrape_the_muse(internship_only=internship); jobs+=scrape_remotive(internship_only=internship)
    jobs+=scrape_arbeitnow(); jobs+=scrape_jobicy_rss()
    if not args.no_indeed: jobs+=scrape_indeed_all(location=location,internship_only=internship)
    if not args.no_linkedin: jobs+=scrape_linkedin_all(internship_only=internship)
    if remote_only: jobs=[j for j in jobs if "remote" in j["where"].lower()]
    jobs=dedup(jobs); jobs.sort(key=lambda j:j.get("date",""),reverse=True)
    ts=datetime.now().strftime("%Y%m%d_%H%M"); date_str=datetime.now().strftime("%A, %d %B %Y")
    base=os.path.join(output_dir,f"design_jobs_{ts}")
    fields=["title","company","where","job_type","source","date","url","summary"]
    with open(base+".csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(jobs)
    with open(base+".json","w",encoding="utf-8") as f: json.dump(jobs,f,indent=2)
    html_path=os.path.join(output_dir,"email.html")
    with open(html_path,"w",encoding="utf-8") as f: f.write(build_html_email(jobs,date_str))
    print(f"\n{len(jobs)} jobs found. Saved to {output_dir}/")

if __name__=="__main__": main()
