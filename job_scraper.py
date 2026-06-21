#!/usr/bin/env python3
import csv, json, os, re, time, urllib.parse, urllib.request
from datetime import datetime
from xml.etree import ElementTree
try:
    from bs4 import BeautifulSoup
    _BS4 = True
except ImportError:
    _BS4 = False
try:
    import jobspy
    _JOBSPY = True
except ImportError:
    _JOBSPY = False
try:
    from deep_translator import GoogleTranslator
    from langdetect import detect as lang_detect
    _TRANSLATE = True
except ImportError:
    _TRANSLATE = False

SEEN_FILE   = os.path.join(os.path.dirname(__file__), "seen_jobs.json")
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

def load_config():
    cfg = {"output_dir": "results"}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f: cfg.update(json.load(f))
    return cfg

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f: return set(json.load(f))
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f: json.dump(sorted(seen), f, indent=2)

TIER1 = {"graphic design","graphic designer","brand designer","packaging designer","packaging design","brand identity","visual identity"}
TIER2 = {"visual designer","art director","motion designer","motion graphics","ui designer","ui/ux","digital designer","print designer","identity designer","logo designer","illustration","illustrator"}
TIER3 = {"creative designer","marketing designer","layout designer","junior designer","design intern","design internship","creative director","content designer","multimedia"}
EXCLUDE = {"interior design","landscape design","fashion design","industrial design","mechanical","software engineer","data scientist","accountant","nurse","teacher","real estate","sales","recruiter"}
UK_TERMS = {"uk","united kingdom","england","scotland","wales","northern ireland","london","manchester","birmingham","leeds","glasgow","edinburgh","bristol","liverpool","sheffield","cambridge","oxford","brighton","newcastle","nottingham","cardiff","belfast","reading","coventry"}
EU_WORLDWIDE = {"europe","european union","eu","germany","france","spain","italy","netherlands","belgium","sweden","denmark","norway","finland","ireland","portugal","austria","switzerland","poland","worldwide","anywhere","global","remote"}
JUNIOR_BOOSTS = {"junior","graduate","entry","intern","internship","placement","assistant","trainee"}

def score_job(title, body, location):
    t = title.lower(); b = (body or "").lower(); loc = location.lower(); combined = t+" "+b
    if any(ex in combined for ex in EXCLUDE): return 0
    if any(kw in t for kw in TIER1): stars=5
    elif any(kw in t for kw in TIER2): stars=4
    elif any(kw in t for kw in TIER3): stars=3
    elif any(kw in b for kw in TIER1|TIER2): stars=2
    elif any(kw in b for kw in TIER3): stars=1
    else: return 0
    if any(w in t for w in JUNIOR_BOOSTS): stars=min(5,stars+1)
    if not any(w in loc for w in UK_TERMS|EU_WORLDWIDE): stars=max(1,stars-1)
    return stars

def is_uk_or_eu_remote(job):
    loc=(job.get("location","")+" "+job.get("where","")).lower(); where=job.get("where","").lower()
    if any(t in loc for t in UK_TERMS): return True
    if "remote" in where or "hybrid" in where or not job.get("location","").strip():
        if any(t in loc for t in EU_WORLDWIDE): return True
        if job.get("location","").strip() in ("","Remote","Worldwide","Anywhere"): return True
    return False

HEADERS={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":"en-GB,en;q=0.9"}

def fetch_text(url, timeout=20):
    try:
        req=urllib.request.Request(url,headers=HEADERS)
        with urllib.request.urlopen(req,timeout=timeout) as r: return r.read().decode("utf-8",errors="replace")
    except Exception as e: print(f"  [warn] {url[:70]}... → {e}"); return None

def fetch_json(url, timeout=20):
    raw=fetch_text(url,timeout)
    if not raw: return None
    try: return json.loads(raw)
    except: return None

def strip_html(html):
    if _BS4: return BeautifulSoup(html,"lxml").get_text(" ",strip=True)
    return re.sub(r"<[^>]+>"," ",html).strip()

def detect_job_type(title, body):
    text=(title+" "+body).lower()
    if any(w in text for w in ["part-time","part time"]): return "Part-time"
    if any(w in text for w in ["intern","internship","placement","work experience"]): return "Internship"
    if any(w in text for w in ["contract","freelance"]): return "Contract"
    return "Full-time"

def detect_where(location, body):
    loc=location.lower(); text=body.lower()
    if any(w in loc or w in text for w in ["remote","anywhere","worldwide"]): return "Remote"
    if "hybrid" in text: return f"Hybrid – {location}" if location else "Hybrid"
    return location if location else "Not specified"

def make_summary(description):
    text=re.sub(r"\s+"," ",description or "").strip()
    sentences=re.split(r"(?<=[.!?])\s+",text)
    good=[s for s in sentences if len(s)>30][:2]
    out=" ".join(good)
    return out[:280]+("…" if len(out)>280 else "")

def translate_to_english(text):
    if not text or not _TRANSLATE: return text
    try:
        if lang_detect(text)=="en": return text
        return GoogleTranslator(source="auto",target="en").translate(text) or text
    except: return text

def _job(title,company,location,url,source,date="",description=""):
    d=description.strip() if description else ""
    return {"title":title.strip(),"company":company.strip(),"location":location.strip(),"url":url.strip(),"source":source,"date":str(date).strip(),"description":d[:600],"job_type":detect_job_type(title,d),"where":detect_where(location.strip(),d),"summary":make_summary(d),"stars":score_job(title,d,location)}

def scrape_jobspy():
    if not _JOBSPY: print("  [JobSpy] not installed — skipping"); return []
    print("  [JobSpy] LinkedIn · Glassdoor · Google Jobs · Indeed ...")
    all_jobs=[]; seen_urls=set()
    queries=["graphic designer","graphic design internship","brand designer","packaging designer","visual designer","ui designer","junior designer"]
    for query in queries:
        try:
            df=jobspy.scrape_jobs(site_name=["linkedin","glassdoor","google","indeed"],search_term=query,location="United Kingdom",results_wanted=25,hours_old=48,country_indeed="UK",verbose=0)
            for _,row in df.iterrows():
                url=str(row.get("job_url") or row.get("url") or "")
                if not url or url in seen_urls: continue
                seen_urls.add(url)
                title=str(row.get("title") or ""); company=str(row.get("company") or "Unknown")
                loc=str(row.get("location") or ""); desc=str(row.get("description") or "")
                date=str(row.get("date_posted") or ""); source=str(row.get("site") or "JobSpy").title()
                j=_job(title,company,loc,url,source,date,desc)
                if j["stars"]>0: all_jobs.append(j)
            time.sleep(2)
        except Exception as e: print(f"  [JobSpy] '{query}' failed: {e}")
    print(f"     → {len(all_jobs)} jobs"); return all_jobs

def scrape_the_muse():
    print("  [The Muse] ..."); jobs=[]
    for page in range(0,5):
        data=fetch_json(f"https://www.themuse.com/api/public/jobs?category=Design%20%26%20UX&page={page}")
        if not data or not data.get("results"): break
        for item in data["results"]:
            title=item.get("name",""); company=item.get("company",{}).get("name","Unknown")
            locs=item.get("locations",[]); loc=locs[0].get("name","") if locs else "Remote"
            link=item.get("refs",{}).get("landing_page",""); pub=item.get("publication_date","")
            body=strip_html(item.get("contents",""))
            j=_job(title,company,loc,link,"The Muse",pub,body)
            if j["stars"]>0: jobs.append(j)
        time.sleep(0.5)
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_remotive():
    print("  [Remotive] ..."); jobs=[]
    data=fetch_json("https://remotive.com/api/remote-jobs?category=design-creative")
    if not data: return jobs
    for item in data.get("jobs",[]):
        title=item.get("title",""); company=item.get("company_name","Unknown")
        loc=item.get("candidate_required_location","Remote"); link=item.get("url","")
        pub=item.get("publication_date",""); body=strip_html(item.get("description",""))
        j=_job(title,company,loc,link,"Remotive",pub,body)
        if j["stars"]>0: jobs.append(j)
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_arbeitnow():
    print("  [Arbeitnow] ..."); jobs=[]
    data=fetch_json("https://arbeitnow.com/api/job-board-api")
    if not data: return jobs
    for item in data.get("data",[]):
        title=item.get("title",""); company=item.get("company_name","Unknown")
        loc=item.get("location",""); link=item.get("url",""); pub=item.get("created_at","")
        body=strip_html(item.get("description",""))
        j=_job(title,company,loc,link,"Arbeitnow",pub,body)
        if j["stars"]>0: jobs.append(j)
    print(f"     → {len(jobs)} jobs"); return jobs

def scrape_jobicy():
    print("  [Jobicy] ..."); jobs=[]
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
        j=_job(title,company,"Remote",link,"Jobicy",pub,desc)
        if j["stars"]>0: jobs.append(j)
    print(f"     → {len(jobs)} jobs"); return jobs

def dedup(jobs):
    seen=set(); out=[]
    for j in jobs:
        key=(j["title"].lower()[:40],j["company"].lower()[:30])
        if key not in seen: seen.add(key); out.append(j)
    return out

STAR_COLOURS={5:"#2ecc71",4:"#27ae60",3:"#f39c12",2:"#e67e22",1:"#95a5a6"}
SOURCE_COLOURS={"Linkedin":"#0077b5","Glassdoor":"#0caa41","Google":"#4285f4","Indeed":"#2089e3","The Muse":"#6c63ff","Remotive":"#00b894","Arbeitnow":"#0984e3","Jobicy":"#e17055"}

def stars_html(n):
    colour=STAR_COLOURS.get(n,"#ccc")
    return f'<span style="color:{colour};font-size:15px;">{"★"*n}</span><span style="color:#ddd;font-size:15px;">{"☆"*(5-n)}</span>'

def build_html_email(jobs, date_str):
    count=len(jobs); rows=""
    for j in jobs:
        badge=SOURCE_COLOURS.get(j["source"],"#888")
        ri="🌍 " if "remote" in j["where"].lower() else "📍 "
        ti={"Internship":"🎓 ","Part-time":"⏰ ","Contract":"📋 ","Full-time":"💼 "}.get(j["job_type"],"")
        rows+=f'<tr><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;min-width:180px;"><a href="{j["url"]}" style="color:#1a1a2e;font-weight:600;font-size:14px;text-decoration:none;">{j["title"]}</a><br><span style="color:#666;font-size:12px;">{j["company"]}</span><br><span style="display:inline-block;margin-top:5px;padding:2px 7px;border-radius:10px;font-size:11px;color:#fff;background:{badge};">{j["source"]}</span></td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;font-size:13px;color:#444;white-space:nowrap;">{ri}{j["where"]}</td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;font-size:13px;color:#444;white-space:nowrap;">{ti}{j["job_type"]}</td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;">{stars_html(j["stars"])}</td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;font-size:13px;color:#555;max-width:320px;">{j["summary"] or "No description available."}</td><td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;vertical-align:top;text-align:center;"><a href="{j["url"]}" style="display:inline-block;padding:6px 14px;background:#1a1a2e;color:#fff;border-radius:6px;font-size:12px;text-decoration:none;white-space:nowrap;">View →</a></td></tr>'
    if not jobs: rows='<tr><td colspan="6" style="padding:32px;text-align:center;color:#aaa;font-size:14px;">No new design jobs today — check back tomorrow.</td></tr>'
    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"></head><body style="margin:0;padding:0;background:#f5f5f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"><table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f7;padding:30px 0;"><tr><td align="center"><table width="780" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);"><tr><td style="background:#1a1a2e;padding:28px 32px;"><h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">🎨 Design Jobs Daily</h1><p style="margin:6px 0 0;color:#a0a8c0;font-size:14px;">{date_str} · {count} new listing{"s" if count!=1 else ""} · UK &amp; EU Remote · sorted by relevance</p></td></tr><tr><td style="padding:0 0 24px;"><table width="100%" cellpadding="0" cellspacing="0"><thead><tr style="background:#f8f8fb;"><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">Role &amp; Company</th><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">Location</th><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">Type</th><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">Match</th><th style="padding:12px;text-align:left;font-size:11px;text-transform:uppercase;color:#999;font-weight:600;">What they need</th><th></th></tr></thead><tbody>{rows}</tbody></table></td></tr><tr><td style="padding:20px 32px;background:#f8f8fb;border-top:1px solid #eee;"><p style="margin:0;color:#aaa;font-size:12px;text-align:center;">★★★★★ = perfect match · Only new listings shown · Sources: LinkedIn, Glassdoor, Google Jobs, Indeed, Remotive, The Muse, Arbeitnow, Jobicy</p></td></tr></table></td></tr></table></body></html>'''

def main():
    import argparse
    p=argparse.ArgumentParser(); p.add_argument("--output-dir",default="")
    args=p.parse_args(); cfg=load_config()
    output_dir=args.output_dir or cfg.get("output_dir","results")
    os.makedirs(output_dir,exist_ok=True)
    print("🎨 Graphic Design Job Scraper\n")
    seen=load_seen(); print(f"  Seen jobs so far: {len(seen)}\n")
    jobs=[]
    jobs+=scrape_jobspy(); jobs+=scrape_the_muse(); jobs+=scrape_remotive()
    jobs+=scrape_arbeitnow(); jobs+=scrape_jobicy()
    before=len(jobs); jobs=[j for j in jobs if is_uk_or_eu_remote(j)]
    print(f"\n  Location filter: {before} → {len(jobs)} (UK + EU remote)")
    new_jobs=[j for j in jobs if j["url"] not in seen]
    print(f"  New jobs (not seen before): {len(new_jobs)}")
    new_jobs=dedup(new_jobs)
    if _TRANSLATE and new_jobs:
        print("  Translating non-English descriptions...")
        for j in new_jobs: j["summary"]=translate_to_english(j["summary"])
    new_jobs.sort(key=lambda j:(j["stars"],j.get("date","")),reverse=True)
    seen.update(j["url"] for j in new_jobs); save_seen(seen)
    ts=datetime.now().strftime("%Y%m%d_%H%M"); date_str=datetime.now().strftime("%A, %d %B %Y")
    base=os.path.join(output_dir,f"design_jobs_{ts}")
    fields=["title","company","where","job_type","stars","source","date","url","summary"]
    with open(base+".csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore"); w.writeheader(); w.writerows(new_jobs)
    with open(base+".json","w",encoding="utf-8") as f: json.dump(new_jobs,f,indent=2)
    html_path=os.path.join(output_dir,"email.html")
    with open(html_path,"w",encoding="utf-8") as f: f.write(build_html_email(new_jobs,date_str))
    print(f"\n  ✓ {len(new_jobs)} new jobs · saved to {output_dir}/")
    print(f"  ✓ seen_jobs.json updated ({len(seen)} total)")
    print("\n  Top matches:")
    for j in new_jobs[:5]: print(f"  {'★'*j['stars']} {j['title']} @ {j['company']} [{j['where']}]")

if __name__=="__main__": main()
